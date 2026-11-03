#!/usr/bin/env python3

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = REPO_ROOT / "experiments" / "results"
TOKEN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?\Z")
KUBE_NAME = re.compile(r"[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?\Z")
QUEUE_NAME = re.compile(r"[A-Za-z0-9_-]{1,80}(?:\.fifo)?\Z")


def token(value):
    if not TOKEN.fullmatch(value):
        raise argparse.ArgumentTypeError("dùng chữ thường, số và dấu '-', tối đa 32 ký tự")
    return value


def kube_name(value):
    if not KUBE_NAME.fullmatch(value):
        raise argparse.ArgumentTypeError("tên Kubernetes không hợp lệ")
    return value


def nonempty(value):
    if not value.strip() or value.startswith("-") or any(ord(c) < 32 for c in value):
        raise argparse.ArgumentTypeError("giá trị không hợp lệ")
    return value


def queue_name(value):
    if not QUEUE_NAME.fullmatch(value) or len(value) > 80:
        raise argparse.ArgumentTypeError("chỉ nhập tên SQS queue, không nhập URL hoặc credential")
    return value


def attempt(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("lượt chạy phải là số nguyên từ 1 đến 999") from exc
    if not 1 <= number <= 999:
        raise argparse.ArgumentTypeError("lượt chạy phải là số nguyên từ 1 đến 999")
    return number


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def git_snapshot(repo_root):
    def command(*args):
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_root), *args], capture_output=True,
                encoding="utf-8", errors="replace", check=False
            )
        except OSError:
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    commit = command("rev-parse", "HEAD")
    branch = command("branch", "--show-current")
    changes = command("status", "--porcelain", "--untracked-files=normal")
    return {"commit": commit, "branch": branch or None, "dirty": None if changes is None else bool(changes)}


def init_run(args, *, repo_root=REPO_ROOT):
    run_id = f"{args.scenario}-{args.variant}-{args.profile}-r{args.attempt:02d}"
    scenario_dir = args.results_dir / args.scenario
    run_dir = scenario_dir / run_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError(f"lượt đã tồn tại, không ghi đè: {run_dir}") from exc

    metadata = {
        "schema_version": 1,
        "run_id": run_id,
        "scenario": args.scenario,
        "variant": args.variant,
        "profile": args.profile,
        "attempt": args.attempt,
        "prepared_at_utc": utc_now(),
        "started_at_utc": None,
        "ended_at_utc": None,
        "validity": "not_assessed",
        "target": {
            "kube_context": args.context,
            "namespace": args.namespace,
            "deployment": args.deployment,
            "queue_name": args.queue,
            "aws_region": args.region,
        },
        "infrastructure_repo": git_snapshot(repo_root),
    }
    for directory in ("raw", "metrics", "events", "logs"):
        (run_dir / directory).mkdir()
    with (run_dir / "metadata.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    (run_dir / "notes.md").write_text(
        "# Ghi chú lượt chạy\n\n"
        "- Bắt đầu / kết thúc (UTC): chưa ghi\n"
        "- Điều kiện đầu, cấu hình và workload thực tế: chưa ghi\n"
        "- Job chấp nhận / hoàn thành / lỗi / duplicate: chưa ghi\n"
        "- Nguồn metric, timestamp / proxy và độ phân giải: chưa ghi\n"
        "- Đánh giá hợp lệ và lý do: chưa đánh giá\n"
        "- Khôi phục và trạng thái sau lượt: chưa ghi\n",
        encoding="utf-8", newline="\n",
    )
    return run_dir


def kubectl_json(context, *args):
    command = ["kubectl", "--context", context, *args, "-o", "json"]
    try:
        result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError as exc:
        raise RuntimeError(f"không chạy được kubectl: {exc}") from exc
    if result.returncode:
        raise RuntimeError(f"kubectl {' '.join(args)} thất bại: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"kubectl {' '.join(args)} không trả JSON hợp lệ") from exc


def inspect_cluster(args):
    ns = args.namespace
    kubectl_json(args.context, "get", "namespace", ns)
    deployment = kubectl_json(args.context, "-n", ns, "get", "deployment", args.deployment)
    controllers = []
    for kind in ("hpa", "scaledobjects.keda.sh"):
        items = kubectl_json(args.context, "-n", ns, "get", kind).get("items", [])
        for item in items:
            spec = item.get("spec") or {}
            target_ref = spec.get("scaleTargetRef") or {}
            target = target_ref.get("name")
            # KEDA defaults an omitted kind to Deployment. Treat an omitted HPA
            # kind conservatively as a possible conflict rather than hide it.
            target_kind = target_ref.get("kind")
            if target == args.deployment and target_kind in (None, "Deployment"):
                controllers.append(f"{kind}/{item.get('metadata', {}).get('name', '<không rõ>')}")
    status = deployment.get("status") or {}
    return {
        "kube_context": args.context,
        "namespace": ns,
        "deployment": args.deployment,
        "desired_replicas": (deployment.get("spec") or {}).get("replicas"),
        "ready_replicas": status.get("readyReplicas", 0),
        "controllers_targeting_deployment": sorted(controllers),
    }


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="tạo hồ sơ cục bộ cho một lượt; không truy cập cluster")
    init.add_argument("--scenario", required=True, choices=[f"E{i}" for i in range(6)])
    init.add_argument("--variant", required=True, type=token, help="ví dụ fixed, hpa, keda, warm")
    init.add_argument("--profile", required=True, type=token, help="ví dụ steady, step, burst")
    init.add_argument("--attempt", required=True, type=attempt)
    init.add_argument("--context", required=True, type=nonempty)
    init.add_argument("--namespace", required=True, type=kube_name)
    init.add_argument("--deployment", required=True, type=kube_name)
    init.add_argument("--queue", required=True, type=queue_name, help="tên queue, không nhập URL hoặc credential")
    init.add_argument("--region", required=True, type=nonempty)
    init.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS, help="thư mục kết quả; mặc định experiments/results")

    inspect = sub.add_parser("inspect", help="chỉ đọc namespace, deployment và autoscaler của target")
    inspect.add_argument("--context", required=True, type=nonempty)
    inspect.add_argument("--namespace", required=True, type=kube_name)
    inspect.add_argument("--deployment", required=True, type=kube_name)
    return result


def main(argv=None):
    # Git Bash/PowerShell pipes may default to a legacy Windows code page.
    # Use UTF-8 for Vietnamese messages rather than failing on output.
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            print(f"Đã chuẩn bị hồ sơ: {init_run(args)}")
            print("Chưa chạy workload. Điền notes.md và timestamp khi thực hiện.")
        else:
            print(json.dumps(inspect_cluster(args), ensure_ascii=False, indent=2))
            print("Chỉ là kiểm tra một phần; đối chiếu autoscaler với nhánh và runbook trước khi tiếp tục.")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
