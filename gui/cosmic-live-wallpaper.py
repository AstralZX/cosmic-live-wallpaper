#!/usr/bin/env python3
"""cosmic-live-wallpaper - Animated wallpaper manager for COSMIC desktop"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

import subprocess, signal, os, json, sys, time, glob, hashlib

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


class Card(Gtk.Box):
    def __init__(self, path, on_apply, on_remove):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.path = path
        self.set_size_request(170, -1)
        self.set_margin_top(4); self.set_margin_bottom(4)
        self.set_margin_start(4); self.set_margin_end(4)
        self.add_css_class("card")

        tp = thumb_path(path)
        if not os.path.exists(tp): gen_thumb(path, tp)

        if os.path.exists(tp):
            self.append(Gtk.Picture.new_for_paintable(Gdk.Texture.new_from_filename(tp)))
        else:
            self.append(Gtk.Picture.new_from_icon_name("video-x-generic"))

        lbl = Gtk.Label(label=os.path.basename(path))
        lbl.set_ellipsize(3); lbl.set_xalign(0)
        self.append(lbl)

        bx = Gtk.Box(spacing=4)
        b = Gtk.Button(label="Apply"); b.add_css_class("suggested-action"); b.add_css_class("flat")
        b.set_hexpand(True); b.connect("clicked", lambda _: on_apply(path)); bx.append(b)
        b2 = Gtk.Button(icon_name="user-trash-symbolic"); b2.add_css_class("flat")
        b2.connect("clicked", lambda _: on_remove(path)); bx.append(b2)
        self.append(bx)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.cosmic.LiveWallpaper")
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
        self.win = Adw.ApplicationWindow(application=app, default_width=820, default_height=540,
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

        for icon, label, name in [("list-add-symbolic", "Library", "lib"),
                                   ("emblem-system-symbolic", "Controls", "ctl"),
                                   ("document-open-recent-symbolic", "History", "hist")]:
            btn = Gtk.Button(icon_name=icon)
            if name == "lib":
                btn.set_tooltip_text("Add video files")
                btn.connect("clicked", self.add_files)
            elif name == "ctl":
                btn.set_tooltip_text("Add folder of videos")
                btn.connect("clicked", self.add_folder)
            else:
                btn.set_tooltip_text("Add folder of videos")
                btn.connect("clicked", self.add_folder)
            hb.pack_start(btn)

        # Library
        scroll = Gtk.ScrolledWindow()
        self.stack.add_titled(scroll, "lib", "Library")
        self.grid = Gtk.FlowBox(valign=Gtk.Align.START, homogeneous=True,
                                column_spacing=4, row_spacing=4,
                                selection_mode=Gtk.SelectionMode.NONE)
        scroll.set_child(self.grid)

        # Controls
        ctl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        self.stack.add_titled(ctl, "ctl", "Controls")

        g1 = Adw.PreferencesGroup(title="Monitor")
        row = Adw.ActionRow(title="Target Display")
        self.dd = Gtk.DropDown(model=Gtk.StringList.new(self.outputs))
        row.add_suffix(self.dd); g1.add(row); ctl.append(g1)

        g2 = Adw.PreferencesGroup(title="Playback")
        self.stat = Adw.ActionRow(title="Status", subtitle="Stopped"); g2.add(self.stat)
        br = Adw.ActionRow()
        self.go = Gtk.Button(label="Start"); self.go.add_css_class("suggested-action")
        self.go.connect("clicked", lambda _: self.start()); br.add_suffix(self.go)
        self.no = Gtk.Button(label="Stop"); self.no.add_css_class("destructive-action")
        self.no.set_sensitive(False); self.no.connect("clicked", lambda _: self.stop())
        br.add_suffix(self.no); g2.add(br); ctl.append(g2)

        g3 = Adw.PreferencesGroup(title="Audio")
        self.mute = Adw.SwitchRow(title="Mute Audio", subtitle="Recommended for wallpapers")
        self.mute.set_active(self._cfg.get("mute", True))
        self.mute.connect("notify::active", lambda r, _: self._cfg.update({"mute": r.get_active()}) or save(CONFIG_FILE, self._cfg))
        g3.add(self.mute); ctl.append(g3)

        ar = Adw.ActionRow(title="Volume")
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.vol.set_value(self._cfg.get("volume", 0)); self.vol.set_hexpand(True)
        ar.add_suffix(self.vol); g3.add(ar)

        g4 = Adw.PreferencesGroup(title="Startup")
        self.auto = Adw.SwitchRow(title="Start on Login")
        auto_path = os.path.join(AUTOSTART_DIR, AUTOSTART_DESKTOP)
        self.auto.set_active(os.path.exists(auto_path))
        self.auto.connect("notify::active", self.toggle_autostart)
        g4.add(self.auto); ctl.append(g4)

        # History
        hscroll = Gtk.ScrolledWindow()
        self.stack.add_titled(hscroll, "hist", "History")
        self.hlist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hscroll.set_child(self.hlist)

        foot = Gtk.CenterBox()
        lbl = Gtk.Label(label="cosmic-live-wallpaper | GTK4 + layer-shell + GStreamer")
        lbl.set_opacity(0.4); lbl.add_css_class("caption")
        foot.set_center_widget(lbl); vbox.append(foot)

        self.refresh_grid()
        self.refresh_hist()
        self.win.present()

    def refresh_grid(self):
        while (c := self.grid.get_first_child()): self.grid.remove(c)
        for wp in self._lib.get("wallpapers", []):
            p = wp.get("path", "")
            if os.path.exists(p):
                self.grid.append(Card(p, self.apply_wp, self.remove_wp))
        if not self._lib.get("wallpapers"):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, margin_top=64)
            i = Gtk.Image.new_from_icon_name("folder-videos-symbolic")
            i.set_pixel_size(48); i.set_opacity(0.3); box.append(i)
            l = Gtk.Label(label="No wallpapers yet.\nClick + to add videos."); l.set_opacity(0.5)
            box.append(l); self.grid.append(box)

    def refresh_hist(self):
        while (c := self.hlist.get_first_child()): self.hlist.remove(c)
        for e in self._lib.get("history", [])[:30]:
            p, ts = e.get("path", ""), e.get("time", 0)
            t = time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
            r = Adw.ActionRow(title=os.path.basename(p), subtitle=t, activatable=True)
            r.connect("activated", lambda _, path=p: self.apply_wp(path))
            tp = thumb_path(p)
            if os.path.exists(tp):
                img = Gtk.Picture.new_for_paintable(Gdk.Texture.new_from_filename(tp))
                img.set_size_request(48, 32); r.add_prefix(img)
            self.hlist.append(r)
        if not self._lib.get("history"):
            l = Gtk.Label(label="No history yet."); l.set_opacity(0.5); l.set_margin_top(32)
            self.hlist.append(l)

    def add_files(self, *a):
        dlg = Gtk.FileDialog(title="Select Video Files")
        f = Gtk.FileFilter(); f.set_name("Video files")
        for e in VIDEO_EXT: f.add_pattern(f"*{e}"); f.add_pattern(f"*{e.upper()}")
        fs = Gio.ListStore.new(Gtk.FileFilter); fs.append(f)
        f2 = Gtk.FileFilter(); f2.set_name("All files"); f2.add_pattern("*"); fs.append(f2)
        dlg.set_filters(fs)
        dlg.open_multiple(self.win, None, self._files_done)

    def _files_done(self, dlg, res):
        try: files = dlg.open_multiple_finish(res)
        except: return
        n = 0
        for i in range(files.get_n_items()):
            p = files.get_item(i).get_path()
            if p: self._add(p); n += 1
        if n: self.refresh_grid(); self.toast(f"Added {n} wallpaper(s)")

    def add_folder(self, *a):
        dlg = Gtk.FileDialog(title="Select Folder")
        dlg.select_folder(self.win, None, self._folder_done)

    def _folder_done(self, dlg, res):
        try: folder = dlg.select_folder_finish(res)
        except: return
        path = folder.get_path(); n = 0
        for e in VIDEO_EXT:
            for f in glob.glob(os.path.join(path, f"*{e}")) + glob.glob(os.path.join(path, f"*{e.upper()}")):
                self._add(f); n += 1
        if n: self.refresh_grid(); self.toast(f"Added {n} from folder")
        else: self.toast("No videos found")

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
        out = self.outputs[self.dd.get_selected()] if self.outputs else ""
        cmd = [bg, path] + ([out] if out else [])
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setpgrp)
            self._cfg.update({"path": path, "output": out}); save(CONFIG_FILE, self._cfg)
            h = self._lib.setdefault("history", [])
            h[:] = [x for x in h if x.get("path") != path]
            h.insert(0, {"path": path, "time": time.time()})
            self._lib["history"] = h[:50]; save(LIBRARY_FILE, self._lib)
            self.refresh_hist()
            self.stat.set_subtitle(f"Playing: {os.path.basename(path)}")
            self.no.set_sensitive(True); self.toast(f"Playing: {os.path.basename(path)}")
        except Exception as e: self.toast(str(e))

    def start(self):
        p = self._cfg.get("path", "")
        if p and os.path.exists(p): self.apply_wp(p)

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
        t = Adw.Toast(title=msg); t.set_timeout(2); self.toast_ov.add_toast(t)


from gi.repository import Gdk
def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    App().run(sys.argv)

if __name__ == "__main__":
    main()
