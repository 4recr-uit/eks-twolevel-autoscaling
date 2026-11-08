"""Publication-friendly Matplotlib figures for the E1 observations."""

from decimal import Decimal, ROUND_HALF_UP
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from e1_plot_data import STAGES, VARIANTS


COLORS = {"warm": "#177d8c", "elastic": "#d97824"}
LABELS = {"warm": "Warm", "elastic": "Elastic"}
INK = "#213348"
MUTED = "#5e6d7e"
GRID = "#dfe6ed"


def configure():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
        "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.edgecolor": GRID, "figure.facecolor": "white", "axes.facecolor": "white",
        "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none",
        "savefig.facecolor": "white",
    })


def fmt(value):
    value = Decimal(str(value))
    places = 3 if 0 < abs(value) < 1 else 2
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{rounded:.{places}f}"


def style_axis(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(length=0, pad=6)


def summary_figure(profile, runs):
    configure()
    fig, axes = plt.subplots(1, 3, figsize=(15.8, 5.6))
    fig.subplots_adjust(left=0.065, right=0.985, top=0.88, bottom=0.16, wspace=0.35)
    specs = (
        ("P95 end-to-end latency", "Seconds", lambda r: r.report["latency_seconds_approx_all_statuses"]["p95"]),
        ("Peak queue depth", "Messages", lambda r: r.report["peak_visible_plus_inflight_approx"]),
        ("Node-minutes", "Node-minutes", lambda r: r.report["worker_node_minutes_approx"]),
    )
    for ax, (title, unit, accessor) in zip(axes, specs):
        style_axis(ax)
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=14)
        ax.set_ylabel(unit, fontsize=10)
        max_value = max(mean(accessor(r) for r in runs if r.variant == variant) for variant in VARIANTS)
        ax.set_ylim(0, max_value * 1.36 if max_value else 1)
        for x, variant in enumerate(VARIANTS):
            group = sorted((r for r in runs if r.variant == variant), key=lambda r: r.attempt)
            values = [accessor(r) for r in group]
            avg = mean(values)
            displayed_avg = sum(Decimal(str(value)) for value in values) / len(values)
            ax.bar(x, avg, width=0.57, color=COLORS[variant], alpha=0.88, zorder=2)
            ax.text(x, avg + max_value * .035, fmt(displayed_avg), ha="center", va="bottom",
                    fontsize=12, fontweight="bold", color=COLORS[variant], zorder=5)
        ax.set_xticks(range(2), ["Warm", "Elastic"])
        ax.set_xlim(-.65, 1.65)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    return fig


def conclusion_figure(groups):
    """Compare per-profile means; p95 is averaged per run, not pooled."""
    configure()
    fig, axes = plt.subplots(1, 3, figsize=(15.8, 5.6))
    fig.subplots_adjust(left=.065, right=.985, top=.84, bottom=.19, wspace=.35)
    legend = [Line2D([0], [0], color=COLORS[v], marker="s", linestyle="None", markersize=10,
                     label=LABELS[v]) for v in VARIANTS]
    fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(.5, .99), ncol=2, frameon=False)
    specs = (
        ("P95 end-to-end latency", "Seconds", lambda r: r.report["latency_seconds_approx_all_statuses"]["p95"]),
        ("Peak queue depth", "Messages", lambda r: r.report["peak_visible_plus_inflight_approx"]),
        ("Node-minutes", "Node-minutes", lambda r: r.report["worker_node_minutes_approx"]),
    )
    for ax, (title, unit, accessor) in zip(axes, specs):
        style_axis(ax)
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=14)
        ax.set_ylabel(unit, fontsize=10)
        averages = {}
        for profile, runs in groups.items():
            for variant in VARIANTS:
                values = [Decimal(str(accessor(r))) for r in runs if r.variant == variant]
                averages[profile, variant] = sum(values) / len(values)
        maximum = max(float(value) for value in averages.values())
        ax.set_ylim(0, maximum * 1.30 if maximum else 1)
        for x, profile in enumerate(("step", "burst")):
            for index, variant in enumerate(VARIANTS):
                value = averages[profile, variant]
                position = x + (-.19 if index == 0 else .19)
                ax.bar(position, float(value), width=.34, color=COLORS[variant], alpha=.88, zorder=2)
                ax.text(position, float(value) + maximum * .025, fmt(value), ha="center", va="bottom",
                        fontsize=10.5, fontweight="bold", color=COLORS[variant])
        ax.set_xticks((0, 1), [f"Step\n(n={len(groups['step']) // 2})",
                                f"Burst\n(n={len(groups['burst']) // 2})"])
        ax.set_xlim(-.65, 1.65)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    return fig


def burst_comparison_figure(groups):
    """Compare run means across the three minimum-worker configurations."""
    configure()
    fig, axes = plt.subplots(2, 2, figsize=(15, 8.5))
    fig.subplots_adjust(left=.075, right=.985, top=.90, bottom=.09, hspace=.48, wspace=.26)
    legend = [Line2D([0], [0], color=COLORS[v], marker="s", linestyle="None", markersize=10,
                     label=LABELS[v]) for v in VARIANTS]
    fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(.5, .99), ncol=2, frameon=False)
    specs = (
        ("P95 end-to-end latency", "Seconds", lambda r: r.report["latency_seconds_approx_all_statuses"]["p95"]),
        ("Peak queue depth", "Messages", lambda r: r.report["peak_visible_plus_inflight_approx"]),
        ("Ready pod-minutes", "Pod-minutes", lambda r: r.report["ready_pod_minutes_approx"]),
        ("Node-minutes", "Node-minutes", lambda r: r.report["worker_node_minutes_approx"]),
    )
    for ax, (title, unit, accessor) in zip(axes.flat, specs):
        style_axis(ax)
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel(unit, fontsize=10)
        averages = {}
        for config, runs in groups.items():
            for variant in VARIANTS:
                values = [Decimal(str(accessor(r))) for r in runs if r.variant == variant]
                averages[config, variant] = sum(values) / len(values)
        maximum = max(float(value) for value in averages.values())
        ax.set_ylim(0, maximum * 1.28 if maximum else 1)
        for x, config in enumerate((1, 2, 3)):
            for index, variant in enumerate(VARIANTS):
                value = averages[config, variant]
                position = x + (-.19 if index == 0 else .19)
                ax.bar(position, float(value), width=.34, color=COLORS[variant], alpha=.88, zorder=2)
                ax.text(position, float(value) + maximum * .025, fmt(value), ha="center", va="bottom",
                        fontsize=10, fontweight="bold", color=COLORS[variant])
        ax.set_xticks(range(3), ["1", "3", "5"])
        ax.set_xlabel("Minimum workers", fontsize=10)
        ax.set_xlim(-.62, 2.62)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    return fig


def separated(series, max_gap):
    """Break plotted lines across missing samples rather than inventing data."""
    xs, ys = [], []
    previous = None
    for time, value in series:
        if previous is not None and time - previous > max_gap:
            xs.append((previous + time) / 2)
            ys.append(float("nan"))
        xs.append(time)
        ys.append(value)
        previous = time
    return xs, ys


def shade_stages(ax, profile, show_labels=False):
    start = 0
    for index, (duration, rate) in enumerate(STAGES[profile]):
        end = start + duration
        if index % 2 == 0:
            ax.axvspan(start, end, color="#e9f2f5", alpha=.72, lw=0, zorder=0)
        if show_labels:
            ax.text((start + end) / 2, 1.025, f"{rate}/s", transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=9, color=MUTED)
        start = end
    ax.axvline(0, color="#9aaab8", lw=.9, linestyle=":")
    ax.axvline(start, color="#9aaab8", lw=.9, linestyle=":")


def timeline_figure(profile, runs, attempts):
    configure()
    fig, axes = plt.subplots(3, len(attempts), figsize=(max(12, 7.6 * len(attempts)), 9.8),
                             sharex="col", sharey="row", squeeze=False)
    fig.subplots_adjust(left=.075, right=.98, top=.84, bottom=.09, hspace=.29, wspace=.16)
    legend = [Line2D([0], [0], color=COLORS[v], lw=2.4, label=LABELS[v]) for v in VARIANTS]
    legend += [Line2D([0], [0], color=MUTED, lw=1.8, label="Ready"),
               Line2D([0], [0], color=MUTED, lw=1.6, ls="--", label="Desired (worker)")]
    fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(.5, .99), ncol=4,
               frameon=False, fontsize=10)
    duration = sum(length for length, _ in STAGES[profile])
    for column, attempt in enumerate(attempts):
        top = axes[0][column]
        top.set_title(f"Run {attempt:02d}", loc="left", fontweight="bold", fontsize=12, pad=26)
        for row in range(3):
            ax = axes[row][column]
            style_axis(ax)
            shade_stages(ax, profile, show_labels=(row == 0))
            ax.set_xlim(-60, duration + 60)
            if row in (1, 2):
                ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
            if row == 2:
                ax.set_xlabel("Time since workload start (s)", fontsize=10)
        for variant in VARIANTS:
            run = next(r for r in runs if r.variant == variant and r.attempt == attempt)
            color = COLORS[variant]
            x, y = separated(run.queue, run.max_gap)
            axes[0][column].plot(x, y, color=color, lw=1.9, marker=".", markersize=4,
                                 alpha=.95, label=LABELS[variant])
            for series, style, width in ((run.desired, "--", 1.25), (run.ready, "-", 2.0)):
                x, y = separated(series, run.max_gap)
                axes[1][column].step(x, y, where="post", color=color, linestyle=style,
                                     linewidth=width, alpha=.95 if style == "-" else .65)
            x, y = separated(run.nodes, run.max_gap)
            axes[2][column].step(x, y, where="post", color=color, lw=2.0)
    for row, name in enumerate(("queue", "ready", "nodes")):
        series_names = ("ready", "desired") if name == "ready" else (name,)
        values = [value for run in runs for series_name in series_names
                  for time, value in getattr(run, series_name) if -60 <= time <= duration + 60]
        maximum = max(values, default=0)
        axes[row][0].set_ylim(0, max(1, maximum * 1.12))
    axes[0][0].set_ylabel("Queue depth\n(visible + in-flight)", fontsize=10)
    axes[1][0].set_ylabel("Worker replicas", fontsize=10)
    axes[2][0].set_ylabel("E1 nodes observed", fontsize=10)
    return fig
