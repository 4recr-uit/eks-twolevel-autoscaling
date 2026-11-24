"""Render the E5 Burst r01 figures from local run artifacts (requires matplotlib)."""

import argparse
from datetime import datetime
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


BASE = Path(__file__).resolve().parent
BURST_START, BURST_END, BIN_SECONDS = 60, 90, 10
INK, MUTED, GRID = "#213348", "#55697b", "#dee5ea"
TEAL, SLATE, RUST = "#177d8c", "#556c84", "#a64d20"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def chart(title):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    fig.subplots_adjust(left=.095, right=.97, bottom=.19, top=.79)
    fig.text(.095, .92, title, fontsize=18, weight="bold", color=INK)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, lw=.8)
    ax.tick_params(length=0, pad=6)
    return fig, ax


def worker_timeline(samples, title):
    fig, ax = chart(title)
    ax.axvspan(BURST_START, BURST_END, color="#eff5f6", lw=0)
    times, desired, ready = zip(*samples)
    ax.step(times, ready, where="post", color=TEAL, lw=3, label="Ready (sampled)")
    ax.plot(times, ready, "o", ms=4.5, color=TEAL, zorder=4)
    ax.step(times, desired, where="post", color=INK, ls="--", lw=1.6, label="Desired")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2, borderaxespad=0)
    ax.set(xlim=(BURST_START, 110), ylim=(0, 13), yticks=range(0, 13, 2),
           xticks=range(60, 111, 10), ylabel="Worker pods", xlabel="Seconds since workload start")
    ax.set_xticklabels(["60\nBurst starts", "70", "80", "90\nBurst ends", "100", "110"])
    return fig, ax


def baseline_chart(samples):
    fig, ax = worker_timeline(samples, "Baseline worker scaling during the burst")
    burst_samples = [row for row in samples if BURST_START <= row[0] < BURST_END]
    peak = max(desired for _, desired, _ in burst_samples)
    first_ready = next(t for t, desired, ready in burst_samples if desired == ready == peak)
    ax.annotate(f"{peak}/{peak} observed ready\nat {first_ready:.2f} s",
                xy=(first_ready, peak), xytext=(first_ready + 5, peak - 4), ha="left",
                fontsize=11, color=TEAL, arrowprops={"arrowstyle": "->", "color": TEAL})
    return fig


def recovery_chart(samples, deletes):
    fig, ax = worker_timeline(samples, "Worker recovery after pod deletion")
    for i, t in enumerate(deletes, start=1):
        ax.axvline(t, color=RUST, ls=":", lw=1.2)
        ax.text(t - .5, 12.6, f"Delete {i}\n{t:.2f} s", color=RUST,
                fontsize=10, ha="right", va="top")
    last_delete = deletes[-1]
    deficit = next(t for t, d, r in samples if t > last_delete and r < d)
    recovered, target, _ = next(row for row in samples
                                if row[0] > deficit and row[1] == row[2] and row[1] > 0)
    ax.annotate(f"{target}/{target} observed ready\n{recovered - last_delete:.1f} s after deletion",
                xy=(recovered, target), xytext=(recovered + 1, 5), ha="center",
                fontsize=11, color=TEAL, arrowprops={"arrowstyle": "->", "color": TEAL})
    return fig


def throughput_chart(directories, deletes):
    fig, ax = chart("Job throughput during the burst")
    starts = list(range(BURST_START, BURST_END, BIN_SECONDS))
    key = "observed_success_per_s_in_10s_bins_starting_T60_T70_T80"
    for variant, offset, color in (("baseline", -.18, SLATE), ("fault", .18, TEAL)):
        reconciliation = read_json(directories[variant] / "job-reconciliation.json")
        bars = ax.bar([i + offset for i in range(len(starts))], reconciliation[key],
                      width=.32, color=color, label=variant.capitalize(), zorder=2)
        ax.bar_label(bars, fmt="%.1f", padding=-18, color="white", fontsize=11, weight="bold")
    workload = read_json(directories["fault"] / "report.json")["workload"]
    offered = workload["high_request_per_second"] * workload["batch_size"]
    ax.axhline(offered, color=INK, ls="--", lw=1.2, label=f"Offered load ({offered} jobs/s)")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend([*handles[1:], handles[0]], [*labels[1:], labels[0]], loc="lower left",
              bbox_to_anchor=(0, 1.01), ncol=3, borderaxespad=0)
    ticks = []
    for start in starts:
        label = f"{start}–{start + BIN_SECONDS} s"
        for i, t in enumerate(deletes, start=1):
            if start <= t < start + BIN_SECONDS:
                label += f"\nDelete {i} at {t:.2f} s"
        ticks.append(label)
    ax.set(xticks=range(len(starts)), xticklabels=ticks, ylim=(0, offered * 1.12),
           ylabel="Completed jobs/s", xlabel="Seconds since workload start")
    return fig


def load_samples(directory, start):
    samples = []
    with (directory / "events" / "collect-worker-samples.jsonl").open(encoding="utf-8-sig") as stream:
        for line in stream:
            sample = json.loads(line)
            samples.append((timestamp(sample["observed_at_utc"]) - start,
                            sample["data"]["desired"], sample["data"]["ready"]))
    return sorted(samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=BASE.parent / "results" / "E5")
    parser.add_argument("--output-dir", type=Path, default=BASE / "figures")
    args = parser.parse_args()
    directories = {v: args.results_dir / f"E5-{v}-burst-r01" for v in ("baseline", "fault")}
    fault = directories["fault"]
    starts = {v: timestamp(read_json(directory / "report.json")["workload_started_utc"])
              for v, directory in directories.items()}
    audit = read_json(fault / "events" / "audit-pod-deletes.json")
    deletes = sorted(timestamp(e["requestReceivedTimestamp"]) - starts["fault"] for e in audit
                     if e["verb"] == "delete" and e["stage"] == "ResponseComplete" and e["responseCode"] == 200)
    if len(deletes) != 2:
        raise ValueError("Expected two successful pod deletions in the E5 fault r01 audit log")
    samples = {v: load_samples(directory, starts[v]) for v, directory in directories.items()}
    plt.rcParams.update({"font.size": 11, "text.color": INK, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": GRID,
                         "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, fig in (("baseline-worker-timeline", baseline_chart(samples["baseline"])),
                      ("worker-recovery", recovery_chart(samples["fault"], deletes)),
                      ("burst-throughput", throughput_chart(directories, deletes))):
        path = args.output_dir / f"{name}.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        print(path)


if __name__ == "__main__":
    main()
