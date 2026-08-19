#!/usr/bin/env python3
"""cosmic-live-wallpaper - Animated wallpaper manager for COSMIC desktop"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

import subprocess, signal, os, json, sys, time, glob, hashlib, traceback

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "cosmic-live-wallpaper")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LIBRARY_FILE = os.path.join(CONFIG_DIR, "library.json")
AUTOSTART_DIR = os.path.join(GLib.get_user_config_dir(), "autostart")
AUTOSTART_DESKTOP = "cosmic-live-wallpaper.desktop"
THUMB_DIR = os.path.join(GLib.get_user_data_dir(), "cosmic-live-wallpaper", "thumbs")
BG_BIN = "cosmic-live-bg"
VIDEO_EXT = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".gif", ".apng", ".ogv"}


def load(f, d=None):
    try:
        with open(f) as fh: return json.load(fh)
    except: return d or {}

def save(f, d):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w") as fh: json.dump(d, fh, indent=2)

def cfg(): return load(CONFIG_FILE, {"path": "", "output": "", "mute": True})
def lib(): return load(LIBRARY_FILE, {"wallpapers": [], "history": []})

def thumb_path(p):
    return os.path.join(THUMB_DIR, hashlib.md5(p.encode()).hexdigest()[:10] + ".png")

def gen_thumb(video, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-y", "-i", video, "-vf", "scale=320:-1",
                        "-frames:v", "1", "-f", "image2", out],
                       capture_output=True, timeout=8)
    except: pass

def find_renderer():
    for d in [os.path.expanduser("~/.local/bin"), "/usr/local/bin", "/usr/bin"]:
        p = os.path.join(d, BG_BIN)
        if os.path.exists(p): return p
    return None


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.cosmic.LiveWallpaper",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.proc = None
        self._cfg = cfg()
        self._lib = lib()
        try:
            r = subprocess.run(["wlr-randr"], capture_output=True, text=True, timeout=3)
            self.outputs = [l.split()[0] for l in r.stdout.splitlines()
                           if l.strip() and not l.startswith(" ") and "x" in l] or ["HDMI-A-1"]
        except: self.outputs = ["HDMI-A-1"]
        self.connect("activate", self.build)

    def build(self, app):
        self.win = Adw.ApplicationWindow(application=app, default_width=820, default_height=560,
                                          title="COSMIC Live Wallpaper")
        self.toast_ov = Adw.ToastOverlay()
        self.win.set_content(self.toast_ov)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_ov.set_child(outer)

        # Header bar
        hb = Adw.HeaderBar()
        outer.append(hb)

        # Sidebar style: Paned with sidebar + content
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_wide_handle(True)
        outer.append(paned)

        # === Left sidebar ===
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, width_request=200)
        sidebar.add_css_class("sidebar")
        paned.set_start_child(sidebar)

        # Sidebar title
        side_title = Gtk.Label(label="COSMIC Live Wallpaper")
        side_title.add_css_class("heading")
        side_title.set_margin_top(12); side_title.set_margin_bottom(8)
        side_title.set_margin_start(12); side_title.set_xalign(0)
        sidebar.append(side_title)

        sep = Gtk.Separator(); sidebar.append(sep)

        # Library section
        lib_label = Gtk.Label(label="  Library")
        lib_label.set_xalign(0); lib_label.set_margin_top(8); lib_label.set_margin_bottom(4)
        lib_label.set_opacity(0.5); lib_label.add_css_class("caption")
        sidebar.append(lib_label)

        add_files_btn = Gtk.Button(icon_name="list-add-symbolic", label="Add Video Files")
        add_files_btn.add_css_class("flat")
        add_files_btn.set_margin_start(8); add_files_btn.set_margin_end(8)
        add_files_btn.set_margin_top(4)
        add_files_btn.connect("clicked", self.add_files)
        sidebar.append(add_files_btn)

        add_folder_btn = Gtk.Button(icon_name="folder-open-symbolic", label="Add Folder")
        add_folder_btn.add_css_class("flat")
        add_folder_btn.set_margin_start(8); add_folder_btn.set_margin_end(8)
        add_folder_btn.set_margin_top(4)
        add_folder_btn.connect("clicked", self.add_folder)
        sidebar.append(add_folder_btn)

        sep2 = Gtk.Separator(); sidebar.append(sep2)

        # Settings section
        settings_label = Gtk.Label(label="  Settings")
        settings_label.set_xalign(0); settings_label.set_margin_top(8); settings_label.set_margin_bottom(4)
        settings_label.set_opacity(0.5); settings_label.add_css_class("caption")
        sidebar.append(settings_label)

        # Monitor selector
        mon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                          margin_start=12, margin_end=12, margin_top=4)
        mon_box.append(Gtk.Label(label="Monitor"))
        self.dd = Gtk.DropDown(model=Gtk.StringList.new(self.outputs))
        mon_box.append(self.dd)
        sidebar.append(mon_box)

        # Mute toggle
        self.mute = Adw.SwitchRow(title="Mute Audio")
        self.mute.set_active(self._cfg.get("mute", True))
        self.mute.connect("notify::active", lambda r, _: (
            self._cfg.update({"mute": r.get_active()}), save(CONFIG_FILE, self._cfg)))
        sidebar.append(self.mute)

        # Volume
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          margin_start=12, margin_end=12, margin_top=4)
        vol_box.append(Gtk.Label(label="Vol"))
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.vol.set_value(self._cfg.get("volume", 0)); self.vol.set_hexpand(True)
        vol_box.append(self.vol)
        sidebar.append(vol_box)

        sep3 = Gtk.Separator(); sidebar.append(sep3)

        # Autostart
        self.auto = Adw.SwitchRow(title="Start on Login")
        auto_path = os.path.join(AUTOSTART_DIR, AUTOSTART_DESKTOP)
        self.auto.set_active(os.path.exists(auto_path))
        self.auto.connect("notify::active", self.toggle_autostart)
        sidebar.append(self.auto)

        # === Right content area ===
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        paned.set_end_child(content)

        # Tab bar for content area
        self.stack = Adw.ViewStack()
        sw = Adw.ViewSwitcherBar()
        sw.set_stack(self.stack)
        content.append(sw)

        # Library page
        lib_scroll = Gtk.ScrolledWindow()
        lib_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.stack.add_titled(lib_scroll, "library", "Library")
        self.grid = Gtk.FlowBox(valign=Gtk.Align.START, homogeneous=True,
                                column_spacing=4, row_spacing=4,
                                selection_mode=Gtk.SelectionMode.NONE)
        lib_scroll.set_child(self.grid)

        # History page
        hist_scroll = Gtk.ScrolledWindow()
        hist_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.stack.add_titled(hist_scroll, "history", "History")
        self.hlist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hist_scroll.set_child(self.hlist)

        # Playback status bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                             margin_top=4, margin_bottom=4, margin_start=8, margin_end=8)
        content.append(status_box)

        self.stat_label = Gtk.Label(label="Stopped")
        self.stat_label.set_hexpand(True); self.stat_label.set_xalign(0)
        self.stat_label.set_opacity(0.7)
        status_box.append(self.stat_label)

        self.go = Gtk.Button(label="Start")
        self.go.add_css_class("suggested-action")
        self.go.connect("clicked", lambda _: self.start())
        status_box.append(self.go)

        self.no = Gtk.Button(label="Stop")
        self.no.add_css_class("destructive-action")
        self.no.set_sensitive(False)
        self.no.connect("clicked", lambda _: self.stop())
        status_box.append(self.no)

        # Load content
        self.refresh_grid()
        self.refresh_hist()
        self.win.present()

    def refresh_grid(self):
        while (c := self.grid.get_first_child()): self.grid.remove(c)
        for wp in self._lib.get("wallpapers", []):
            p = wp.get("path", "")
            if os.path.exists(p):
                self._add_card(p)
        if not self._lib.get("wallpapers"):
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                          valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
            icon = Gtk.Image.new_from_icon_name("folder-videos-symbolic")
            icon.set_pixel_size(64); icon.set_opacity(0.3)
            empty.append(icon)
            lbl = Gtk.Label(label="No wallpapers yet.\nUse the sidebar to add video files.")
            lbl.set_opacity(0.5); lbl.set_justify(Gtk.Justification.CENTER)
            empty.append(lbl)
            self.grid.append(empty)

    def _add_card(self, path):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.set_size_request(170, -1)
        card.set_margin_top(4); card.set_margin_bottom(4)
        card.set_margin_start(4); card.set_margin_end(4)
        card.add_css_class("card")

        tp = thumb_path(path)
        if not os.path.exists(tp): gen_thumb(path, tp)

        if os.path.exists(tp):
            try:
                texture = Gdk.Texture.new_from_filename(tp)
                card.append(Gtk.Picture.new_for_paintable(texture))
            except Exception:
                card.append(Gtk.Picture.new_from_icon_name("video-x-generic"))
        else:
            card.append(Gtk.Picture.new_from_icon_name("video-x-generic"))

        lbl = Gtk.Label(label=os.path.basename(path))
        lbl.set_ellipsize(3); lbl.set_xalign(0)
        card.append(lbl)

        bx = Gtk.Box(spacing=4)
        b = Gtk.Button(label="Apply"); b.add_css_class("suggested-action"); b.add_css_class("flat")
        b.set_hexpand(True); b.connect("clicked", lambda _: self.apply_wp(path)); bx.append(b)
        b2 = Gtk.Button(icon_name="user-trash-symbolic"); b2.add_css_class("flat")
        b2.connect("clicked", lambda _: self.remove_wp(path)); bx.append(b2)
        card.append(bx)
        self.grid.append(card)

    def refresh_hist(self):
        while (c := self.hlist.get_first_child()): self.hlist.remove(c)
        for e in self._lib.get("history", [])[:30]:
            p, ts = e.get("path", ""), e.get("time", 0)
            t = time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
            r = Adw.ActionRow(title=os.path.basename(p), subtitle=t, activatable=True)
            r.connect("activated", lambda _, path=p: self.apply_wp(path))
            tp = thumb_path(p)
            if os.path.exists(tp):
                try:
                    texture = Gdk.Texture.new_from_filename(tp)
                    img = Gtk.Picture.new_for_paintable(texture)
                    img.set_size_request(48, 32)
                    r.add_prefix(img)
                except: pass
            self.hlist.append(r)
        if not self._lib.get("history"):
            l = Gtk.Label(label="No history yet."); l.set_opacity(0.5); l.set_margin_top(32)
            self.hlist.append(l)

    def add_files(self, *a):
        try:
            dlg = Gtk.FileDialog(title="Select Video Files")
            f = Gtk.FileFilter(); f.set_name("Video files")
            for e in VIDEO_EXT: f.add_pattern(f"*{e}"); f.add_pattern(f"*{e.upper()}")
            fs = Gio.ListStore.new(Gtk.FileFilter); fs.append(f)
            f2 = Gtk.FileFilter(); f2.set_name("All files"); f2.add_pattern("*"); fs.append(f2)
            dlg.set_filters(fs)
            dlg.open_multiple(self.win, None, self._files_done)
        except Exception as e:
            self.toast(f"Error: {e}")

    def _files_done(self, dlg, res):
        try: files = dlg.open_multiple_finish(res)
        except GLib.Error: return
        except Exception as e:
            self.toast(f"Error: {e}"); return
        n = 0
        for i in range(files.get_n_items()):
            f = files.get_item(i)
            p = f.get_path() if hasattr(f, 'get_path') else f.get_uri()
            if p: self._add(p); n += 1
        if n: self.refresh_grid(); self.toast(f"Added {n} wallpaper(s)")

    def add_folder(self, *a):
        try:
            dlg = Gtk.FileDialog(title="Select Folder")
            dlg.select_folder(self.win, None, self._folder_done)
        except Exception as e:
            self.toast(f"Error: {e}")

    def _folder_done(self, dlg, res):
        try: folder = dlg.select_folder_finish(res)
        except GLib.Error: return
        except Exception as e:
            self.toast(f"Error: {e}"); return
        path = folder.get_path()
        if not path: return
        n = 0
        for e in VIDEO_EXT:
            for f in glob.glob(os.path.join(path, f"*{e}")) + glob.glob(os.path.join(path, f"*{e.upper()}")):
                self._add(f); n += 1
        if n: self.refresh_grid(); self.toast(f"Added {n} from folder")
        else: self.toast("No videos found in folder")

    def _add(self, path):
        path = os.path.abspath(path)
        if path not in [w["path"] for w in self._lib.get("wallpapers", [])]:
            self._lib.setdefault("wallpapers", []).append({"path": path, "added": time.time()})
            save(LIBRARY_FILE, self._lib)

    def remove_wp(self, path):
        self._lib["wallpapers"] = [w for w in self._lib["wallpapers"] if w["path"] != path]
        save(LIBRARY_FILE, self._lib)
        self.refresh_grid()

    def apply_wp(self, path):
        self.stop()
        bg = find_renderer()
        if not bg: self.toast("Renderer not found! Run: make install"); return
        idx = self.dd.get_selected()
        out = self.outputs[idx] if self.outputs and idx < len(self.outputs) else ""
        cmd = [bg, path] + ([out] if out else [])
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         preexec_fn=os.setpgrp)
            self._cfg.update({"path": path, "output": out}); save(CONFIG_FILE, self._cfg)
            h = self._lib.setdefault("history", [])
            h[:] = [x for x in h if x.get("path") != path]
            h.insert(0, {"path": path, "time": time.time()})
            self._lib["history"] = h[:50]; save(LIBRARY_FILE, self._lib)
            self.refresh_hist()
            self.stat_label.set_text(f"Playing: {os.path.basename(path)}")
            self.no.set_sensitive(True)
            self.toast(f"Playing: {os.path.basename(path)}")
        except Exception as e: self.toast(str(e))

    def start(self):
        p = self._cfg.get("path", "")
        if p and os.path.exists(p): self.apply_wp(p)
        else: self.toast("No wallpaper selected. Add a video first.")

    def stop(self):
        if self.proc:
            try: os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except: pass
            try: self.proc.wait(timeout=2)
            except:
                try: os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except: pass
            self.proc = None
        subprocess.run(["pkill", "-f", BG_BIN], capture_output=True)
        self.stat_label.set_text("Stopped"); self.no.set_sensitive(False)

    def toggle_autostart(self, row, _):
        enabled = row.get_active()
        os.makedirs(AUTOSTART_DIR, exist_ok=True)
        dp = os.path.join(AUTOSTART_DIR, AUTOSTART_DESKTOP)
        if enabled:
            bg = find_renderer()
            if not bg: return
            v, o = self._cfg.get("path", ""), self._cfg.get("output", "")
            ex = f"{bg} {v}" + (f" {o}" if o else "")
            with open(dp, "w") as f:
                f.write(f"[Desktop Entry]\nType=Application\nName=COSMIC Live Wallpaper\n"
                        f"Exec={ex}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
            self.toast("Autostart enabled")
        else:
            if os.path.exists(dp): os.remove(dp)
            self.toast("Autostart disabled")

    def toast(self, msg):
        t = Adw.Toast(title=msg); t.set_timeout(3)
        self.toast_ov.add_toast(t)


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    App().run(sys.argv)

if __name__ == "__main__":
    main()
