#!/usr/bin/env python3
"""cosmic-live-wallpaper - Animated wallpaper manager for COSMIC desktop"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

import subprocess, signal, os, json, sys, time, glob, hashlib, threading

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
        self._watch_id = None
        try:
            r = subprocess.run(["wlr-randr"], capture_output=True, text=True, timeout=3)
            self.outputs = [l.split()[0] for l in r.stdout.splitlines()
                           if l.strip() and not l.startswith(" ") and "x" in l] or ["HDMI-A-1"]
        except: self.outputs = ["HDMI-A-1"]
        self.connect("activate", self.build)

    def build(self, app):
        self.win = Adw.ApplicationWindow(application=app, default_width=860, default_height=560,
                                          title="COSMIC Live Wallpaper")
        self.toast_ov = Adw.ToastOverlay()
        self.win.set_content(self.toast_ov)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_ov.set_child(vbox)

        hb = Adw.HeaderBar()
        vbox.append(hb)

        sw = Adw.ViewSwitcher()
        self.stack = Adw.ViewStack()
        sw.set_stack(self.stack)
        hb.set_title_widget(sw)

        # ── Library Tab ──
        lib_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.stack.add_titled(lib_page, "library", "Library")

        lib_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                              margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        add_files_btn = Gtk.Button(icon_name="list-add-symbolic", label="Add Videos")
        add_files_btn.add_css_class("suggested-action")
        add_files_btn.connect("clicked", self.add_files)
        lib_toolbar.append(add_files_btn)

        add_folder_btn = Gtk.Button(icon_name="folder-open-symbolic", label="Add Folder")
        add_folder_btn.connect("clicked", self.add_folder)
        lib_toolbar.append(add_folder_btn)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh library")
        refresh_btn.connect("clicked", lambda _: self.refresh_grid())
        lib_toolbar.append(refresh_btn)

        lib_page.append(lib_toolbar)

        lib_scroll = Gtk.ScrolledWindow()
        lib_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        lib_scroll.set_vexpand(True)
        self.grid = Gtk.FlowBox(valign=Gtk.Align.START, homogeneous=True,
                                column_spacing=4, row_spacing=4,
                                selection_mode=Gtk.SelectionMode.NONE)
        lib_scroll.set_child(self.grid)
        lib_page.append(lib_scroll)

        # ── Controls Tab ──
        ctl_scroll = Gtk.ScrolledWindow()
        ctl_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.stack.add_titled(ctl_scroll, "controls", "Controls")

        ctl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        ctl_scroll.set_child(ctl)

        # Playback group
        g_play = Adw.PreferencesGroup(title="Playback")
        self.stat = Adw.ActionRow(title="Status", subtitle="Stopped")
        g_play.add(self.stat)
        br = Adw.ActionRow()
        self.go = Gtk.Button(label="Start"); self.go.add_css_class("suggested-action")
        self.go.connect("clicked", lambda _: self.start())
        br.add_suffix(self.go)
        self.no = Gtk.Button(label="Stop"); self.no.add_css_class("destructive-action")
        self.no.set_sensitive(False); self.no.connect("clicked", lambda _: self.stop())
        br.add_suffix(self.no)
        g_play.add(br)
        ctl.append(g_play)

        # Monitor group
        g_mon = Adw.PreferencesGroup(title="Monitor")
        row = Adw.ActionRow(title="Target Display")
        self.dd = Gtk.DropDown(model=Gtk.StringList.new(self.outputs))
        row.add_suffix(self.dd)
        g_mon.add(row)
        ctl.append(g_mon)

        # Audio group
        g_audio = Adw.PreferencesGroup(title="Audio")
        self.mute = Adw.SwitchRow(title="Mute Audio", subtitle="Recommended for wallpapers")
        self.mute.set_active(self._cfg.get("mute", True))
        self.mute.connect("notify::active", lambda r, _: (
            self._cfg.update({"mute": r.get_active()}), save(CONFIG_FILE, self._cfg)))
        g_audio.add(self.mute)
        ar = Adw.ActionRow(title="Volume")
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.vol.set_value(self._cfg.get("volume", 0)); self.vol.set_hexpand(True)
        ar.add_suffix(self.vol)
        g_audio.add(ar)
        ctl.append(g_audio)

        # Startup group
        g_start = Adw.PreferencesGroup(title="Startup")
        self.auto = Adw.SwitchRow(title="Start on Login")
        auto_path = os.path.join(AUTOSTART_DIR, AUTOSTART_DESKTOP)
        self.auto.set_active(os.path.exists(auto_path))
        self.auto.connect("notify::active", self.toggle_autostart)
        g_start.add(self.auto)
        ctl.append(g_start)

        # ── History Tab ──
        hist_scroll = Gtk.ScrolledWindow()
        hist_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.stack.add_titled(hist_scroll, "history", "History")
        self.hlist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hist_scroll.set_child(self.hlist)

        # Footer
        foot = Gtk.CenterBox()
        lbl = Gtk.Label(label="cosmic-live-wallpaper | GTK4 + layer-shell + GStreamer")
        lbl.set_opacity(0.4); lbl.add_css_class("caption")
        foot.set_center_widget(lbl)
        vbox.append(foot)

        self.refresh_grid()
        self.refresh_hist()
        self.win.present()

    def refresh_grid(self):
        self._lib = lib()
        while (c := self.grid.get_first_child()): self.grid.remove(c)
        wps = self._lib.get("wallpapers", [])
        existing = {p for p in [wp.get("path", "") for wp in wps] if p}
        for wp in wps:
            p = wp.get("path", "")
            if os.path.exists(p):
                self._add_card(p)
        if not wps:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                          valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
            icon = Gtk.Image.new_from_icon_name("folder-videos-symbolic")
            icon.set_pixel_size(64); icon.set_opacity(0.3)
            empty.append(icon)
            lbl = Gtk.Label(label="No wallpapers yet.\nClick \"Add Videos\" to get started.")
            lbl.set_opacity(0.5); lbl.set_justify(Gtk.Justification.CENTER)
            empty.append(lbl)
            self.grid.append(empty)
        self._last_lib_mtime = self._get_lib_mtime()

    def _get_lib_mtime(self):
        try: return os.path.getmtime(LIBRARY_FILE)
        except: return 0

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
            except: card.append(Gtk.Picture.new_from_icon_name("video-x-generic"))
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
            p = f.get_path() if hasattr(f, 'get_path') else None
            if p: self._add(p); n += 1
        if n:
            self._lib = lib()
            self.refresh_grid()
            self.toast(f"Added {n} wallpaper(s)")

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
        for ext in VIDEO_EXT:
            for f in glob.glob(os.path.join(path, f"*{ext}")) + glob.glob(os.path.join(path, f"*{ext.upper()}")):
                self._add(f); n += 1
        if n:
            self._lib = lib()
            self.refresh_grid()
            self.toast(f"Added {n} from folder")
        else:
            self.toast("No videos found in folder")

    def _add(self, path):
        path = os.path.abspath(path)
        if path not in [w["path"] for w in self._lib.get("wallpapers", [])]:
            self._lib.setdefault("wallpapers", []).append({"path": path, "added": time.time()})
            save(LIBRARY_FILE, self._lib)

    def remove_wp(self, path):
        self._lib["wallpapers"] = [w for w in self._lib["wallpapers"] if w["path"] != path]
        save(LIBRARY_FILE, self._lib)
        self.refresh_grid()
        self.toast("Removed wallpaper")

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
            self.stat.set_subtitle(f"Playing: {os.path.basename(path)}")
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
        self.stat.set_subtitle("Stopped"); self.no.set_sensitive(False)

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

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._last_lib_mtime = self._get_lib_mtime()
        GLib.timeout_add(2000, self._auto_reload)

    def _auto_reload(self):
        try:
            mtime = self._get_lib_mtime()
            if mtime != self._last_lib_mtime:
                self._last_lib_mtime = mtime
                self._lib = lib()
                self.refresh_grid()
                self.refresh_hist()
        except: pass
        return True


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    App().run(sys.argv)

if __name__ == "__main__":
    main()
