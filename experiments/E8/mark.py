#!/usr/bin/env python3
"""Record a manual fault marker locally; this tool never modifies the cluster."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--pod", required=True, help="worker Pod name observed before the manual action")
    parser.add_argument("--pod-uid", required=True, help="UID of the same Pod")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,252}", args.pod) or not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", args.pod_uid):
        parser.error("Pod name or UID invalid")
    metadata = json.loads((args.run_dir / "metadata.json").read_text(encoding="utf-8-sig"))
    collection = json.loads((args.run_dir / "collection.json").read_text(encoding="utf-8-sig"))
    if metadata.get("scenario") != "E8" or metadata.get("variant") != "fault" or collection.get("status") != "collecting":
        parser.error("fault run must be collecting")
    marker = {"marked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "pod": args.pod,
              "pod_uid": args.pod_uid, "meaning": "manual action requested after this marker; exact deletion time must be verified"}
    with (args.run_dir / "events/fault-marker.json").open("x", encoding="utf-8") as out:
        json.dump(marker, out, ensure_ascii=False, indent=2); out.write("\n")
    print("Marker saved; execute the reviewed manual action separately.")

if __name__ == "__main__": main()
