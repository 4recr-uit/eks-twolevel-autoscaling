#!/usr/bin/env python3
"""Read-only Kubernetes snapshots for E3; no queue or workload mutations."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import time


def collect(context, namespace, timeout):
    queries = {
        "pods": ["-n", namespace, "get", "pods"],
        "events": ["-n", namespace, "get", "events"],
        "hpa": ["-n", namespace, "get", "hpa"],
        "scaledobjects": ["-n", namespace, "get", "scaledobjects"],
        "nodes": ["get", "nodes"],
        "nodeclaims": ["get", "nodeclaims"],
    }
    sample = {"started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "resources": {}}
    for name, args in queries.items():
        try:
            result = subprocess.run(["kubectl", "--context", context, *args, "-o", "json"],
                                    capture_output=True, text=True, timeout=timeout, check=False)
            if result.returncode:
                sample["resources"][name] = {"error": result.stderr.strip()[:500] or "kubectl failed"}
                continue
            data = json.loads(result.stdout)
            # Store only fields needed to reconstruct lifecycle; omit Pod env and specs.
            items = []
            for item in data.get("items", []):
                meta = item.get("metadata", {})
                row = {"name": meta.get("name"), "uid": meta.get("uid"),
                       "namespace": meta.get("namespace"), "created": meta.get("creationTimestamp"),
                       "deleted": meta.get("deletionTimestamp"), "status": item.get("status", {})}
                if name == "pods":
                    row["node"] = item.get("spec", {}).get("nodeName")
                    row["owners"] = meta.get("ownerReferences", [])
                if name == "events":
                    row.update({k: item.get(k) for k in ("reason", "message", "involvedObject", "firstTimestamp", "lastTimestamp", "count", "eventTime")})
                items.append(row)
            sample["resources"][name] = {"items": items}
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            sample["resources"][name] = {"error": str(exc)[:500]}
    sample["ended_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return sample


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--context", required=True)
    p.add_argument("--namespace", required=True)
    p.add_argument("--output", type=Path, required=True, help="new JSONL file, never overwritten")
    p.add_argument("--interval", type=float, default=10)
    p.add_argument("--timeout", type=float, default=15)
    args = p.parse_args()
    if args.context.startswith("-") or args.namespace.startswith("-") or args.interval <= 0 or args.timeout <= 0:
        p.error("invalid context, namespace, interval or timeout")
    try:
        with args.output.open("x", encoding="utf-8") as out:
            print("Collecting read-only snapshots; Ctrl+C to stop.", flush=True)
            try:
                while True:
                    start = time.monotonic()
                    out.write(json.dumps(collect(args.context, args.namespace, args.timeout), ensure_ascii=False) + "\n")
                    out.flush()
                    time.sleep(max(0, args.interval - (time.monotonic() - start)))
            except KeyboardInterrupt:
                print("Stopped.")
    except FileExistsError:
        p.error("output already exists; choose a new file")


if __name__ == "__main__":
    main()
