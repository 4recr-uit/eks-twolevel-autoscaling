#!/usr/bin/env python3
"""So sánh các report E8 đã được người chạy kiểm tra; chỉ đọc file."""

import argparse
import json
import math
from pathlib import Path
import statistics
import sys


def cell(values, total):
    values = sorted(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))
    if not values:
        return f"N/A (0/{total})"
    return f"{statistics.median(values):.2f} [{values[0]:.2f}–{values[-1]:.2f}] ({len(values)}/{total})"


def compare(reports):
    if not reports:
        raise ValueError("Cần ít nhất một report")
    reference = reports[0]
    keys = ("profile", "workload", "configuration", "resource_window_before_workload_seconds", "resource_window_after_workload_seconds")
    for item in reports:
        if item.get("variant") not in ("baseline", "fault"):
            raise ValueError("Variant trong report không hợp lệ")
        if any(item.get(key) != reference.get(key) for key in keys):
            raise ValueError("Các report phải cùng profile, workload, cấu hình worker/queue và cửa sổ quan sát")
    ids = [item["run_id"] for item in reports]
    if len(ids) != len(set(ids)):
        raise ValueError("Run ID bị lặp")
    lines = [f"# So sánh E8 — {reference['profile']}", "",
             "Trung vị [min–max] (số lượt có dữ liệu / số lượt); người chạy cần kiểm tra tính hợp lệ.", "",
             "| Nhánh | Lượt | Accepted | Success đến drain | Throughput trong tải (task/s) | p95 E2E (s) | Peak backlog | Drain (s) | Ready Pod-minutes | Worker Node-minutes |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for variant in ("baseline", "fault"):
        group = [x for x in reports if x["variant"] == variant]
        if not group:
            continue
        n = len(group)
        cols = [cell([x.get("accepted_jobs") for x in group], n),
                cell([(x.get("completed_by_status_through_drain_approx") or {}).get("success") for x in group], n),
                cell([x.get("success_per_second_during_workload_approx") for x in group], n),
                cell([(x.get("latency_seconds_approx_all_statuses") or {}).get("p95") for x in group], n),
                cell([x.get("peak_visible_plus_inflight_approx") for x in group], n),
                cell([x.get("drain_confirmation_seconds_approx") for x in group], n),
                cell([x.get("ready_pod_minutes_approx") for x in group], n),
                cell([x.get("worker_node_minutes_approx") for x in group], n)]
        lines.append(f"| {variant} | {n} | " + " | ".join(cols) + " |")
    lines.extend(["", "Các metric là ước lượng; success và latency không thay thế đối soát job ID."
                  " Kiểm tra cùng image, node, worker và điều kiện thí nghiệm trước khi kết luận.", ""])
    for item in reports:
        warnings = item.get("warnings") or []
        lines.append(f"- {item['run_id']}: " + (", ".join(warnings) if warnings else "không có cảnh báo tự động") +
                     f"; validity={item.get('validity', 'not_assessed')}")
    return "\n".join(lines) + "\n"


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="đường dẫn report.json của các lượt cùng profile")
    args = parser.parse_args()
    try:
        reports = [json.loads(path.read_text(encoding="utf-8-sig")) for path in args.reports]
        print(compare(reports), end="")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Không so sánh được: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
