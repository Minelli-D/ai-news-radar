#!/usr/bin/env bash
# Upload site/ to the private site bucket with per-type cache headers.
#   scripts/deploy_site.sh <bucket> [version]      (add --dryrun via DRYRUN=1)
#
# - "?v=dev" in HTML, module imports and the web app manifest becomes "?v=<version>" so
#   long-cached assets refresh.
# - The collector's objects (news.json, feed.xml, latest/*) are never deleted or overwritten.
set -euo pipefail

bucket="${1:?usage: deploy_site.sh <bucket> [version]}"
version="${2:-dev}"
dryrun=()
[[ "${DRYRUN:-}" == "1" ]] && dryrun=(--dryrun)

root="$(cd "$(dirname "$0")/.." && pwd)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
cp -R "$root/site/." "$stage/"
find "$stage" -type f \( -name '*.html' -o -name '*.mjs' -o -name '*.webmanifest' \) -exec sed -i "s/?v=dev/?v=${version}/g" {} +

collector_owned=(--exclude "news.json" --exclude "feed.xml" --exclude "latest/*")

# Pages and small root files: 5 minutes, like the data files.
aws s3 sync "$stage" "s3://${bucket}" --delete "${dryrun[@]}" \
  --exclude "assets/*" --exclude "*.webmanifest" "${collector_owned[@]}" \
  --cache-control "public, max-age=300"
# The CLI does not know .webmanifest, and browsers ignore a manifest served with a generic type.
aws s3 cp "$stage/manifest.webmanifest" "s3://${bucket}/manifest.webmanifest" "${dryrun[@]}" \
  --content-type "application/manifest+json" --cache-control "public, max-age=300"

# Versioned assets: 1 day. ES modules need an explicit JavaScript MIME type.
aws s3 sync "$stage/assets" "s3://${bucket}/assets" --delete "${dryrun[@]}" \
  --exclude "*.mjs" --cache-control "public, max-age=86400"
aws s3 cp "$stage/assets" "s3://${bucket}/assets" --recursive "${dryrun[@]}" \
  --exclude "*" --include "*.mjs" \
  --content-type "text/javascript; charset=utf-8" --cache-control "public, max-age=86400"
