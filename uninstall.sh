#!/bin/bash
set -e
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
rm -f "${DESTDIR}${PREFIX}/bin/cosmic-live-bg"
rm -f "${DESTDIR}${PREFIX}/bin/cosmic-live-wallpaper"
rm -rf "${DESTDIR}${PREFIX}/share/cosmic-live-wallpaper"
rm -f "${DESTDIR}/usr/share/applications/cosmic-live-wallpaper.desktop"
echo "  Uninstalled."
