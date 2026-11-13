#!/usr/bin/env python3
"""Draw E1 figures using local reports and collector samples."""

import argparse
from pathlib import Path
import sys

from e1_plot_data import PROFILES, load_profile


def parse_args():
    e1 = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Vẽ biểu đồ Warm/Elastic E1 từ dữ liệu cục bộ")
    parser.add_argument("--results-dir", type=Path, default=e1.parent / "results" / "E1",
                        help="thư mục chứa các lượt E1")
    parser.add_argument("--output-dir", type=Path,
                        help="thư mục lưu hình; mặc định figures/config-N")
    parser.add_argument("--config", type=int, choices=(1, 2, 3), default=1,
                        help="cấu hình E1 cần vẽ; mặc định 1")
    parser.add_argument("--profile", choices=("all", *PROFILES), default="all")
    parser.add_argument("--attempts", type=int, nargs="+", default=[1, 2], metavar="N",
                        help="các lượt ở cả hai nhánh; mặc định 1 2")
    parser.add_argument("--overwrite", action="store_true", help="cho phép ghi đè hình đã tồn tại")
    return parser.parse_args()


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args()
    if (not args.attempts or len(args.attempts) > 4 or len(set(args.attempts)) != len(args.attempts)
            or any(n <= 0 or n > 99 for n in args.attempts)):
        print("Lỗi: chọn 1–4 attempt khác nhau, mỗi attempt từ 1 đến 99.", file=sys.stderr)
        return 2
    attempts = sorted(args.attempts)
    profiles = PROFILES if args.profile == "all" else (args.profile,)
    e1 = Path(__file__).resolve().parent.parent
    output = (args.output_dir or e1 / "figures" / f"config-{args.config}").resolve()
    targets = [output / f"{profile}_{kind}.png" for profile in profiles
               for kind in ("summary", "timeline")]
    if args.profile == "all":
        targets.append(output / "conclusion_average.png")
    existing = [str(path) for path in targets if path.exists()]
    if existing and not args.overwrite:
        print("Lỗi: hình đã tồn tại; dùng --overwrite để tạo lại:\n" + "\n".join(existing), file=sys.stderr)
        return 1
    try:
        # Validate every selected run before writing any output.
        groups = {profile: load_profile(args.results_dir.resolve(), profile, attempts, args.config) for profile in profiles}
        from e1_plot_charts import plt, summary_figure, timeline_figure, conclusion_figure
        output.mkdir(parents=True, exist_ok=True)
        for profile, runs in groups.items():
            for kind, fig in (("summary", summary_figure(profile, runs)),
                              ("timeline", timeline_figure(profile, runs, attempts))):
                destination = output / f"{profile}_{kind}.png"
                fig.savefig(destination, dpi=200)
                print(f"Đã tạo: {destination}")
                plt.close(fig)
        if args.profile == "all":
            fig = conclusion_figure(groups)
            destination = output / "conclusion_average.png"
            fig.savefig(destination, dpi=200)
            print(f"Đã tạo: {destination}")
            plt.close(fig)
        print("Đã kiểm tra điều kiện đầu có trong mẫu; validity của lượt vẫn cần được đánh giá thủ công.")
        return 0
    except ModuleNotFoundError as exc:
        print(f"Thiếu thư viện {exc.name}. Chạy: python -m pip install -r visualize-scripts/requirements.txt",
              file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Không thể tạo biểu đồ: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
