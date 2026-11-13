#!/usr/bin/env python3
"""Summarize sampled Pod recovery after a manually recorded fault marker."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys


def ts(value): return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def analyze(marker, samples):
    start = ts(marker["marked_at_utc"]); uid = marker["pod_uid"]
    ordered = sorted(samples, key=lambda x: ts(x["observed_at_utc"]))
    before = any(ts(x["observed_at_utc"]) <= start and any(p.get("uid") == uid for p in x["data"]["pods"]) for x in ordered)
    absent = next((ts(x["observed_at_utc"]) for x in ordered if ts(x["observed_at_utc"]) > start
                   and all(p.get("uid") != uid for p in x["data"]["pods"])), None) if before else None
    candidates = []
    for x in ordered:
        observed = ts(x["observed_at_utc"])
        if observed < start: continue
        for p in x["data"]["pods"]:
            containers = p.get("containers", [])
            if (p.get("uid") != uid and p.get("created_at") and ts(p["created_at"]) >= start
                and p.get("phase") == "Running" and containers and all(c.get("ready") for c in containers)):
                candidates.append((observed, p.get("name"), p.get("uid")))
    first = min(candidates) if candidates else None
    return {"marker": marker, "target_observed_before_marker": before,
            "first_observed_target_absent_seconds": round(absent-start, 2) if absent else None,
            "first_observed_new_ready_seconds": round(first[0]-start, 2) if first else None,
            "candidate_new_pod": {"name": first[1], "uid": first[2]} if first else None,
            "limitations": "Sampling bounds times; a newly Ready Pod can result from scaling, not necessarily replace the target. Verify UID, events and desired count; marker precedes the manual action."}


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(); directory = args.run_dir
    marker = json.loads((directory / "events/fault-marker.json").read_text(encoding="utf-8-sig"))
    samples = [json.loads(line) for line in (directory / "events/collect-worker-samples.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(analyze(marker, samples), ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
