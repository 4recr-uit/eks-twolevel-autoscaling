#!/usr/bin/env python3
"""Vẽ lại timeline E7 theo bố cục trang dọc từ các mẫu thực nghiệm."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from plot_e7 import (
    BASE, COLORS, INK, LABELS, MUTED, RATES, VARIANTS,
    configure, load_run, separated, style,
)


def main():
    output = BASE / "figures" / "queue-worker-portrait.png"
    if output.exists():
        raise FileExistsError(f"Ảnh đã tồn tại: {output}")
    runs = {variant: load_run(BASE.parent / "results/E7", variant) for variant in VARIANTS}
    configure()
    fig, axes = plt.subplots(3, 2, figsize=(9, 8.1), sharex=True, sharey="col")
    fig.subplots_adjust(left=.115, right=.98, top=.88, bottom=.105, hspace=.31, wspace=.17)
    handles = [
        Line2D([0], [0], color=INK, lw=1.8, marker=".", label="Mẫu hàng đợi"),
        Line2D([0], [0], color=INK, lw=2, label="Worker Ready"),
        Line2D([0], [0], color=INK, lw=1.5, ls="--", label="Mong muốn"),
        Line2D([0], [0], color=MUTED, lw=1, ls=":", label="Giới hạn replica"),
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .99),
               ncol=2, frameon=False, fontsize=10)
    axes[0, 0].set_title("Hàng đợi (visible + in-flight)", fontsize=11, pad=20)
    axes[0, 1].set_title("Số worker", fontsize=11, pad=20)
    for row, variant in enumerate(VARIANTS):
        run, color = runs[variant], COLORS[variant]
        for col in range(2):
            ax = axes[row, col]
            style(ax)
            for i, rate in enumerate(RATES):
                if i % 2 == 0:
                    ax.axvspan(i * 60, (i + 1) * 60, color="#e9f2f5", alpha=.72, lw=0)
                if col == 0:
                    ax.text(i * 60 + 30, 1.02, str(rate),
                            transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                            fontsize=8.5, color=MUTED)
            for x in (0, 420):
                ax.axvline(x, color="#9aaab8", linestyle=":", lw=.9)
            ax.set_xlim(-60, 570)
        axes[row, 0].set_ylabel(f"{LABELS[variant]}\nThông điệp", color=color, fontsize=10)
        axes[row, 0].set_ylim(0, 57)
        axes[row, 0].yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
        x, y = separated(run["queue"], run["queue_gap"])
        axes[row, 0].plot(x, y, color=color, marker=".", markersize=3, lw=1.6)
        for name, line in (("desired", "--"), ("ready", "-")):
            x, y = separated(run[name], run["replica_gap"])
            axes[row, 1].step(x, y, where="post", color=color, ls=line,
                              lw=1.4 if name == "desired" else 1.9,
                              alpha=.75 if name == "desired" else 1)
        axes[row, 1].axhline(10, color=MUTED, ls=":", lw=1)
        axes[row, 1].set_ylim(0, 11)
        axes[row, 1].yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
    for ax in axes[-1]:
        ax.set_xlabel("Thời gian từ đầu workload (giây)", fontsize=9.5)
    fig.savefig(output, dpi=200, facecolor="white")
    plt.close(fig)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
