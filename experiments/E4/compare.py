SCENARIO = 'E4'
VARIANTS = ['pod-zero', 'node-zero']
"""So sánh report của cùng kịch bản và điều kiện."""
import argparse, json, math, pathlib, statistics, sys

def show(values,total):
    v=sorted(x for x in values if isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x))
    return f"{statistics.median(v):.2f} [{v[0]:.2f}–{v[-1]:.2f}] ({len(v)}/{total})" if v else f"N/A (0/{total})"
def compare(items):
    if not items:raise ValueError("Cần ít nhất một report")
    keys=("scenario","profile","configuration","idle_window_seconds")
    ref=items[0]
    if ref.get("scenario")!=SCENARIO or any(any(x.get(k)!=ref.get(k) for k in keys) for x in items):raise ValueError("Kịch bản, workload, worker hoặc cửa sổ không khớp")
    schedules=[x.get("cron_schedule") for x in items if x.get("cron_schedule") is not None]
    if schedules and any(x!=schedules[0] for x in schedules):raise ValueError("Cron schedule không khớp")
    if len({x.get("run_id") for x in items})!=len(items):raise ValueError("Run ID bị lặp")
    lines=["# So sánh "+SCENARIO+" — "+ref["profile"],"","Trung vị [min–max] (có dữ liệu / tổng lượt); cần đánh giá từng lượt.","","| Nhánh | Lượt | First job (s) | p95 E2E (s) | Peak backlog | Idle Pod-min |","|---|---:|---:|---:|---:|---:|"]
    for variant in VARIANTS:
        group=[x for x in items if x.get("variant")==variant];n=len(group)
        if n:lines.append("| "+variant+" | "+str(n)+" | "+" | ".join((show([x.get("first_job_completion_seconds") for x in group],n),show([(x.get("e2e_latency_seconds_approx_all_statuses") or {}).get("p95") for x in group],n),show([x.get("peak_visible_plus_inflight_approx") for x in group],n),show([x.get("ready_pod_minutes_idle_approx") for x in group],n)))+" |")
    if any(x.get("variant") not in VARIANTS for x in items):raise ValueError("Variant không hợp lệ")
    lines += ["", "First job đối chiếu theo job ID; histogram gồm error/duplicate; dữ liệu thiếu ghi N/A. Cần kiểm tra điều kiện đầu, cửa sổ và validity."]
    for x in items:lines.append("- "+str(x["run_id"])+": "+str(x.get("warnings",[])))
    return "\n".join(lines)+"\n"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("reports",nargs="+",type=pathlib.Path);a=p.parse_args()
    print(compare([json.loads(x.read_text(encoding="utf-8-sig")) for x in a.reports]),end="")
if __name__=="__main__":
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:main()
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:print(f"Lỗi: {exc}",file=sys.stderr);sys.exit(1)
