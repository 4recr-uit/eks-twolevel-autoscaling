#!/usr/bin/env python3
"""Vẽ diễn biến một lượt E2 từ dữ liệu collector và timeline đã lưu."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


def parse_time(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_samples(path: Path, start: float, get_value) -> list[tuple[float, object]]:
    points = []
    with path.open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                points.append((parse_time(sample["observed_at_utc"]) - start, get_value(sample["data"])))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path}, dòng {number}: dữ liệu không hợp lệ: {exc}") from exc
    if not points:
        raise ValueError(f"Không có mẫu trong {path}")
    return sorted(points, key=lambda point: point[0])


def node_count(data: dict, selector: dict[str, str]) -> int:
    return sum(
        all(node.get("labels", {}).get(key) == value for key, value in selector.items())
        for node in data["nodes"]
    )


def load_run(run_dir: Path) -> dict:
    report = load_json(run_dir / "report.json")
    timeline = load_json(run_dir / "timeline.json")
    if report["run_id"] != timeline["run_id"]:
        raise ValueError("run_id trong report và timeline không khớp")
    workload = report["workload"]
    if report.get("profile") != "burst" or workload.get("model_version") != 5:
        raise ValueError("Script hiện hỗ trợ workload E2 Burst model v5")
    if workload.get("high_phase_duration_seconds") != 90:
        raise ValueError("Model v5 yêu cầu pha cao 90 giây; hãy kiểm tra workload")
    selector = report["configuration"]["node_selector"]
    if not selector:
        raise ValueError("Thiếu node selector để xác định Node worker E2")

    t0 = parse_time(timeline["timeline_utc"]["T0"])
    t6 = parse_time(timeline["timeline_utc"]["T6"]) - t0
    high = parse_time(timeline["high_rate_started_utc"]) - t0
    high_end = high + workload["high_phase_duration_seconds"]
    if not (0 < high < high_end < t6):
        raise ValueError("Các mốc workload không theo thứ tự của Burst model v5")

    queue = load_samples(
        run_dir / "metrics/collect-sqs-samples.jsonl", t0,
        lambda data: (data["main"]["counts"]["ApproximateNumberOfMessages"]
                      + data["main"]["counts"]["ApproximateNumberOfMessagesNotVisible"]),
    )
    workers = load_samples(
        run_dir / "events/collect-worker-samples.jsonl", t0,
        lambda data: (data["desired"], data["ready"]),
    )
    nodes = load_samples(
        run_dir / "events/collect-topology-samples.jsonl", t0,
        lambda data: node_count(data, selector),
    )
    end = min(series[-1][0] for series in (queue, workers, nodes))
    if end <= t6:
        raise ValueError("Mẫu không bao phủ khoảng sau khi dừng workload")
    markers = {
        key: parse_time(value) - t0
        for key, value in timeline["timeline_utc"].items()
        if key in ("T3", "T4", "T8") and value is not None
    }
    return {"run_id": report["run_id"], "workload": workload, "high": high,
            "high_end": high_end, "stop": t6, "end": end, "queue": queue,
            "workers": workers, "nodes": nodes, "markers": markers}


def create_figure(data: dict):
    # Không dùng backend tương tác để script chạy được trên máy không có GUI.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.titlesize": 11, "axes.labelsize": 10,
                         "legend.fontsize": 8.5, "svg.fonttype": "none"})
    fig, axes = plt.subplots(4, 1, figsize=(9, 7.5), sharex=True,
                             gridspec_kw={"height_ratios": [0.8, 1, 1, 1], "hspace": 0.25})
    fig.suptitle("E2 — Diễn biến tải, hàng đợi và co giãn", fontsize=14, fontweight="bold", y=0.99)
    fig.text(0.5, 0.942, "Một lượt đo; thời gian tính từ lúc bắt đầu workload", ha="center", fontsize=9.5)

    high, high_end, stop, end = (data[name] for name in ("high", "high_end", "stop", "end"))
    for ax in axes:
        ax.axvspan(high, high_end, color="#f3c969", alpha=0.2, zorder=0)
        ax.axvspan(stop, end, color="#e5e7eb", alpha=0.5, zorder=0)
        ax.axvline(stop, color="#737b88", linewidth=0.9, linestyle="--", alpha=0.85)
        ax.grid(axis="y", color="#d8dee7", linewidth=0.7, alpha=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)

    # Các bậc biểu diễn tốc độ đặt theo kịch bản, không phải request/s đã đo.
    w = data["workload"]
    axes[0].step([0, high, high_end, stop, end],
                 [w["low_request_per_second"], w["high_request_per_second"],
                  w["low_request_per_second"], 0, 0],
                 where="post", color="#355d9a", linewidth=2)
    axes[0].set_ylabel("Tải đặt\n(request/s)")
    axes[0].set_ylim(bottom=0, top=w["high_request_per_second"] * 1.3)
    axes[0].set_yticks([0, w["high_request_per_second"] / 2, w["high_request_per_second"]])
    axes[0].text((high + high_end) / 2, 0.92, "Pha tải cao", transform=axes[0].get_xaxis_transform(),
                 ha="center", va="top", fontsize=9, color="#704b00")
    axes[0].text((stop + end) / 2, 0.92, "Sau khi dừng tải", transform=axes[0].get_xaxis_transform(),
                 ha="center", va="top", fontsize=9, color="#555e69")

    # Chỉ vẽ điểm SQS: số liệu xấp xỉ, không giả định diễn biến giữa hai mẫu.
    qx, qy = zip(*data["queue"])
    axes[1].scatter(qx, qy, s=14, color="#b75e28", alpha=0.9, label="Visible + in-flight", zorder=3)
    axes[1].set_ylabel("Queue\n(message)")
    axes[1].set_ylim(bottom=0)
    axes[1].legend(loc="upper right", frameon=False)

    wx = [point[0] for point in data["workers"]]
    desired = [point[1][0] for point in data["workers"]]
    ready = [point[1][1] for point in data["workers"]]
    axes[2].step(wx, desired, where="post", color="#4b78a8", linewidth=1.5,
                 linestyle="--", label="Desired")
    axes[2].step(wx, ready, where="post", color="#207b5f", linewidth=2, label="Ready")
    axes[2].scatter(wx, ready, s=8, color="#207b5f", alpha=0.65, zorder=3)
    if "T8" in data["markers"]:
        axes[2].axvline(data["markers"]["T8"], color="#77538e", linestyle=":", linewidth=1.4,
                        label=f"Quan sát 0 worker (T8 ≈ {data['markers']['T8']:.0f} s)")
    axes[2].set_ylabel("Worker\n(replica)")
    axes[2].set_ylim(0, max(1, max(desired), max(ready)) * 1.45)
    axes[2].yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    axes[2].legend(loc="upper right", ncol=3, frameon=False)

    nx, ny = zip(*data["nodes"])
    axes[3].step(nx, ny, where="post", color="#555e6c", linewidth=2, label="Node E2 hiện diện")
    axes[3].scatter(nx, ny, s=8, color="#555e6c", alpha=0.6, zorder=3)
    for key, color, label in (("T3", "#8a5a9b", "Tạo NodeClaim"),
                               ("T4", "#23856b", "Quan sát Node Ready")):
        if key in data["markers"]:
            value = data["markers"][key]
            axes[3].axvline(value, color=color, linestyle=":", linewidth=1.5,
                            label=f"{label} ({key} ≈ {value:.0f} s)")
    axes[3].set_ylabel("Node E2\n(Node)")
    axes[3].set_xlabel("Thời gian từ T0 (giây)")
    axes[3].set_ylim(-0.1, max(4.8, max(ny) + 2.8))
    axes[3].set_yticks(range(0, max(ny) + 1))
    axes[3].legend(loc="upper right", ncol=1, frameon=False)
    axes[3].set_xlim(0, end)
    fig.text(0.5, 0.025,
             "Tải là lịch phát dự kiến; queue là mẫu SQS xấp xỉ; Pod/Node biểu diễn theo mẫu quan sát.",
             ha="center", fontsize=8.5, color="#555e69")
    fig.subplots_adjust(left=0.12, right=0.98, top=0.90, bottom=0.12)
    return fig


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path,
                        default=root.parent / "results/E2/E2-elastic-burst-r02",
                        help="thư mục dữ liệu E2; mặc định là r02")
    parser.add_argument("--output-dir", type=Path, default=root / "figures",
                        help="thư mục lưu PNG và SVG")
    parser.add_argument("--overwrite", action="store_true", help="cho phép ghi đè ảnh đã tồn tại")
    args = parser.parse_args()
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    targets = [args.output_dir / f"e2-two-level.{ext}" for ext in ("png", "svg")]
    if not args.overwrite and any(path.exists() for path in targets):
        print("Ảnh đã tồn tại; dùng --overwrite nếu muốn ghi đè.", file=sys.stderr)
        return 1
    try:
        data = load_run(args.run_dir)
        fig = create_figure(data)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for path in targets:
            fig.savefig(path, dpi=250, facecolor="white")
            print(f"Đã tạo: {path.resolve()}")
        import matplotlib.pyplot as plt
        plt.close(fig)
        print(f"Dữ liệu: {data['run_id']}; kết thúc cửa sổ chung: {data['end']:.1f} s")
        return 0
    except ModuleNotFoundError as exc:
        print(f"Thiếu thư viện {exc.name}. Cài bằng: python -m pip install matplotlib", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Không thể tạo biểu đồ: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
