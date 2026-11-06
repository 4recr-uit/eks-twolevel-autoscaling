SCENARIO = 'E5'
"""Gửi đúng một job, lưu ID để đối chiếu; không tự thử lại khi lỗi."""
import argparse, datetime as dt, json, pathlib, sys, urllib.error, urllib.parse, urllib.request

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True, type=pathlib.Path)
    p.add_argument("--base-url", default="http://127.0.0.1:8082")
    p.add_argument("--work-units", type=int, default=100)
    p.add_argument("--db-mode", choices=("none","light","full"), default="light")
    args=p.parse_args()
    if not 1 <= args.work_units <= 10000: p.error("work-units phải từ 1 đến 10000")
    u=urllib.parse.urlsplit(args.base_url)
    if u.scheme not in ("http","https") or not u.hostname or u.username or u.password or u.query or u.fragment: p.error("base-url không hợp lệ")
    directory=args.run_dir
    metadata=json.loads((directory/"metadata.json").read_text(encoding="utf-8-sig"))
    collection=json.loads((directory/"collection.json").read_text(encoding="utf-8-sig"))
    if metadata.get("scenario") != SCENARIO or collection.get("status") != "collecting": raise ValueError("Sai kịch bản hoặc collector chưa chạy")
    target=directory/"raw/first-job.json"
    record={"scenario":SCENARIO,"state":"sending","sent_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"work_units":args.work_units,"db_mode":args.db_mode}
    with target.open("x",encoding="utf-8") as f: json.dump(record,f,ensure_ascii=False)
    payload=json.dumps({"workUnits":args.work_units,"dbMode":args.db_mode,"batchSize":1,"customerId":"benchmark-"+SCENARIO.lower()}).encode()
    request=urllib.request.Request(args.base_url.rstrip("/")+"/jobs",data=payload,headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body=json.load(response)
            record.update(http_status=response.status,api_status=body.get("status"),job_ids=body.get("jobIds"),enqueued_at_unix_ms=body.get("enqueuedAt"))
            record["state"]="accepted" if response.status == 200 and body.get("status") == "published" and isinstance(body.get("jobIds"),list) and len(body["jobIds"]) == 1 else "not_confirmed"
    except (OSError,ValueError,urllib.error.URLError) as exc:
        record.update(state="unknown",error=str(exc)[:300])
    record["response_at_utc"]=dt.datetime.now(dt.timezone.utc).isoformat()
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(record,ensure_ascii=False,indent=2))
    return 0 if record["state"]=="accepted" else 2

if __name__ == "__main__":
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    try: sys.exit(main())
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
        print(f"Không gửi job: {exc}",file=sys.stderr); sys.exit(1)
