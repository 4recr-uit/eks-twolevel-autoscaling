#!/usr/bin/env python3
"""Vẽ biểu đồ Step E4 từ report và mẫu gốc; không truy cập cluster."""

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from compare import compare

BASE = Path(__file__).resolve().parent
VARIANTS = ("q-low", "q-medium", "q-high")
LABELS = {"q-low": "q-low (5)", "q-medium": "q-medium (10)", "q-high": "q-high (20)"}
COLORS = {"q-low": "#177d8c", "q-medium": "#d97824", "q-high": "#6355a4"}
INK, MUTED, GRID = "#213348", "#5e6d7e", "#dfe6ed"
RATES = (5, 10, 15, 20, 15, 10, 5)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_run(root, variant):
    directory = root / f"E4-{variant}-step-r01"
    report = read_json(directory / "report.json")
    collection = read_json(directory / "collection.json")
    if report.get("run_id") != directory.name or report.get("variant") != variant:
        raise ValueError(f"Run ID hoặc variant không khớp: {directory}")
    if report.get("validity") != "valid" or collection.get("status") != "finished":
        raise ValueError(f"Lượt chưa valid hoặc chưa thu xong: {directory}")
    if report.get("warnings"):
        raise ValueError(f"Lượt có cảnh báo cần kiểm tra: {directory}")
    start = timestamp(report["workload_started_utc"])
    end = timestamp(report["workload_finished_utc"]) - start
    if abs(end - 420) > 3 or report["workload"].get("model_version") != 4:
        raise ValueError(f"Workload không phải Step v4 7 phút: {directory}")
    queue = []
    path = directory / "metrics/collect-sqs-samples.jsonl"
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        sample = json.loads(line)
        counts = sample["data"]["main"]["counts"]
        queue.append((timestamp(sample["observed_at_utc"]) - start,
                      counts["ApproximateNumberOfMessages"] + counts["ApproximateNumberOfMessagesNotVisible"]))
    series = {}
    for name in ("desired", "ready"):
        result = read_json(directory / f"metrics/collect-prometheus-{name}_replicas.json")
        items = result.get("data", {}).get("result", [])
        if result.get("status") != "success" or len(items) != 1:
            raise ValueError(f"Thiếu series {name}: {directory}")
        series[name] = [(float(t) - start, float(v)) for t, v in items[0]["values"]
                        if math.isfinite(float(v))]
    if not queue or not all(series.values()):
        raise ValueError(f"Thiếu mẫu timeline: {directory}")
    return {"report": report, "queue": sorted(queue), **series,
            "queue_gap": max(30, float(collection["requested_interval_seconds"]) * 3 + 10),
            "replica_gap": float(collection["prometheus_export_step_seconds"]) * 3}


def separated(points, max_gap):
    xs, ys, previous = [], [], None
    for x, y in points:
        if previous is not None and x - previous > max_gap:
            xs.append((previous + x) / 2)
            ys.append(float("nan"))
        xs.append(x)
        ys.append(y)
        previous = x
    return xs, ys


def configure():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.edgecolor": GRID, "figure.facecolor": "white", "axes.facecolor": "white",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.facecolor": "white"})


def style(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=.8)
    ax.tick_params(length=0, pad=6)


def timeline(runs):
    fig, axes = plt.subplots(2, 3, figsize=(18, 7.8), sharex=True, sharey="row")
    fig.subplots_adjust(left=.065, right=.99, top=.82, bottom=.10, hspace=.24, wspace=.13)
    handles = [Line2D([0], [0], color=INK, lw=2, marker=".", label="Queue samples"),
               Line2D([0], [0], color=INK, lw=2, label="Ready"),
               Line2D([0], [0], color=INK, lw=1.5, ls="--", label="Desired"),
               Line2D([0], [0], color=MUTED, lw=1, ls=":", label="Max replicas")]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .98), ncol=4, frameon=False)
    for col, variant in enumerate(VARIANTS):
        run, color = runs[variant], COLORS[variant]
        for row in range(2):
            ax = axes[row, col]
            style(ax)
            for i, rate in enumerate(RATES):
                if i % 2 == 0:
                    ax.axvspan(i*60, (i+1)*60, color="#e9f2f5", alpha=.72, lw=0)
                if row == 0:
                    ax.text(i*60+30, 1.03, f"{rate}/s", transform=ax.get_xaxis_transform(),
                            ha="center", va="bottom", fontsize=9, color=MUTED)
            for x in (0, 420):
                ax.axvline(x, color="#9aaab8", linestyle=":", lw=.9)
            ax.set_xlim(-60, 570)
        axes[0, col].set_title(LABELS[variant], loc="left", fontweight="bold", color=color, pad=25)
        x, y = separated(run["queue"], run["queue_gap"])
        axes[0, col].plot(x, y, color=color, marker=".", markersize=4, lw=1.8)
        for name, line in (("desired", "--"), ("ready", "-")):
            x, y = separated(run[name], run["replica_gap"])
            axes[1, col].step(x, y, where="post", color=color, ls=line,
                              lw=1.5 if name == "desired" else 2.1, alpha=.75 if name == "desired" else 1)
        axes[1, col].axhline(10, color=MUTED, ls=":", lw=1)
        axes[1, col].set_xlabel("Time since workload start (s)")
    axes[0, 0].set_ylabel("Queue depth\n(visible + in-flight)")
    axes[1, 0].set_ylabel("Worker replicas")
    axes[0, 0].set_ylim(bottom=0)
    axes[1, 0].set_ylim(0, 11)
    axes[1, 0].yaxis.set_major_locator(MaxNLocator(integer=True))
    return fig


def summary(runs):
    fig, axes = plt.subplots(1, 3, figsize=(15.8, 5.6))
    fig.subplots_adjust(left=.065, right=.985, top=.88, bottom=.16, wspace=.35)
    specs = (("P95 end-to-end latency", "Seconds", lambda r: r["latency_seconds_approx_all_statuses"]["p95"], 3),
             ("Ready pod-minutes", "Pod-minutes", lambda r: r["ready_pod_minutes_approx"], 1),
             ("Success throughput during load", "Jobs / second", lambda r: r["success_per_second_during_workload_approx"], 2))
    for ax, (title, unit, accessor, precision) in zip(axes.flat, specs):
        style(ax)
        values = [accessor(runs[v]["report"]) for v in VARIANTS]
        if any(value is None or not math.isfinite(value) for value in values):
            raise ValueError(f"Thiếu giá trị {title}")
        maximum = max(values)
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=12)
        ax.set_ylabel(unit, fontsize=10)
        for index, (variant, value) in enumerate(zip(VARIANTS, values)):
            ax.bar(index, value, width=.57, color=COLORS[variant], alpha=.88)
            ax.text(index, value + maximum*.035, f"{value:.{precision}f}", ha="center",
                    va="bottom", color=COLORS[variant], fontweight="bold")
        ax.set_xticks(range(3), ["5", "10", "20"])
        ax.set_xlabel("KEDA queueLength")
        ax.set_ylim(0, maximum*1.25 if maximum else 1)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    return fig


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=BASE.parent / "results/E4")
    parser.add_argument("--output-dir", type=Path, default=BASE / "figures")
    parser.add_argument("--overwrite", action="store_true", help="cho phép thay các hình đã có")
    args = parser.parse_args()
    try:
        runs = {variant: load_run(args.results_dir, variant) for variant in VARIANTS}
        compare([runs[variant]["report"] for variant in VARIANTS])
        targets = [args.output_dir / f"{name}.png"
                   for name in ("queue-worker-timeline", "latency-pod-minutes-throughput")]
        if not args.overwrite and any(path.exists() for path in targets):
            raise ValueError("Hình đã tồn tại; dùng --overwrite hoặc --output-dir khác")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        configure()
        for name, factory in (("queue-worker-timeline", timeline), ("latency-pod-minutes-throughput", summary)):
            fig = factory(runs)
            try:
                path = args.output_dir / f"{name}.png"
                fig.savefig(path, dpi=200, facecolor="white")
                print(path)
            finally:
                plt.close(fig)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Không thể vẽ E4: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
