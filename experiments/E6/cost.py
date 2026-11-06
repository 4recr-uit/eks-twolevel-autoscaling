#!/usr/bin/env python3
"""Ước tính chi phí compute từ giá và thời gian do người dùng cung cấp; không gọi AWS."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import sys


def required_text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"Thiếu {key}")
    return value.strip()


def number(obj, key, *, positive=False):
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value): raise ValueError(f"{key} phải là số hữu hạn")
    if value < 0 or (positive and value == 0): raise ValueError(f"{key} phải dương" if positive else f"{key} phải không âm")
    return float(value)


def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None: raise ValueError("timestamp cần timezone")
    return result


def calculate(data):
    fields = ("run_id", "configuration", "workload", "region", "currency", "price_date", "price_source", "source_run", "success_count_method")
    result = {name: required_text(data, name) for name in fields}
    start = timestamp(required_text(data, "window_start")); end = timestamp(required_text(data, "window_end"))
    window = (end-start).total_seconds()
    if window <= 0: raise ValueError("window_end phải sau window_start")
    processed = number(data, "processed_success", positive=True)
    entries = data.get("instances")
    if not isinstance(entries, list) or not entries: raise ValueError("instances cần ít nhất một nhóm instance")
    total = idle_total = 0.0; idle_known = True; groups = []
    for row in entries:
        if not isinstance(row, dict): raise ValueError("instances phải chứa object")
        instance_type = required_text(row, "instance_type"); capacity_type = required_text(row, "capacity_type")
        seconds = number(row, "node_seconds"); price = number(row, "hourly_price")
        value = seconds / 3600 * price; total += value
        idle = row.get("idle_node_seconds")
        if idle is None: idle_known = False; idle_cost = None
        else:
            idle = number(row, "idle_node_seconds")
            if idle > seconds: raise ValueError("idle_node_seconds không thể lớn hơn node_seconds")
            idle_cost = idle / 3600 * price; idle_total += idle_cost
        groups.append({"instance_type": instance_type, "capacity_type": capacity_type, "node_seconds": seconds,
                       "hourly_price": price, "compute_cost": value, "idle_cost": idle_cost})
    result.update(window_start=start.isoformat(), window_end=end.isoformat(), window_seconds=window,
                  processed_success=processed, groups=groups, compute_cost=total,
                  idle_cost=idle_total if idle_known else None, cost_per_1000=total/processed*1000,
                  limitations="Ước tính instance compute từ giá và node-seconds đã nhập; không phải hóa đơn AWS. Idle là thành phần của compute_cost, không cộng hai lần. Không gồm EKS, NAT, RDS hoặc các chi phí khác.")
    return result


def compare(results, baseline_id=None):
    if not results: raise ValueError("Cần ít nhất một kết quả")
    ids = [x["run_id"] for x in results]
    if len(ids) != len(set(ids)): raise ValueError("run_id bị trùng")
    first = results[0]
    for x in results[1:]:
        if any(x[k] != first[k] for k in ("workload", "window_seconds", "region", "currency")):
            raise ValueError("Chỉ so sánh cùng workload, độ dài cửa sổ, region và currency")
    if baseline_id is not None and baseline_id not in ids: raise ValueError("Không tìm thấy baseline")
    base = next((x for x in results if x["run_id"] == baseline_id), None)
    for x in results:
        x["saving_percent_per_1000_vs_baseline"] = (100*(base["cost_per_1000"]-x["cost_per_1000"])/base["cost_per_1000"] if base and base["cost_per_1000"] > 0 else None)
    return results


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="JSON do người chạy điền từ dữ liệu đo và giá")
    parser.add_argument("--baseline", help="run_id làm mốc so cost/1000")
    parser.add_argument("--output", type=Path, help="file mới; không ghi đè")
    args = parser.parse_args()
    try:
        data = compare([calculate(json.loads(p.read_text(encoding="utf-8-sig"))) for p in args.inputs], args.baseline)
        text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as f: f.write(text)
        else: print(text, end="")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc: parser.exit(1, f"Không tính được: {exc}\n")

if __name__ == "__main__": main()
