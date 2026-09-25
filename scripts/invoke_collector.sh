#!/usr/bin/env bash
# Invoke the collector synchronously and fail if the function reported an error.
#   scripts/invoke_collector.sh <function-name>
set -euo pipefail

function_name="${1:?usage: invoke_collector.sh <function-name>}"
response="$(mktemp)"
trap 'rm -f "$response"' EXIT

meta="$(aws lambda invoke --function-name "$function_name" --cli-read-timeout 120 \
  --cli-binary-format raw-in-base64-out --payload '{}' "$response")"

if jq -e '.FunctionError' <<<"$meta" >/dev/null; then
  echo "::error::the collector failed"
  cat "$response"
  exit 1
fi
jq . "$response"
