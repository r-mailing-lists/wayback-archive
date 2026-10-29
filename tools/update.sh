#!/usr/bin/env bash
#
# Re-parse the lists rebuilt from the Wayback Machine.
#
# For every list directory (one with a config.json) this parses raw/ with
# rmail-parser and rebuilds the top-level lists.tsv index. Nothing is
# fetched: the lists are closed, and tools/wayback.py fetched their files once.
#
# Usage: tools/update.sh [list ...]
#   list ...    limit the run to these lists (default: all of them)
#
# Environment:
#   RMAIL_PARSER  path to the rmail-parser binary (default: ./rmail-parser)
#   ALIASES       path to an aliases.json for name resolution (optional)

set -euo pipefail

cd "$(dirname "$0")/.."

RMAIL_PARSER=${RMAIL_PARSER:-./rmail-parser}
ALIASES=${ALIASES:-}

NAMES=()
for arg in "$@"; do
  case "$arg" in
    -*) echo "Unknown option: $arg" >&2; exit 2 ;;
    *) NAMES+=("$arg") ;;
  esac
done

if [ ${#NAMES[@]} -eq 0 ]; then
  for cfg in */config.json; do
    NAMES+=("${cfg%/config.json}")
  done
fi

# Parse <list>/raw/ into <list>/processed/ and lift the stats files next to
# it, matching the layout of the other archive repositories.
parse_list() {
  local list=$1 f log
  local aliases_args=()
  if [ -n "$ALIASES" ]; then
    aliases_args=(--aliases "$ALIASES")
  fi

  rm -rf "$list/processed"
  mkdir -p "$list/processed"
  # The parser logs one line per file it writes; only surface that on failure.
  if ! log=$("$RMAIL_PARSER" parse --input "$list/raw/" --output "$list/processed/" \
      --list "$list" ${aliases_args[@]+"${aliases_args[@]}"} 2>&1); then
    echo "$log" >&2
    echo "  $list: rmail-parser failed" >&2
    return 1
  fi

  for f in meta.json index.json message-order.json contributors.json; do
    mv "$list/processed/$f" "$list/$f"
  done
}

for list in "${NAMES[@]}"; do
  if [ ! -f "$list/config.json" ]; then
    echo "No such list: $list" >&2
    exit 1
  fi
  echo "$list"
  parse_list "$list"
done

# Rebuild the index of every list from its config.json and meta.json.
{
  printf 'list\tdescription\tmessages\tthreads\tfirst_message\tlast_message\tsource_url\n'
  for cfg in */config.json; do
    # A list that has not been fetched yet has no statistics to index.
    [ -f "${cfg%/config.json}/meta.json" ] || continue
    jq -r --slurpfile meta "${cfg%/config.json}/meta.json" '
      [.list, .description, $meta[0].total_messages, $meta[0].total_threads,
       ($meta[0].first_message // ""), ($meta[0].last_message // ""), .source_url] | @tsv
    ' "$cfg"
  done
} > lists.tsv

echo "Indexed $(($(wc -l < lists.tsv) - 1)) lists in lists.tsv"
