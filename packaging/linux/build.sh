#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao (adapted from PDF Multifile Searcher)
#
# Build the Linux release files: an AppImage, a tar.gz of the program folder, the source
# archive of the program and the source archives of the bundled LGPL components.
#
# Runs inside an AlmaLinux 8 container (glibc 2.28), so the result also runs on older
# distributions. Locally:  packaging/linux/build-in-docker.sh
# Output: release/  (relative to the repository root)
#
# The program is built with the pinned standalone Python (packaging/pins.json) and the
# pinned packages (packaging/release-constraints.txt); packaging/collect_licenses.py then
# adds the "licenses" folder and stops the build if any binary has an unknown licence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_ID="abfindungsoptimierer"
WORK="${WORK:-/tmp/abfo-build}"
OUT="$ROOT/release"
pin() { python3.12 -c "import json,sys; d=json.load(open('packaging/pins.json')); print(eval('d' + sys.argv[1]))" "$1"; }

echo "== Installing build dependencies"
# Install documentation too: some packages (X11, xcb) keep their licence files there,
# and collect_licenses.py copies them into the package.
sed -i '/^tsflags=nodocs/d' /etc/dnf/dnf.conf
dnf -y -q install epel-release
# python3.12 only runs the build scripts; the program uses the standalone Python.
dnf -y -q install python3.12 python3.12-pip binutils file findutils tar gzip which \
    fontconfig freetype dbus-libs glib2 libxkbcommon libxkbcommon-x11 \
    mesa-libGL mesa-libEGL libX11 libX11-xcb libxcb xcb-util xcb-util-cursor \
    xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
    libwayland-client libwayland-cursor libwayland-egl

echo "== Creating the build environment"
rm -rf "$WORK/venv" "$WORK/bootstrap" "$WORK/dist" "$WORK/pyinstaller" "$WORK/AppDir"
mkdir -p "$WORK" "$OUT"
python3.12 -m venv "$WORK/bootstrap"
"$WORK/bootstrap/bin/pip" install --quiet zstandard
PYTHON="$("$WORK/bootstrap/bin/python" packaging/fetch_python.py linux "$WORK")"
"$PYTHON" -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet --upgrade pip
"$WORK/venv/bin/pip" install --quiet -c packaging/release-constraints.txt "$ROOT" pyinstaller
VERSION="$("$WORK/venv/bin/python" -c 'from importlib.metadata import version; print(version("abfindungsoptimierer"))')"
echo "Version: $VERSION"
echo "Bundled package versions:"
"$WORK/venv/bin/pip" freeze --exclude-editable | grep -v '^abfindungsoptimierer' | tee "$WORK/freeze.txt"

echo "== Running the tests with the bundled versions"
"$WORK/venv/bin/pip" install --quiet pytest
QT_QPA_PLATFORM=offscreen "$WORK/venv/bin/python" -m pytest -q -p no:cacheprovider tests

echo "== Building the program folder"
"$WORK/venv/bin/pyinstaller" packaging/$APP_ID.spec --noconfirm \
    --distpath "$WORK/dist" --workpath "$WORK/pyinstaller"
BUNDLE="$WORK/dist/$APP_ID"
cp packaging/README-binary.txt "$BUNDLE/README.txt"
"$WORK/venv/bin/python" packaging/collect_licenses.py --bundle "$BUNDLE" --python "$WORK/python"

echo "== Smoke tests"
"$BUNDLE/$APP_ID-cli" --version
"$BUNDLE/$APP_ID-cli" tests/fixtures/beispiel_persoenlich.xml examples/gesetzliche_vorgaben_beispiel.xml \
    --compact --pdf "$WORK/smoke.pdf" > "$WORK/smoke.json"
"$WORK/venv/bin/python" -c "import json,sys; d=json.load(open(sys.argv[1])); assert 'saldo' in d, d.keys(); print('Saldo', d['saldo'])" "$WORK/smoke.json"
head -c 5 "$WORK/smoke.pdf" | grep -q '%PDF' || { echo "PDF report missing"; exit 1; }
set +e
QT_QPA_PLATFORM=offscreen timeout 10 "$BUNDLE/$APP_ID"
STATUS=$?
set -e
[ "$STATUS" -eq 124 ] || { echo "The window program exited early with status $STATUS"; exit 1; }

echo "== tar.gz"
TARBALL="$OUT/$APP_ID-$VERSION-linux-x86_64.tar.gz"
tar -C "$WORK/dist" -czf "$TARBALL" "$APP_ID"

echo "== AppImage"
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps" "$APPDIR/usr/share/metainfo"
cp -r "$BUNDLE" "$APPDIR/usr/lib/$APP_ID"
# The AppImage additionally contains the AppImage runtime; add its notices.
"$WORK/venv/bin/python" packaging/collect_licenses.py --bundle "$APPDIR/usr/lib/$APP_ID" \
    --python "$WORK/python" --appimage
cp packaging/linux/$APP_ID.desktop "$APPDIR/$APP_ID.desktop"
cp packaging/linux/$APP_ID.desktop "$APPDIR/usr/share/applications/"
cp packaging/icons/app-icon-256.png "$APPDIR/$APP_ID.png"
cp packaging/icons/app-icon-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp packaging/icons/app-icon-256.png "$APPDIR/.DirIcon"
sed "s/@VERSION@/$VERSION/" packaging/linux/$APP_ID.appdata.xml \
    > "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml"
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# Start the window program; with --cli the command-line program (JSON output, PDF report).
HERE="$(dirname "$(readlink -f "$0")")"
if [ "${1:-}" = "--cli" ]; then
    shift
    exec "$HERE/usr/lib/abfindungsoptimierer/abfindungsoptimierer-cli" "$@"
fi
exec "$HERE/usr/lib/abfindungsoptimierer/abfindungsoptimierer" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

TOOL="$WORK/appimagetool"
curl -fsSL -o "$TOOL" "$(pin "['appimage']['appimagetool_url']")"
echo "$(pin "['appimage']['appimagetool_sha256']")  $TOOL" | sha256sum -c -
chmod +x "$TOOL"
RUNTIME="$WORK/runtime-x86_64"
curl -fsSL -o "$RUNTIME" "$(pin "['appimage']['runtime_url']")"
echo "$(pin "['appimage']['runtime_sha256']")  $RUNTIME" | sha256sum -c -
APPIMAGE="$OUT/Abfindungsoptimierer-$VERSION-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream --runtime-file "$RUNTIME" "$APPDIR" "$APPIMAGE"

echo "== Testing the AppImage"
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --cli --version | head -1
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --cli tests/fixtures/beispiel_persoenlich.xml \
    examples/gesetzliche_vorgaben_beispiel.xml --compact > "$WORK/smoke2.json"
"$WORK/venv/bin/python" -c "import json,sys; assert 'saldo' in json.load(open(sys.argv[1]))" "$WORK/smoke2.json"

echo "== Source code"
# The program's complete source (GPL-3.0) and the sources of the LGPL components travel with the packages.
SRC_DIR="$WORK/$APP_ID-$VERSION"
rm -rf "$SRC_DIR" && mkdir -p "$SRC_DIR"
tar -C "$ROOT" --exclude=./release --exclude=./.git --exclude=./.venv --exclude=./build --exclude='./*.egg-info' \
    --exclude='*/__pycache__' --exclude=./.pytest_cache -cf - . | tar -C "$SRC_DIR" -xf -
tar -C "$WORK" -czf "$OUT/$APP_ID-$VERSION-source.tar.gz" "$APP_ID-$VERSION"
"$WORK/venv/bin/python" packaging/fetch_sources.py "$OUT/sources"
cp "$WORK/freeze.txt" "$OUT/$APP_ID-$VERSION-python-packages.txt"
# One flat list (the release page has no folders): packages, source archive and the LGPL/GPL sources.
rm -f "$OUT/SHA256SUMS.txt"
{ (cd "$OUT" && sha256sum *.AppImage *.tar.gz *.txt); (cd "$OUT/sources" && sha256sum *); } > "$WORK/SHA256SUMS.txt"
mv "$WORK/SHA256SUMS.txt" "$OUT/SHA256SUMS.txt"

ls -la "$OUT" "$OUT/sources"
