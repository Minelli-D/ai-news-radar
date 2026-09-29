#!/usr/bin/env bash
# Render scripts/app-icon.svg to the PNG app icons in site/assets/ (committed; run again only
# after changing the SVG). Needs Inkscape and ImageMagick.
#   scripts/render_icons.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# 180: iOS home screen (apple-touch-icon). 192 and 512: the web app manifest (Android, desktop).
for size in 180 192 512; do
  inkscape "$root/scripts/app-icon.svg" --export-width="$size" --export-height="$size" \
    --export-filename="$tmp/icon-$size.png" 2>/dev/null
  # Opaque RGB with no metadata or timestamps, so the same SVG gives the same bytes.
  magick "$tmp/icon-$size.png" -alpha off -strip -define png:exclude-chunks=date,time \
    "$root/site/assets/icon-$size.png"
done
ls -l "$root"/site/assets/icon-*.png
