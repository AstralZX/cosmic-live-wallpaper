CC = gcc
PKG = gtk4-layer-shell-0 gtk4 gstreamer-1.0 gstreamer-video-1.0 gstreamer-app-1.0 glib-2.0
CFLAGS = $(shell pkg-config --cflags $(PKG)) -Wall -Werror=implicit-function-declaration -O2
LDFLAGS = $(shell pkg-config --libs $(PKG))

PREFIX ?= /usr/local
BINDIR = $(PREFIX)/bin
SHAREDIR = $(PREFIX)/share/cosmic-live-wallpaper

all: cosmic-live-bg

cosmic-live-bg: src/renderer.c
	$(CC) -o $@ $< $(CFLAGS) $(LDFLAGS)

install: cosmic-live-bg
	install -Dm755 cosmic-live-bg $(DESTDIR)$(BINDIR)/cosmic-live-bg
	install -Dm755 cosmic-live-wallpaper $(DESTDIR)$(BINDIR)/cosmic-live-wallpaper
	install -Dm755 gui/cosmic-live-wallpaper.py $(DESTDIR)$(SHAREDIR)/cosmic-live-wallpaper.py
	install -Dm644 cosmic-live-wallpaper.desktop $(DESTDIR)/usr/share/applications/cosmic-live-wallpaper.desktop
	@echo ""
	@echo "  Installed! Run 'cosmic-live-wallpaper' to open the GUI."
	@echo ""

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/cosmic-live-bg
	rm -f $(DESTDIR)$(BINDIR)/cosmic-live-wallpaper
	rm -rf $(DESTDIR)$(SHAREDIR)
	rm -f $(DESTDIR)/usr/share/applications/cosmic-live-wallpaper.desktop
	@echo ""
	@echo "  Uninstalled."
	@echo ""

clean:
	rm -f cosmic-live-bg

.PHONY: all install uninstall clean
