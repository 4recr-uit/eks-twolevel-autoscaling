#!/usr/bin/env bash
# E2 command shortcuts; no cluster apply/delete is performed by this script.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command=${1:-help}
if (($#)); then shift; fi
case "$command" in
  init) exec python ./run.py init "$@" ;;
  inspect) exec python ./run.py inspect "$@" ;;
  collect) exec python ./collect.py "$@" ;;
  report) exec python ./report.py "$@" ;;
  timeline) exec python ./timeline.py "$@" ;;
  compare) exec python ./compare.py "$@" ;;
  load)
    if (($# != 2)) || [[ $1 != burst ]]; then echo "Dùng: bash run.sh load burst RUN_DIR" >&2; exit 2; fi
    dir=$2
    if [[ ! -f "$dir/metadata.json" || ! -d "$dir/raw" || -e "$dir/raw/k6-summary.json" ]]; then
      echo "RUN_DIR không hợp lệ hoặc summary đã tồn tại; không ghi đè." >&2; exit 1
    fi
    python -c 'import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); metadata = json.loads((p / "metadata.json").read_text(encoding="utf-8-sig"))
collection = json.loads((p / "collection.json").read_text(encoding="utf-8-sig"))
if metadata.get("scenario") != "E2" or metadata.get("profile") != sys.argv[2] or metadata.get("variant") != "elastic" or collection.get("status") != "collecting":
    sys.exit("Profile hoặc collector không khớp; không phát tải.")' "$dir" "$1"
    exec k6 run --summary-export "$dir/raw/k6-summary.json" ./burst.js ;;
  *) echo "Dùng: bash run.sh {init|inspect|collect|load|report|timeline|compare} ..."; echo "Xem README.md để chuẩn bị, apply và khôi phục." ;;
esac
