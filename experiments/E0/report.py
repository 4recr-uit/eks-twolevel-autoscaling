#!/usr/bin/env python3
"""Summarize an explicitly selected E0 measurement window without changing source data."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import sys


def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("Timestamp phải bao gồm múi giờ, ví dụ 2026-11-05T03:40:20Z")
    return result.timestamp()


def matrix(directory, name):
    path = directory / "metrics" / f"collect-prometheus-{name}.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("status") != "success":
        return []
    return data.get("data", {}).get("result", [])


def rates(series, start, end, status=None):
    """Counter rates use each series' observed interval and handle counter resets."""
    values = []
    for item in series:
        if status is not None and item.get("metric", {}).get("status") != status:
            continue
        samples = sorted((float(t), float(v)) for t, v in item.get("values", [])
                         if start <= float(t) <= end and math.isfinite(float(v)))
        if len(samples) < 2 or samples[-1][0] <= samples[0][0]:
            continue
        delta = sum(b if b < a else b - a for (_, a), (_, b) in zip(samples, samples[1:]))
        values.append(delta / (samples[-1][0] - samples[0][0]))
    return round(sum(values), 3) if values else None


def summarize(directory, start, end):
    if end <= start:
        raise ValueError("Cửa sổ phải có thời điểm kết thúc sau bắt đầu")
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8-sig"))
    collection = json.loads((directory / "collection.json").read_text(encoding="utf-8-sig"))
    if metadata.get("scenario") != "E0" or collection.get("status") not in ("finished", "partial"):
        raise ValueError("Cần một lượt E0 với collection đã kết thúc")
    if start < timestamp(collection["started_at_utc"]) or end > timestamp(collection["ended_at_utc"]):
        raise ValueError("Cửa sổ nằm ngoài khoảng thu dữ liệu")
    success = rates(matrix(directory, "worker_tasks_processed_total"), start, end, "success")
    published = rates(matrix(directory, "published_jobs"), start, end)
    cpu = rates(matrix(directory, "worker_cpu_counter"), start, end)
    queue = []
    samples = directory / "metrics/collect-sqs-samples.jsonl"
    if samples.exists():
        for line in samples.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            sample = json.loads(line)
            if start <= timestamp(sample["observed_at_utc"]) <= end:
                counts = sample["data"]["main"]["counts"]
                queue.append(counts["ApproximateNumberOfMessages"])
    # Capture only completed-success records. Logs may omit terminated pods/restarts.
    jobs = []
    for path in sorted((directory / "logs").glob("collect-*.log")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "{" not in line:
                continue
            try:
                event = json.loads(line[line.index("{"):])
                completed = float(event.get("completedAt", 0)) / 1000
                if event.get("status") == "success" and start <= completed <= end and event.get("e2eMs") is not None:
                    jobs.append((event.get("jobId"), float(event["e2eMs"]) / 1000))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    durations = sorted(value for _, value in jobs)
    p95 = durations[math.ceil(.95 * len(durations)) - 1] if durations else None
    ids = [job_id for job_id, _ in jobs if job_id]
    warnings = list(collection.get("warnings") or [])
    if collection.get("status") != "finished":
        warnings.append("collection_partial")
    for name, value in (("success_rate_missing", success), ("published_rate_missing", published),
                        ("cpu_rate_missing", cpu), ("sqs_samples_missing", max(queue) if queue else None),
                        ("latency_logs_missing", p95)):
        if value is None:
            warnings.append(name)
    if len(ids) != len(set(ids)):
        warnings.append("duplicate_job_ids_in_logs")
    return {"run_id": metadata.get("run_id"), "window_start_utc": dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat(),
            "window_end_utc": dt.datetime.fromtimestamp(end, dt.timezone.utc).isoformat(),
            "published_tasks_per_second_approx": published, "success_tasks_per_second_approx": success,
            "worker_cpu_millicores_approx": round(cpu * 1000, 1) if cpu is not None else None,
            "peak_visible_messages_approx": max(queue) if queue else None,
            "p95_success_e2e_seconds_from_logs": p95, "success_log_records": len(jobs),
            "warnings": sorted(set(warnings)), "validity": "not_assessed",
            "notes": "Chọn cửa sổ ổn định thủ công; log/counter/SQS có thể thiếu mẫu và không chứng minh μ độc lập."}


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--start", required=True, help="Đầu cửa sổ UTC ISO 8601")
    parser.add_argument("--end", required=True, help="Cuối cửa sổ UTC ISO 8601")
    parser.add_argument("--output", type=Path, help="File mới; mặc định RUN_DIR/e0-report.json")
    args = parser.parse_args()
    try:
        result = summarize(args.run_dir, timestamp(args.start), timestamp(args.end))
        output = args.output or args.run_dir / "e0-report.json"
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(f"Đã tạo {output}; kiểm tra warnings và tính hợp lệ.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Không lập được báo cáo: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
