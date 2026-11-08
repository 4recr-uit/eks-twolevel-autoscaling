"""Vẽ timeline E2 r02 từ mẫu collector và mốc k6; không sửa dữ liệu gốc."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator


ROOT = Path(__file__).resolve().parent
RUN = ROOT.parent / "results" / "E2" / "E2-elastic-burst-r02"
OUTPUT = ROOT / "figures" / "e2-r02-timeline.png"


def seconds(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def samples(path, start, value_fn):
    points = []
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                points.append((seconds(row["observed_at_utc"]) - start, value_fn(row["data"])))
    if not points:
        raise ValueError(f"Khong co mau: {path}")
    return sorted(points)


def segmented(points, maximum_gap=30):
    """Ngắt đường khi thiếu mẫu dài; không nối suy diễn qua khoảng trống."""
    x, y = [], []
    previous = None
    for time, value in points:
        if previous is not None and time - previous > maximum_gap:
            x.append((time + previous) / 2)
            y.append(float("nan"))
        x.append(time)
        y.append(value)
        previous = time
    return x, y


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"Anh da ton tai: {args.output}; dung --overwrite neu can.")

    timeline = json.loads((RUN / "timeline.json").read_text(encoding="utf-8-sig"))
    k6 = json.loads((RUN / "raw" / "k6-summary.json").read_text(encoding="utf-8-sig"))["metrics"]
    expected = {"workload_model_version": 5, "workload_profile_code": 2,
                "workload_low_rate": 5, "workload_high_rate": 40}
    if any(k6[name]["value"] != value for name, value in expected.items()):
        raise ValueError("Workload khong khop Burst E2 version 5.")
    start = seconds(timeline["timeline_utc"]["T0"])
    if abs(start - k6["workload_started_at_unix_ms"]["value"] / 1000) > 0.01:
        raise ValueError("Moc bat dau k6 va timeline khong khop.")
    markers = {name: seconds(timeline["timeline_utc"][name]) - start for name in ("T3", "T4", "T8")}
    if not (0 <= markers["T3"] < 60 < markers["T4"] < 150 < markers["T8"]):
        raise ValueError("Moc timeline khong khop luot E2 r02.")

    queue = samples(
        RUN / "metrics" / "collect-sqs-samples.jsonl", start,
        lambda data: data["main"]["counts"]["ApproximateNumberOfMessages"]
        + data["main"]["counts"]["ApproximateNumberOfMessagesNotVisible"],
    )
    worker_rows = RUN / "events" / "collect-worker-samples.jsonl"
    desired = samples(worker_rows, start, lambda data: data["desired"])
    ready = samples(worker_rows, start, lambda data: data["ready"])
    nodes = samples(
        RUN / "events" / "collect-topology-samples.jsonl", start,
        lambda data: sum(node.get("labels", {}).get("karpenter.sh/nodepool") == "e2-orders"
                         for node in data["nodes"]),
    )
    if max(value for time, value in queue if 0 <= time <= 210.1) != 52:
        raise ValueError("Peak queue khong khop README E2.")

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#263645", "text.color": "#263645",
                         "xtick.color": "#465866", "ytick.color": "#465866"})
    fig, axes = plt.subplots(4, 1, figsize=(12.5, 10.2), sharex=True,
                             gridspec_kw={"height_ratios": [0.9, 1.15, 1.15, 0.9]})
    fig.subplots_adjust(left=0.15, right=0.98, top=0.91, bottom=0.09, hspace=0.21)
    event_colors = {"T3": "#995a20", "T4": "#71559a"}
    for ax in axes:
        ax.axvspan(60, 150, facecolor="#eaf2f5", alpha=0.9, zorder=0)
        for name, color in event_colors.items():
            ax.axvline(markers[name], color=color, linestyle=":", linewidth=1.6, alpha=0.85)
        ax.grid(axis="y", color="#dbe3e8", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_xlim(-15, 380)
    axes[0].step([-15, 0, 60, 150, 210, 380], [0, 5, 40, 5, 0, 0],
                 where="post", color="#265f90", linewidth=2.6)
    axes[0].set_ylabel("Tải mục tiêu\n(request/s)")
    axes[0].set_yticks([0, 5, 40])
    axes[0].set_ylim(0, 47)
    axes[0].text(105, 42.3, "Pha tải cao", ha="center", fontsize=10)
    x, y = segmented(queue)
    axes[1].plot(x, y, color="#bd672b", marker=".", markersize=4, linewidth=1.8)
    axes[1].set_ylabel("Hàng đợi\n(thông điệp)")
    axes[1].set_ylim(bottom=0)
    for data, color, label, style in [
        (desired, "#648293", "Mong muốn", "--"),
        (ready, "#087c85", "Ready", "-"),
    ]:
        x, y = segmented(data)
        axes[2].step(x, y, where="post", color=color, linestyle=style, linewidth=2.2, label=label)
    axes[2].set_ylabel("Worker\n(replica)")
    axes[2].set_ylim(0, 7)
    axes[2].yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    axes[2].legend(loc="upper right", ncol=2, frameon=False, fontsize=10)
    x, y = segmented(nodes)
    axes[3].step(x, y, where="post", color="#555bb0", linewidth=2.2)
    axes[3].set_ylabel("Node E2\n(ghi nhận)")
    axes[3].set_ylim(0, 3)
    axes[3].set_yticks([0, 1, 2, 3])
    axes[3].set_xlabel("Thời gian từ đầu workload (giây)")
    axes[3].set_xticks([0, 60, 120, 180, 210, 270, 330, 380])
    fig.legend(handles=[
        Line2D([0], [0], color=event_colors["T3"], linestyle=":", lw=1.8,
               label="T3: tạo NodeClaim"),
        Line2D([0], [0], color=event_colors["T4"], linestyle=":", lw=1.8,
               label="T4: quan sát Node Ready"),
    ], loc="upper center", ncol=2, frameon=False, fontsize=11, bbox_to_anchor=(0.55, 0.985))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200, facecolor="white")
    plt.close(fig)
    print(f"Saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()
