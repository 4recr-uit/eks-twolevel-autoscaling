"""Read and validate E1 results without changing the original data."""

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path


VARIANTS = ("warm", "elastic")
PROFILES = ("step", "burst")
STAGES = {
    "step": ((60, 5), (60, 10), (60, 15), (60, 20), (60, 15), (60, 10), (60, 5)),
    "burst": ((60, 5), (30, 40), (60, 5)),
}
EXPECTED_MODEL = {"step": 4, "burst": 3}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Không đọc được {path}: {exc}") from exc


def read_jsonl(path):
    try:
        with path.open(encoding="utf-8-sig") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Không đọc được {path}: {exc}") from exc


def utc_seconds(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def points(rows, start, get_value):
    result = sorted((utc_seconds(row["observed_at_utc"]) - start, get_value(row["data"]))
                    for row in rows)
    if not result:
        raise ValueError("Không có mẫu theo thời gian")
    return result


def preceding(series, when, maximum_age=30):
    candidates = [point for point in series if point[0] <= when]
    if not candidates or when - candidates[-1][0] > maximum_age:
        raise ValueError("Thiếu mẫu gần thời điểm bắt đầu workload")
    return candidates[-1][1]


@dataclass
class Run:
    run_id: str
    profile: str
    variant: str
    attempt: int
    report: dict
    metadata: dict
    queue: list
    desired: list
    ready: list
    nodes: list
    seconds: float
    max_gap: float


def load_run(root, profile, variant, attempt, config=1):
    minimums = {1: 1, 2: 3, 3: 5}
    if type(config) is not int or config not in minimums:
        raise ValueError("Config E1 phải là 1, 2 hoặc 3")
    prefix = "E1" if config == 1 else f"E1-config{config}"
    run_id = f"{prefix}-{variant}-{profile}-r{attempt:02d}"
    directory = root / run_id
    report = read_json(directory / "report.json")
    metadata = read_json(directory / "metadata.json")
    collection = read_json(directory / "collection.json")
    if (report.get("run_id") != run_id or metadata.get("run_id") != run_id
            or report.get("profile") != profile or report.get("variant") != variant
            or metadata.get("profile") != profile or metadata.get("variant") != variant
            or metadata.get("attempt") != attempt or metadata.get("scenario") != "E1"):
        raise ValueError(f"{run_id}: metadata và report không khớp")
    if (metadata.get("config", 1) != config or report.get("config", 1) != config
            or metadata.get("min_workers", 1) != minimums[config]
            or report.get("min_workers", 1) != minimums[config]):
        raise ValueError(f"{run_id}: config hoặc số worker không khớp")
    if collection.get("status") != "finished" or collection.get("errors"):
        raise ValueError(f"{run_id}: collector chưa hoàn thành hoặc có lỗi")
    workload = report["workload"]
    if (workload.get("model_version") != EXPECTED_MODEL[profile]
            or workload.get("low_request_per_second") != 5
            or workload.get("high_request_per_second") != (20 if profile == "step" else 40)):
        raise ValueError(f"{run_id}: workload không khớp profile được hỗ trợ")
    for key in ("peak_visible_plus_inflight_approx", "worker_node_minutes_approx"):
        if not isinstance(report.get(key), (int, float)) or not math.isfinite(report[key]):
            raise ValueError(f"{run_id}: thiếu {key}")
    p95 = report.get("latency_seconds_approx_all_statuses", {}).get("p95")
    if not isinstance(p95, (int, float)) or not math.isfinite(p95):
        raise ValueError(f"{run_id}: thiếu p95")

    start = utc_seconds(report["workload_started_utc"])
    seconds = utc_seconds(report["workload_finished_utc"]) - start
    if not (sum(length for length, _ in STAGES[profile]) - 5 <= seconds
            <= sum(length for length, _ in STAGES[profile]) + 10):
        raise ValueError(f"{run_id}: thời lượng workload không khớp profile")
    queue_samples = read_jsonl(directory / "metrics/collect-sqs-samples.jsonl")
    queue = points(queue_samples, start,
                   lambda d: d["main"]["counts"]["ApproximateNumberOfMessages"]
                   + d["main"]["counts"]["ApproximateNumberOfMessagesNotVisible"])
    queue_baseline = points(queue_samples, start,
                            lambda d: sum(d["main"]["counts"].values())
                            + sum(d["dlq"]["counts"].values()))
    workers = read_jsonl(directory / "events/collect-worker-samples.jsonl")
    desired = points(workers, start, lambda d: d["desired"])
    ready = points(workers, start, lambda d: d["ready"])
    worker_nodes = points(workers, start, lambda d: frozenset(p.get("node") for p in d["pods"] if p.get("node")))
    topology = read_jsonl(directory / "events/collect-topology-samples.jsonl")
    nodes = points(topology, start,
                   lambda d: sum(n.get("labels", {}).get("karpenter.sh/nodepool") == "e1-orders"
                                 for n in d["nodes"]))
    ready_nodes = points(topology, start,
                         lambda d: sum(n.get("labels", {}).get("karpenter.sh/nodepool") == "e1-orders"
                                       and any(c.get("type") == "Ready" and c.get("status") == "True"
                                               for c in n.get("conditions", [])) for n in d["nodes"]))
    node_names = points(topology, start,
                        lambda d: frozenset(n["name"] for n in d["nodes"]
                                            if n.get("labels", {}).get("karpenter.sh/nodepool") == "e1-orders"))
    initial_count = preceding(nodes, 0)
    if (not initial_count or preceding(ready_nodes, 0) != initial_count
            or preceding(ready, 0) != minimums[config] or preceding(desired, 0) != minimums[config]):
        raise ValueError(f"{run_id}: điều kiện đầu không đúng: cần {minimums[config]} worker Ready và node E1 Ready")
    if variant == "warm" and initial_count != 4:
        raise ValueError(f"{run_id}: warm cần 4 node E1 ở đầu lượt")
    if variant == "elastic" and preceding(node_names, 0) != preceding(worker_nodes, 0):
        raise ValueError(f"{run_id}: elastic có node E1 không chạy worker hoặc worker ngoài E1")
    if preceding(queue_baseline, 0) != 0:
        raise ValueError(f"{run_id}: queue chính hoặc DLQ đầu lượt chưa bằng 0")
    interval = float(collection.get("requested_interval_seconds", 5))
    return Run(run_id, profile, variant, attempt, report, metadata, queue, desired, ready,
               nodes, seconds, max(30.0, interval * 3 + 10))


def load_profile(root, profile, attempts, config=1):
    runs = [load_run(root, profile, variant, attempt, config)
            for variant in VARIANTS for attempt in attempts]
    reference = runs[0].report
    keys = ("workload", "configuration", "resource_window_before_workload_seconds",
            "resource_window_after_workload_seconds")
    for run in runs[1:]:
        if any(run.report.get(key) != reference.get(key) for key in keys):
            raise ValueError(f"{run.run_id}: workload, worker hoặc cửa sổ không khớp các lượt cùng profile")
    if (reference.get("resource_window_before_workload_seconds") != 60
            or reference.get("resource_window_after_workload_seconds") != 60):
        raise ValueError(f"{profile}: script hiện yêu cầu cửa sổ report trước/sau tải đều 60 giây")
    return runs
