# COSMIC Live Wallpaper

Animated/video wallpaper for the COSMIC desktop on Wayland.

Most video wallpaper tools (mpvpaper, Papyrus) don't work on COSMIC's compositor — they crash with OpenGL errors or just render a white screen. This project works around that by using a GTK4 window pinned to the Wayland background layer via [gtk4-layer-shell](https://github.com/wlr-gaming/gtk4-layer-shell), with GStreamer decoding video frames into the window directly. No OpenGL compositing tricks, no X11 hacks.

## How it works

1. **`cosmic-live-bg`** — A small C renderer that creates a GTK4 window, pins it to the background layer via layer-shell, and plays video using GStreamer
2. **`cosmic-live-wallpaper`** — A Python GTK4/libadwaita GUI for managing your wallpaper library, picking monitors, and controlling playback

The renderer loops videos by tearing down and recreating the GStreamer pipeline on end-of-stream. Each frame is decoded into a reusable pixbuf, converted to a GdkTexture, and displayed on a GtkPicture widget. Excess frames are dropped to stay smooth under load.

## Requirements

**Runtime:**
- A Wayland compositor that supports `wlr-layer-shell` (COSMIC, Hyprland, Sway, etc.)
- GStreamer with `gst-libav` (for broad codec support)

**Build dependencies** (Arch Linux):
```
gtk4-layer-shell-0
gtk4
gstreamer
python-gobject
```

On other distros, install the equivalent `-dev`/`-devel` packages for:
- `gtk4-layer-shell`
- `gtk4`
- `gstreamer-1.0`, `gstreamer-video-1.0`, `gstreamer-app-1.0`
- `glib-2.0`
- `pkg-config`

The GUI also needs `ffmpeg` in your PATH for generating thumbnails.

## Install

```bash
make
sudo make install
```

Or use the install script:
```bash
sudo ./install.sh
```

To install to `~/.local` instead of `/usr/local`:
```bash
make PREFIX=$HOME/.local install
```

## Usage

### GUI

```bash
cosmic-live-wallpaper
```

- **Library** — Add video files or folders, browse your collection with thumbnails, apply or remove wallpapers
- **Controls** — Pick your monitor, start/stop playback, mute audio, enable autostart on login
- **History** — Recently used wallpapers with timestamps, click to re-apply

### Command line

```bash
cosmic-live-bg /path/to/video.mp4
cosmic-live-bg /path/to/video.mp4 HDMI-A-1
```

## Features

- Plays any video GStreamer supports (mp4, webm, mkv, avi, mov, gif, etc.)
- Infinite looping — video restarts seamlessly when it ends
- Multi-monitor support — choose which display to wallpaper
- Wallpaper library with thumbnails — add files or entire folders
- Playback history — remembers your last 30 used wallpapers
- Audio mute toggle (muted by default since it's a wallpaper)
- Autostart on login via `.desktop` file
- Lightweight renderer — only one active pipeline, frames dropped to stay smooth
- GStreamer drops excess frames to keep up under load

## Uninstall

```bash
sudo make uninstall
```

## Contributing

Contributions welcome. Some ideas:

- Volume slider that actually works with playbin
- Per-wallpaper settings (brightness, speed, etc.)
- Playlist / random rotation mode
- System tray integration
- Static image fallback when no video is set

## License

[GNU Affero General Public License v3.0](LICENSE)
