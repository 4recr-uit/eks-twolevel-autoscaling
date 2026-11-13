#!/usr/bin/env python3
"""Vẽ timeline E2 theo bố cục biểu đồ E1 từ dữ liệu đã thu."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator


INK = "#213348"
MUTED = "#5e6d7e"
GRID = "#dfe6ed"
QUEUE = "#d97824"
READY = "#177d8c"
DESIRED = "#72879b"
NODE = "#5961a5"
EVENT = "#9a6c31"
E2_DIR = Path(__file__).resolve().parent.parent


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as source:
        return json.load(source)


def timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def read_series(path: Path, start: float, value_fn) -> list[tuple[float, object]]:
    points = []
    with path.open(encoding="utf-8-sig") as source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                points.append((timestamp(row["observed_at_utc"]) - start, value_fn(row["data"])))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"{path}, dòng {number}: {error}") from error
    if not points:
        raise ValueError(f"Không có mẫu trong {path}")
    return sorted(points, key=lambda point: point[0])


def load_run(directory: Path) -> dict:
    report = read_json(directory / "report.json")
    timeline = read_json(directory / "timeline.json")
    metadata = read_json(directory / "metadata.json")
    collection = read_json(directory / "collection.json")
    if not (report["run_id"] == timeline["run_id"] == metadata["run_id"]):
        raise ValueError("run_id trong report, timeline và metadata không khớp")
    if metadata.get("scenario") != "E2" or report.get("profile") != "burst":
        raise ValueError("Script chỉ hỗ trợ lượt E2 Burst")
    if collection.get("status") != "finished" or collection.get("errors"):
        raise ValueError("Collector chưa kết thúc hoặc có lỗi thu")
    workload = report["workload"]
    if workload.get("model_version") != 5 or workload.get("high_phase_duration_seconds") != 90:
        raise ValueError("Script hiện hỗ trợ Burst E2 model v5, pha cao 90 giây")

    marks = timeline["timeline_utc"]
    start = timestamp(marks["T0"])
    stop = timestamp(marks["T6"]) - start
    high = timestamp(timeline["high_rate_started_utc"]) - start
    high_end = high + workload["high_phase_duration_seconds"]
    if not 0 < high < high_end < stop:
        raise ValueError("Mốc workload không khớp thứ tự Burst model v5")
    selector = report["configuration"]["node_selector"]
    if not selector:
        raise ValueError("Thiếu node selector của NodePool E2")

    queue = read_series(
        directory / "metrics/collect-sqs-samples.jsonl", start,
        lambda data: data["main"]["counts"]["ApproximateNumberOfMessages"]
        + data["main"]["counts"]["ApproximateNumberOfMessagesNotVisible"],
    )
    workers = read_series(
        directory / "events/collect-worker-samples.jsonl", start,
        lambda data: (data["desired"], data["ready"]),
    )
    nodes = read_series(
        directory / "events/collect-topology-samples.jsonl", start,
        lambda data: sum(
            all(node.get("labels", {}).get(key) == value for key, value in selector.items())
            for node in data["nodes"]
        ),
    )
    end = min(series[-1][0] for series in (queue, workers, nodes))
    if end <= stop:
        raise ValueError("Không đủ mẫu sau khi dừng workload")
    interval = float(collection.get("requested_interval_seconds", 5))
    events = {key: timestamp(marks[key]) - start for key in (f"T{i}" for i in range(9)) if marks.get(key)}
    return {"id": report["run_id"], "queue": queue, "workers": workers, "nodes": nodes,
            "high": high, "high_end": high_end, "stop": stop, "end": end, "events": events,
            "low_rate": workload["low_request_per_second"], "high_rate": workload["high_request_per_second"],
            "max_gap": max(30.0, interval * 3 + 10)}


def separated(points, max_gap):
    """Không nối đường qua một khoảng thiếu mẫu quá dài."""
    x, y = [], []
    previous = None
    for elapsed, value in points:
        if previous is not None and elapsed - previous > max_gap:
            x.append((previous + elapsed) / 2)
            y.append(float("nan"))
        x.append(elapsed)
        y.append(value)
        previous = elapsed
    return x, y


def draw(data: dict):
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
        "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.edgecolor": GRID, "figure.facecolor": "white", "axes.facecolor": "white",
        "axes.spines.top": False, "axes.spines.right": False,
        "savefig.facecolor": "white",
    })
    fig, axes = plt.subplots(3, 1, figsize=(12, 7.8), sharex=True)
    fig.subplots_adjust(left=.105, right=.98, top=.87, bottom=.105, hspace=.28)
    handles = [
        Line2D([0], [0], color=QUEUE, lw=2, marker=".", label="Queue"),
        Line2D([0], [0], color=READY, lw=2.2, label="Ready workers"),
        Line2D([0], [0], color=DESIRED, lw=1.8, ls="--", label="Desired workers"),
        Line2D([0], [0], color=NODE, lw=2, label="E2 nodes present"),
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.55, .98),
               ncol=4, frameon=False, fontsize=9.5)

    # Cùng cách tô pha và vẽ bậc như biểu đồ timeline E1; kéo dài qua lúc thu hồi Node.
    low, high, high_end, stop = 0, data["high"], data["high_end"], data["stop"]
    end = data["end"]
    for row, ax in enumerate(axes):
        ax.set_axisbelow(True)
        ax.grid(axis="y", color=GRID, linewidth=.8)
        ax.tick_params(length=0, pad=6)
        ax.axvspan(low, high, color="#e9f2f5", alpha=.72, lw=0, zorder=0)
        ax.axvspan(high_end, stop, color="#e9f2f5", alpha=.72, lw=0, zorder=0)
        for t in (0, stop):
            ax.axvline(t, color="#9aaab8", linewidth=.9, linestyle=":")
        ax.set_xlim(0, end)
        if row:
            ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    for begin, end_phase, label in (
        (0, high, f"{data['low_rate']} req/s"),
        (high, high_end, f"{data['high_rate']} req/s"),
        (high_end, stop, f"{data['low_rate']} req/s"),
    ):
        axes[0].text((begin + end_phase) / 2, 1.035, label,
                     transform=axes[0].get_xaxis_transform(), ha="center", va="bottom",
                     fontsize=10, color=MUTED)

    x, y = separated(data["queue"], data["max_gap"])
    axes[0].plot(x, y, color=QUEUE, linewidth=1.9, marker=".", markersize=4.5)
    axes[0].set_ylabel("Queue\n(visible + in-flight)")
    axes[0].set_ylim(bottom=0)

    for index, color, style, label in ((0, DESIRED, "--", "desired"), (1, READY, "-", "ready")):
        series = [(elapsed, value[index]) for elapsed, value in data["workers"]]
        x, y = separated(series, data["max_gap"])
        axes[1].step(x, y, where="post", color=color, linestyle=style,
                     linewidth=1.6 if label == "desired" else 2.2)
    axes[1].set_ylabel("Workers\n(replicas)")
    axes[1].set_ylim(0, max(1, max(max(value) for _, value in data["workers"]) * 1.25))

    x, y = separated(data["nodes"], data["max_gap"])
    axes[2].step(x, y, where="post", color=NODE, linewidth=2.2)
    axes[2].set_ylabel("E2 nodes\n(present)")
    axes[2].set_xlabel("Time since workload start (s)")
    axes[2].set_ylim(0, max(1, max(value for _, value in data["nodes"]) + 0.8))

    # Lần đầu quan sát số Node giảm ở lần scale-down cuối cùng, không phải
    # thời điểm EC2 thực sự bị chấm dứt.
    decreases = [
        (current_time, current_count)
        for (_, previous_count), (current_time, current_count)
        in zip(data["nodes"], data["nodes"][1:])
        if 0 <= current_time <= end and current_count < previous_count
    ]
    if decreases:
        decrease_time, decrease_count = decreases[-1]
        axes[2].vlines(decrease_time, 0, decrease_count, color=EVENT,
                       linewidth=1.4, linestyle="--", zorder=4)
        axes[2].scatter([decrease_time], [decrease_count], s=26, color=EVENT, zorder=5)
        axes[2].annotate(f"{decrease_time:.1f} s", xy=(decrease_time, 0),
                         xycoords=axes[2].get_xaxis_transform(), xytext=(0, -9),
                         textcoords="offset points", ha="center", va="top",
                         fontsize=9, color=EVENT,
                         bbox={"facecolor": "white", "edgecolor": "none", "pad": .5})

    # Bố trí các nhãn theo nhiều hàng để những mốc gần nhau không chồng lên nhau.
    # Đường đứng thể hiện thời điểm; chiều cao nhãn không phải giá trị của metric.
    event_labels = (
        ("T0", 0, .95, "left"), ("T6", 0, .95, "right"), ("T7", 0, .69, "left"),
        ("T1", 1, .95, "right"), ("T2", 1, .64, "left"),
        ("T5", 1, .95, "left"), ("T8", 1, .95, "left"),
        ("T3", 2, .95, "right"), ("T4", 2, .95, "left"),
    )
    for key, row, label_height, alignment in event_labels:
        if key not in data["events"]:
            continue
        t = data["events"][key]
        axes[row].axvline(t, color=EVENT, linewidth=1.2, linestyle=":", alpha=.85)
        label = f"{key}\n{t:.1f} s"
        axes[row].text(t, label_height, label, transform=axes[row].get_xaxis_transform(),
                       ha=alignment, va="top", fontsize=8.5, color=EVENT,
                       bbox={"facecolor": "white", "edgecolor": "none", "pad": 1, "alpha": .9})
    return fig


def main() -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path,
                        default=E2_DIR.parent / "results/E2/E2-elastic-burst-r02")
    parser.add_argument("--output-dir", type=Path, default=E2_DIR / "figures")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    targets = [args.output_dir / "e2-e1-style-timeline.png"]
    if not args.overwrite and any(path.exists() for path in targets):
        print("Ảnh đã tồn tại; dùng --overwrite nếu muốn tạo lại.", file=sys.stderr)
        return 1
    try:
        data = load_run(args.run_dir)
        figure = draw(data)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for path in targets:
            figure.savefig(path, dpi=200)
            print(f"Đã tạo: {path.resolve()}")
        plt.close(figure)
        print(f"Nguồn: {data['id']}; cửa sổ chung đến {data['end']:.1f} giây từ T0.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Không thể vẽ E2: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
