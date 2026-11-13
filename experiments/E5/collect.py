#!/usr/bin/env python3
"""Read-only E5 collector. Ctrl+C finalizes the run; it never starts workload."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import math
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request


COUNTS = (
    "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible",
    "ApproximateNumberOfMessagesDelayed",
)
ENV_ALLOWLIST = {"APP_MODE", "WORKER_CONCURRENCY", "WORKER_DB_MODE", "SQS_MAX_MESSAGES"}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def append_json(path, value):
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def load_run(directory):
    directory = directory.resolve()
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8-sig"))
    if not isinstance(metadata, dict):
        raise ValueError("metadata.json phải là JSON object")
    if metadata.get("schema_version") != 1 or metadata.get("scenario") != "E5":
        raise ValueError("Bộ thu này chỉ hỗ trợ hồ sơ E5 schema_version=1 do run.py init tạo.")
    target = metadata.get("target", {})
    if not isinstance(target, dict) or not isinstance(metadata.get("run_id"), str) or not metadata["run_id"]:
        raise ValueError("metadata thiếu run_id hoặc target hợp lệ")
    for name in ("kube_context", "namespace", "deployment", "queue_name", "aws_region"):
        value = target.get(name)
        if not isinstance(value, str) or not value or value.startswith("-") or any(ord(c) < 32 for c in value):
            raise ValueError(f"metadata.target.{name} không hợp lệ")
    for name in ("namespace", "deployment"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,252}", target[name]):
            raise ValueError(f"metadata.target.{name} không hợp lệ")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}(?:\.fifo)?", target["queue_name"]) or len(target["queue_name"]) > 80:
        raise ValueError("metadata phải chứa tên queue, không phải URL")
    for name in ("raw", "metrics", "events", "logs"):
        if not (directory / name).is_dir():
            raise ValueError(f"Thiếu thư mục {name}; kiểm tra lại init")
    if (directory / "collection.json").exists():
        raise ValueError("Lượt này đã có collection.json; tạo attempt mới, không ghi đè kết quả cũ.")
    # Reserve only files owned by this collector, leaving k6 output and notes alone.
    for folder in ("metrics", "events", "logs"):
        if any(p.name.startswith("collect-") for p in (directory / folder).iterdir()):
            raise ValueError(f"Đã có file collect-* trong {folder}; tạo attempt mới.")
    return directory, metadata


def prometheus_url(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("Dùng URL HTTP(S) không chứa credential/query, ví dụ http://127.0.0.1:9090")
    return value.rstrip("/")


class Source:
    def __init__(self, target, url, timeout):
        self.target, self.url, self.timeout = target, url, timeout
        self.queue_urls = {}

    def command(self, argv, *, raw=False):
        # Ctrl+C belongs to the collector. Let in-flight read requests finish
        # without forwarding the console signal to AWS CLI/kubectl.
        options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                   if sys.platform == "win32" else {"start_new_session": True})
        result = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace", timeout=self.timeout, **options)
        if result.returncode:
            raise RuntimeError(f"{argv[0]} thất bại: {result.stderr.strip()[:800]}")
        return result.stdout if raw else json.loads(result.stdout)

    def kube(self, *args):
        return self.command(["kubectl", "--context", self.target["kube_context"], *args, "-o", "json"])

    def aws(self, service, *args):
        return self.command(["aws", "--region", self.target["aws_region"], "--no-cli-pager", service, *args, "--output", "json"])

    def prom(self, endpoint, **params):
        uri = f"{self.url}/api/v1/{endpoint}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(uri, timeout=self.timeout) as response:
            data = json.load(response)
        if data.get("status") != "success":
            raise RuntimeError(f"Prometheus: {data.get('error', 'response không hợp lệ')}")
        return data

    def queue(self, name):
        if name not in self.queue_urls:
            self.queue_urls[name] = self.aws("sqs", "get-queue-url", "--queue-name", name)["QueueUrl"]
        data = self.aws("sqs", "get-queue-attributes", "--queue-url", self.queue_urls[name],
                        "--attribute-names", *COUNTS, "RedrivePolicy", "VisibilityTimeout")["Attributes"]
        # Missing counts are not silently treated as zero.
        return {"queue_name": name, "counts": {key: int(data[key]) for key in COUNTS},
                "visibility_timeout_seconds": int(data["VisibilityTimeout"]),
                "redrive_policy": json.loads(data["RedrivePolicy"]) if data.get("RedrivePolicy") else None}

    def worker(self):
        target = self.target
        dep = self.kube("-n", target["namespace"], "get", "deployment", target["deployment"])
        selector = dep["spec"]["selector"]
        if not selector.get("matchLabels") or selector.get("matchExpressions"):
            raise ValueError("E5 collector yêu cầu Deployment có selector matchLabels đơn giản")
        labels = ",".join(f"{k}={v}" for k, v in sorted(selector["matchLabels"].items()))
        pods = self.kube("-n", target["namespace"], "get", "pods", "-l", labels)["items"]
        spec = dep["spec"]["template"]["spec"]
        return {
            "name": dep["metadata"]["name"], "uid": dep["metadata"]["uid"],
            "generation": dep["metadata"]["generation"], "desired": dep["spec"].get("replicas", 1),
            "ready": dep.get("status", {}).get("readyReplicas", 0),
            "service_account": spec.get("serviceAccountName", "default"),
            "node_selector": spec.get("nodeSelector", {}),
            "containers": [{"name": c["name"], "image": c["image"],
                            "image_pull_policy": c.get("imagePullPolicy"), "resources": c.get("resources", {}),
                            "env": {e["name"]: e["value"] for e in c.get("env", [])
                                    if e["name"] in ENV_ALLOWLIST and "value" in e}}
                           for c in spec["containers"]],
            "pods": [{"name": p["metadata"]["name"], "uid": p["metadata"]["uid"],
                      "created_at": p["metadata"]["creationTimestamp"],
                      "deleting_at": p["metadata"].get("deletionTimestamp"),
                      "node": p["spec"].get("nodeName"), "phase": p.get("status", {}).get("phase"),
                      "conditions": p.get("status", {}).get("conditions", []),
                      "containers": [{k: c.get(k) for k in ("name", "image", "imageID", "ready", "restartCount")}
                                     for c in p.get("status", {}).get("containerStatuses", [])]}
                     for p in pods],
        }

    def controllers(self):
        result = []
        for kind in ("hpa", "scaledobjects.keda.sh"):
            for item in self.kube("-n", self.target["namespace"], "get", kind)["items"]:
                ref = item.get("spec", {}).get("scaleTargetRef", {})
                if ref.get("name") == self.target["deployment"] and ref.get("kind", "Deployment") == "Deployment":
                    result.append(f"{kind}/{item['metadata']['name']}")
        return result

    def nodes(self):
        return [{"name": n["metadata"]["name"], "uid": n["metadata"]["uid"],
                 "created_at": n["metadata"].get("creationTimestamp"),
                 "deleting_at": n["metadata"].get("deletionTimestamp"),
                 "provider_id": n.get("spec", {}).get("providerID"),
                 "labels": {k: v for k, v in n["metadata"].get("labels", {}).items()
                            if k in ("role", "node.kubernetes.io/instance-type", "topology.kubernetes.io/zone", "karpenter.sh/nodepool")},
                 "allocatable": n.get("status", {}).get("allocatable", {}),
                 "conditions": n.get("status", {}).get("conditions", [])}
                for n in self.kube("get", "nodes")["items"]]


def queries(target):
    ns, dep = json.dumps(target["namespace"]), json.dumps(target["deployment"])
    pod = json.dumps(re.escape(target["deployment"]) + "-.*")
    queue = json.dumps(target["queue_name"])
    worker = f'namespace={ns},pod=~{pod},queue={queue}'
    pod_selector = f'namespace={ns},pod=~{pod}'
    return {
        "published_jobs": f'app_sqs_messages_published_total{{namespace={ns},queue={queue}}}',
        "worker_tasks_processed_total": f'worker_tasks_processed_total{{{worker}}}',
        "worker_job_e2e_latency_seconds_bucket": f'worker_job_e2e_latency_seconds_bucket{{{worker}}}',
        "worker_cpu_counter": f'container_cpu_usage_seconds_total{{{pod_selector},container!="",container!="POD"}}',
        "worker_target_up": f'up{{{pod_selector}}}',
        "desired_replicas": f'kube_deployment_spec_replicas{{namespace={ns},deployment={dep}}}',
        "ready_replicas": f'kube_deployment_status_replicas_ready{{namespace={ns},deployment={dep}}}',
        "pending_pods": f'kube_pod_status_phase{{{pod_selector},phase="Pending"}}',
        "node_info": 'kube_node_info',
    }


def preflight(source, variant):
    expected = {
        "keda": {"hpa/e5-orders-keda-hpa", "scaledobjects.keda.sh/e5-orders-sqs"},
    }
    if variant not in ("baseline", "fault"):
        raise ValueError("Variant E5 phải là baseline hoặc fault")
    controller_variant = "keda"
    worker = source.worker()
    replicas = 1
    if worker["desired"] != replicas or worker["ready"] != replicas:
        raise ValueError(f"E5 {variant} cần {replicas} worker desired/Ready trước lượt")
    if len(worker["pods"]) != replicas or any(
            not p["containers"] or any(not c["ready"] or not c["imageID"] for c in p["containers"])
            for p in worker["pods"]):
        raise ValueError("Chờ worker Ready và có image digest trước khi thu")
    if worker.get("node_selector", {}).get("karpenter.sh/nodepool") != "e5-orders":
        raise ValueError("Worker chưa chọn NodePool e5-orders")
    controllers = source.controllers()
    if set(controllers) != expected[controller_variant]:
        raise ValueError(f"Autoscaler không khớp nhánh {variant}: {controllers}")
    ns = source.target["namespace"]
    if controller_variant == "keda":
        scaled = source.kube("-n", ns, "get", "scaledobject", "e5-orders-sqs")
        hpa = source.kube("-n", ns, "get", "hpa", "e5-orders-keda-hpa")
        owners = hpa["metadata"].get("ownerReferences", [])
        spec = scaled["spec"]
        triggers = spec.get("triggers", [])
        trigger = triggers[0] if len(triggers) == 1 else {}
        if (scaled["metadata"].get("labels", {}).get("experiments.retailstore.dev/owner") != "e5"
                or not any(o.get("uid") == scaled["metadata"]["uid"] and o.get("kind") == "ScaledObject" for o in owners)
                or spec.get("minReplicaCount") != 1 or spec.get("maxReplicaCount") != 10
                or spec.get("pollingInterval", 30) != 30
                or spec.get("cooldownPeriod", 300) != 300
                or hpa.get("spec", {}).get("minReplicas", 1) != 1
                or hpa.get("spec", {}).get("maxReplicas") != 10
                or trigger.get("type") != "aws-sqs-queue"
                or str(trigger.get("metadata", {}).get("queueLength")) != "10"
                or str(trigger.get("metadata", {}).get("scaleOnInFlight", "true")).lower() != "true"
                or str(trigger.get("metadata", {}).get("scaleOnDelayed", "false")).lower() != "false"):
            raise ValueError("ScaledObject/HPA E5 không đúng owner hoặc cấu hình min=1, max=10, queueLength=10")
        if not any(c.get("type") == "Ready" and c.get("status") == "True"
                   for c in scaled.get("status", {}).get("conditions", [])):
            raise ValueError("ScaledObject E5 chưa Ready")
    if controller_variant == "keda":
        conditions = hpa.get("status", {}).get("conditions", [])
        if not all(any(c.get("type") == name and c.get("status") == "True" for c in conditions)
                   for name in ("AbleToScale", "ScalingActive")):
            raise ValueError("HPA chưa AbleToScale/ScalingActive; kiểm tra metric và chờ đồng bộ")
    queue = source.queue(source.target["queue_name"])
    # Verify the queue feeding the worker (and KEDA's queueURLFromEnv) is the
    # same queue being sampled. Do not persist the queue URL in the output.
    deployment = source.kube("-n", ns, "get", "deployment", source.target["deployment"])
    containers = deployment["spec"]["template"]["spec"]["containers"]
    worker_containers = [c for c in containers if c.get("name") == source.target["deployment"]]
    if len(worker_containers) != 1:
        raise ValueError("Không xác định được container worker")
    env = {e["name"]: e.get("value") for e in worker_containers[0].get("env", [])}
    if env.get("SQS_QUEUE_URL") != source.queue_urls[source.target["queue_name"]]:
        raise ValueError("SQS_QUEUE_URL của worker không khớp queue đang thu")
    if controller_variant == "keda" and (trigger.get("metadata", {}).get("queueURLFromEnv") != "SQS_QUEUE_URL"
                              or trigger.get("metadata", {}).get("queueURL")
                              or trigger.get("metadata", {}).get("awsRegion") != source.target["aws_region"]):
        raise ValueError("KEDA không dùng SQS_QUEUE_URL/region của worker")
    if any(queue["counts"].values()):
        raise ValueError(f"Queue chưa rỗng: {queue['counts']}")
    dlq = None
    if queue["redrive_policy"]:
        name = queue["redrive_policy"]["deadLetterTargetArn"].rsplit(":", 1)[-1]
        dlq = source.queue(name)
        if any(dlq["counts"].values()):
            raise ValueError("DLQ chưa rỗng; đối chiếu trước lượt mới")
    up = source.prom("query", query=queries(source.target)["worker_target_up"])
    values = up.get("data", {}).get("result", [])
    if len(values) < replicas or any(float(item["value"][1]) != 1 for item in values):
        raise ValueError("Prometheus chưa có đủ target worker UP")
    return {"observed_at_utc": utc_now(), "variant": variant, "worker": worker, "nodes": source.nodes(),
            "queue": queue, "dlq": dlq, "controllers": controllers}


def matrix_stats(data):
    series = data.get("data", {}).get("result", [])
    points = [point for item in series for point in item.get("values", [])]
    return {"series": len(series), "points": len(points),
            "nonfinite_points": sum(not math.isfinite(float(point[1])) for point in points),
            "warnings": data.get("warnings", [])}


class Collector:
    def __init__(self, directory, metadata, source, args):
        self.directory, self.metadata, self.source, self.args = directory, metadata, source, args
        self.stop = threading.Event()
        self.errors = []
        self.warnings = set()
        self.sample_counts = {"sqs": 0, "worker": 0, "topology": 0}
        self.exports = {}
        self.started = None
        self.before = None

    def error(self, source, exc):
        item = {"observed_at_utc": utc_now(), "source": source, "error": str(exc)[:1000]}
        self.errors.append(item)
        append_json(self.directory / "logs/collect-errors.jsonl", item)
        print(f"Cảnh báo {source}: {item['error']}", flush=True)

    def observe_worker(self, worker):
        if self.before:
            original = self.before["worker"]
            if worker["uid"] != original["uid"] or worker["containers"] != original["containers"]:
                self.warnings.add("worker_configuration_changed")
            baseline_ids = {c.get("imageID") for p in original["pods"] for c in p["containers"]}
            for pod in worker["pods"]:
                for container in pod["containers"]:
                    if container.get("imageID") and container["imageID"] not in baseline_ids:
                        self.warnings.add("worker_image_changed")
                    if container.get("restartCount", 0):
                        self.warnings.add("worker_restarted")

    def sample(self, pool):
        def sqs():
            data = {"main": self.source.queue(self.source.target["queue_name"])}
            if self.before["dlq"]:
                data["dlq"] = self.source.queue(self.before["dlq"]["queue_name"])
            return data
        def topology():
            nodes = self.source.nodes()
            claims = self.source.kube("get", "nodeclaims").get("items", [])
            events = self.source.kube("-n", self.source.target["namespace"], "get", "events").get("items", [])
            return {"nodes": nodes, "nodeclaims": [{"name": x.get("metadata", {}).get("name"),
                    "uid": x.get("metadata", {}).get("uid"), "created": x.get("metadata", {}).get("creationTimestamp"),
                    "labels": x.get("metadata", {}).get("labels", {}), "status": x.get("status", {})} for x in claims],
                    "events": [{k: x.get(k) for k in ("reason", "message", "involvedObject", "firstTimestamp", "lastTimestamp", "eventTime", "count")}
                               for x in events if x.get("reason") == "FailedScheduling"]}
        tasks = {name: (utc_now(), pool.submit(function)) for name, function in
                 (("sqs", sqs), ("worker", self.source.worker), ("topology", topology))}
        for name, (started, future) in tasks.items():
            try:
                data = future.result()
                ended = utc_now()
                if name == "worker":
                    self.observe_worker(data)
                    data = {"desired": data["desired"], "ready": data["ready"],
                            "pods": [{"name": p["name"], "uid": p["uid"], "node": p.get("node"),
                                      "containers": p["containers"], "phase": p["phase"], "conditions": p["conditions"],
                                      "created_at": p["created_at"]} for p in data["pods"]]}
                if name == "sqs" and data.get("dlq") and any(data["dlq"]["counts"].values()):
                    self.warnings.add("dlq_messages_observed")
                if name == "sqs":
                    counts = data["main"]["counts"]
                    print(f"{ended} SQS visible={counts[COUNTS[0]]} in-flight={counts[COUNTS[1]]} delayed={counts[COUNTS[2]]}", flush=True)
                path = self.directory / (f"events/collect-{name}-samples.jsonl" if name in ("worker", "topology") else f"metrics/collect-{name}-samples.jsonl")
                append_json(path, {"request_started_at_utc": started, "observed_at_utc": ended, "data": data})
                self.sample_counts[name] += 1
            except Exception as exc:
                self.error(name, exc)

    def finalize(self, ended):
        try:
            after = {"worker": self.source.worker(), "nodes": self.source.nodes(), "controllers": self.source.controllers()}
            self.observe_worker(after["worker"])
            if after["nodes"] != self.before["nodes"]:
                before_nodes = {(n["name"], n["uid"]) for n in self.before["nodes"]}
                if before_nodes != {(n["name"], n["uid"]) for n in after["nodes"]}:
                    self.warnings.add("node_set_changed")
            if set(after["controllers"]) != set(self.before["controllers"]):
                self.warnings.add("autoscaler_changed")
            write_json(self.directory / "events/collect-after.json", after)
        except Exception as exc:
            self.error("snapshot_after", exc)
        try:
            final_queue = {"main": self.source.queue(self.source.target["queue_name"])}
            if self.before["dlq"]:
                final_queue["dlq"] = self.source.queue(self.before["dlq"]["queue_name"])
            write_json(self.directory / "metrics/collect-sqs-after.json", {"observed_at_utc": utc_now(), "data": final_queue})
            if any(final_queue["main"]["counts"].values()):
                self.warnings.add("main_queue_not_empty_at_end")
            if final_queue.get("dlq") and any(final_queue["dlq"]["counts"].values()):
                self.warnings.add("dlq_messages_at_end")
        except Exception as exc:
            self.error("sqs_after", exc)
        for name, query in queries(self.source.target).items():
            try:
                data = self.source.prom("query_range", query=query, start=self.started, end=ended, step=self.args.step)
                write_json(self.directory / f"metrics/collect-prometheus-{name}.json", data)
                self.exports[name] = {"query": query, **matrix_stats(data)}
                if not self.exports[name]["points"] or self.exports[name]["nonfinite_points"] or data.get("warnings"):
                    self.warnings.add(f"prometheus_review:{name}")
            except Exception as exc:
                self.error(f"prometheus_export:{name}", exc)

    def run(self, before):
        self.before = before
        self.started = utc_now()
        record = {"schema_version": 1, "run_id": self.metadata["run_id"], "status": "collecting",
                  "started_at_utc": self.started, "ended_at_utc": None,
                  "prometheus_url": self.source.url, "requested_interval_seconds": self.args.interval,
                  "prometheus_export_step_seconds": self.args.step,
                  "validity": "not_assessed", "scope": "E5; KEDA + Karpenter worker disruption, validity chưa được đánh giá"}
        marker = self.directory / "collection.json"
        write_json(marker, record)  # Exclusive creation also prevents two collectors claiming a run.
        previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda *_: self.stop.set())
        try:
            write_json(self.directory / "events/collect-before.json", before)
            self.observe_worker(before["worker"])
            print(f"ĐANG THU: {self.metadata['run_id']} (Ctrl+C sau khi workload dừng và queue drain)", flush=True)
            deadline = time.monotonic() + self.args.duration if self.args.duration else None
            with ThreadPoolExecutor(max_workers=3) as pool:
                while not self.stop.is_set():
                    tick = time.monotonic()
                    self.sample(pool)
                    if deadline and time.monotonic() >= deadline:
                        break
                    wait = max(0, self.args.interval - (time.monotonic() - tick))
                    if deadline:
                        wait = min(wait, max(0, deadline - time.monotonic()))
                    self.stop.wait(wait)
                print("Đang kết thúc: lấy mẫu cuối và xuất Prometheus. Giữ terminal mở...", flush=True)
                # Preserve a short tail so the final worker scrape has time to arrive.
                if self.args.tail_seconds:
                    time.sleep(self.args.tail_seconds)
                self.sample(pool)
            ended = utc_now()
            self.finalize(ended)
            record.update(status="partial" if self.errors else "finished", ended_at_utc=ended,
                          sample_counts=self.sample_counts, warnings=sorted(self.warnings), errors=self.errors,
                          prometheus_exports=self.exports,
                          k6_summary_present=(self.directory / "raw/k6-summary.json").is_file())
            if not record["k6_summary_present"]:
                record["warnings"].append("k6_summary_not_found_at_raw/k6-summary.json")
            summary = [f"# Thu dữ liệu {record['run_id']}", "", f"- Trạng thái thu: {record['status']}",
                       f"- Cửa sổ thu (UTC): {self.started} → {ended}",
                       f"- Số mẫu thành công: {json.dumps(self.sample_counts)}", "",
                       "## Cần kiểm tra", "",
                       *[f"- {warning}" for warning in record["warnings"]],
                       *[f"- Lỗi {item['source']}: {item['error']}" for item in self.errors], "",
                       "Chưa đánh giá tính hợp lệ. Đối chiếu timestamp k6, queue, counters và replica;",
                       "kiểm tra drain, errors, dropped iterations và node trước khi so sánh E5.",
                       "Histogram E2E gồm cả error/duplicate; SQS là xấp xỉ, counters không đối soát job ID."]
            with (self.directory / "collection-summary.md").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write("\n".join(summary) + "\n")
            # Publish the finished marker only after all outputs were written.
            # metadata.json and the user's validity assessment remain untouched.
            temp = marker.with_suffix(".tmp")
            write_json(temp, record)
            temp.replace(marker)
            print(f"Đã lưu: {self.directory}\nTrạng thái thu: {record['status']}; cảnh báo: {len(record['warnings'])}. Chưa đánh giá tính hợp lệ của thí nghiệm.", flush=True)
            return 2 if self.errors else 0
        except Exception:
            # collection.json remains 'collecting' if finalization failed: never claim success.
            raise
        finally:
            signal.signal(signal.SIGINT, previous)


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("phải là số dương hữu hạn")
    return number


def main(argv=None):
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="thư mục lượt do run.py init tạo")
    parser.add_argument("--prometheus-url", type=prometheus_url, default="http://127.0.0.1:9090")
    parser.add_argument("--interval", type=positive, default=5, help="chu kỳ yêu cầu lấy mẫu; thời gian thực lưu trong JSONL")
    parser.add_argument("--step", type=positive, default=5, help="bước query_range; không tăng độ phân giải scrape gốc")
    parser.add_argument("--request-timeout", type=positive, default=20)
    parser.add_argument("--duration", type=positive, help="tự dừng sau khoảng thời gian này, dùng cho smoke test")
    parser.add_argument("--tail-seconds", type=int, default=10, choices=range(0, 61), metavar="0..60")
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra trước lượt, không tạo file")
    args = parser.parse_args(argv)
    try:
        directory, metadata = load_run(args.run_dir)
        source = Source(metadata["target"], args.prometheus_url, args.request_timeout)
        print("Đang kiểm tra worker, queue/DLQ và Prometheus...", flush=True)
        before = preflight(source, metadata.get("variant"))
        if args.check:
            print("Kiểm tra nguồn thu E5 đạt. Chưa thu dữ liệu hay chạy workload.")
            return 0
        return Collector(directory, metadata, source, args).run(before)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Đã hủy trong bước kiểm tra, chưa bắt đầu thu.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
