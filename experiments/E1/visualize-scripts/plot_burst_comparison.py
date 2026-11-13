#!/usr/bin/env python3
"""Compare mean Burst results across all three E1 configurations."""

import argparse
import math
from pathlib import Path
import sys

from e1_plot_data import load_profile


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    e1 = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="So sánh trung bình Burst của ba config E1")
    parser.add_argument("--results-dir", type=Path, default=e1.parent / "results" / "E1")
    parser.add_argument("--output-dir", type=Path, default=e1 / "figures" / "comparison")
    parser.add_argument("--attempts", type=int, nargs="+", default=[1, 2], metavar="N")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if (not args.attempts or len(args.attempts) > 4 or len(set(args.attempts)) != len(args.attempts)
            or any(n <= 0 or n > 99 for n in args.attempts)):
        print("Lỗi: chọn 1–4 attempt khác nhau, mỗi attempt từ 1 đến 99.", file=sys.stderr)
        return 2
    targets = [args.output_dir / "burst_comparison_average.png"]
    if not args.overwrite and any(path.exists() for path in targets):
        print("Lỗi: hình đã tồn tại; dùng --overwrite để tạo lại.", file=sys.stderr)
        return 1
    try:
        groups = {config: load_profile(args.results_dir.resolve(), "burst", sorted(args.attempts), config)
                  for config in (1, 2, 3)}
        keys = ("workload", "configuration", "resource_window_before_workload_seconds",
                "resource_window_after_workload_seconds")
        reference = groups[1][0].report
        for runs in groups.values():
            for run in runs:
                if any(run.report.get(key) != reference.get(key) for key in keys):
                    raise ValueError(f"{run.run_id}: workload, worker hoặc cửa sổ không khớp")
                value = run.report.get("ready_pod_minutes_approx")
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"{run.run_id}: thiếu ready pod-minutes")
        from e1_plot_charts import burst_comparison_figure, plt
        args.output_dir.mkdir(parents=True, exist_ok=True)
        fig = burst_comparison_figure(groups)
        for target in targets:
            fig.savefig(target, dpi=200)
            print(f"Đã tạo: {target.resolve()}")
        plt.close(fig)
        print("Đã kiểm tra điều kiện đầu có trong mẫu; validity vẫn cần được đánh giá thủ công.")
        return 0
    except ModuleNotFoundError as exc:
        print(f"Thiếu thư viện {exc.name}. Chạy: python -m pip install -r visualize-scripts/requirements.txt",
              file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Không thể tạo biểu đồ: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
