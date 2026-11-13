#!/usr/bin/env bash
# E1 command shortcuts; no cluster apply/delete is performed by this script.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command=${1:-help}
if (($#)); then shift; fi
case "$command" in
  init) exec python ./run.py init "$@" ;;
  inspect) exec python ./run.py inspect "$@" ;;
  collect) exec python ./collect.py "$@" ;;
  report) exec python ./report.py "$@" ;;
  compare) exec python ./compare.py "$@" ;;
  load)
    if (($# != 2)); then echo "Dùng: bash run.sh load step|burst RUN_DIR" >&2; exit 2; fi
    case "$1" in step) file=step.js ;; burst) file=burst.js ;; *) echo "Profile không hợp lệ" >&2; exit 2 ;; esac
    dir=$2
    if [[ ! -f "$dir/metadata.json" || ! -d "$dir/raw" || -e "$dir/raw/k6-summary.json" ]]; then
      echo "RUN_DIR không hợp lệ hoặc summary đã tồn tại; không ghi đè." >&2; exit 1
    fi
    python -c 'import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); metadata = json.loads((p / "metadata.json").read_text(encoding="utf-8-sig"))
collection = json.loads((p / "collection.json").read_text(encoding="utf-8-sig"))
if metadata.get("scenario") != "E1" or metadata.get("profile") != sys.argv[2] or metadata.get("variant") not in ("warm", "elastic") or collection.get("status") != "collecting":
    sys.exit("Profile hoặc collector không khớp; không phát tải.")' "$dir" "$1"
    exec k6 run --summary-export "$dir/raw/k6-summary.json" "./$file" ;;
  *) echo "Dùng: bash run.sh {init|inspect|collect|load|report|compare} ..."; echo "Xem README.md để chuẩn bị, apply và khôi phục." ;;
esac
