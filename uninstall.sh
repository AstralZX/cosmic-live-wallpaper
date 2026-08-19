#!/bin/bash
set -e
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
ICONDIR="${PREFIX}/share/icons/hicolor"
rm -f "${DESTDIR}${PREFIX}/bin/cosmic-live-bg"
rm -f "${DESTDIR}${PREFIX}/bin/cosmic-live-wallpaper"
rm -rf "${DESTDIR}${PREFIX}/share/cosmic-live-wallpaper"
rm -f "${DESTDIR}/usr/share/applications/cosmic-live-wallpaper.desktop"
rm -f "${DESTDIR}${ICONDIR}/128x128/apps/cosmic-live-wallpaper.png"
rm -f "${DESTDIR}${ICONDIR}/256x256/apps/cosmic-live-wallpaper.png"
rm -f "${DESTDIR}${ICONDIR}/512x512/apps/cosmic-live-wallpaper.png"
echo "  Uninstalled."
