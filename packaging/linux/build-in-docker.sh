#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao (adapted from PDF Multifile Searcher)
#
# Build the Linux release files locally in an AlmaLinux 8 container (glibc 2.28).
# Output: release/ in the repository root.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mkdir -p "$ROOT/release"
docker run --rm \
    -v "$ROOT:/src:ro" -v "$ROOT/release:/out" \
    almalinux:8 bash -c '
        set -e
        mkdir /work
        tar -C /src --exclude=./release --exclude=./.venv -cf - . | tar -C /work -xf -
        cd /work
        bash packaging/linux/build.sh
        cp -r release/* /out/
        chown -R '"$(id -u):$(id -g)"' /out
    '
