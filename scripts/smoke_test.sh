#!/usr/bin/env bash
# Post-deploy smoke tests against the public URL.
#   scripts/smoke_test.sh https://dxxxxxxxxxxxx.cloudfront.net
set -euo pipefail

site="${1:?usage: smoke_test.sh <site-url>}"
site="${site%/}"
curl_opts=(--silent --show-error --retry 5 --retry-all-errors --retry-delay 5 --max-time 20)

expect_status() { # url status
  local got
  got="$(curl "${curl_opts[@]}" -o /dev/null -w '%{http_code}' "$1")"
  [[ "$got" == "$2" ]] || { echo "FAIL $1 -> HTTP $got (expected $2)"; exit 1; }
  echo "ok   $1 -> HTTP $got"
}

expect_type() { # url content-type-substring
  local got
  got="$(curl "${curl_opts[@]}" --fail -o /dev/null -w '%{content_type}' "$1")"
  [[ "$got" == *"$2"* ]] || { echo "FAIL $1 -> $got (expected $2)"; exit 1; }
  echo "ok   $1 -> $got"
}

expect_status "$site/" 200
expect_status "$site/does-not-exist" 404
expect_type "$site/assets/app.mjs" "javascript"
expect_type "$site/latest/openai" "text/html"

curl "${curl_opts[@]}" --fail "$site/news.json" | python3 -c '
import json, sys
data = json.load(sys.stdin)
items, generated = data["items"], data["generatedAt"]
assert items, "news.json has no items"
print(f"ok   news.json is valid JSON: {len(items)} items, generated {generated}")
'

curl "${curl_opts[@]}" --fail "$site/feed.xml" | python3 -c '
import sys
import xml.etree.ElementTree as ET
root = ET.fromstring(sys.stdin.buffer.read())
assert root.tag == "rss", root.tag
count = len(root.findall("./channel/item"))
print(f"ok   feed.xml is valid XML: {count} items")
'
echo "smoke tests passed"
