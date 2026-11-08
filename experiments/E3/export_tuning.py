#!/usr/bin/env python3
"""Export the documented E3 tuning queries through Prometheus's read-only API."""

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


DEFAULT_TIME = 1794047517
QUERY_FILE = Path(__file__).with_name("TUNING-QUERIES.md")
ROOT = Path(__file__).resolve().parents[2]


def utc(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


def read_queries(path):
    pattern = (r"^## (Q\d+) — ([^\n]+)\n\n"
               r"Đơn vị/diễn giải: ([^\n]+)\n\n```promql\n(.*?)\n```")
    matches = re.findall(pattern, path.read_text(encoding="utf-8"), re.M | re.S)
    if [item[0] for item in matches] != [f"Q{i:02d}" for i in range(1, 19)]:
        raise ValueError("File hướng dẫn phải có đủ Q01–Q18, đúng thứ tự và định dạng.")
    return [{"id": ident, "title": title, "unit": unit.rstrip("."), "query": query}
            for ident, title, unit, query in matches]


def query_api(base_url, query, evaluation_time, timeout):
    params = urllib.parse.urlencode({"query": query, "time": evaluation_time})
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/v1/query?" + params,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"status": "error", "error": body[:4000] or str(exc)}
        data["http_status"] = exc.code
    if not isinstance(data, dict):
        raise ValueError("Prometheus không trả JSON object.")
    return data


def save_json(path, payload):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def markdown(payload):
    lines = ["# Kết quả PromQL tuning E3", "",
             f"- Thời điểm đánh giá UTC: {payload['evaluation_time_utc']}",
             f"- Unix timestamp: {payload['evaluation_time_unix']}",
             f"- Cửa sổ rate/latency: {payload['rate_window_seconds']} giây trước mốc đánh giá.",
             f"- Trạng thái xuất: {payload['status']}", "",
             "Các giá trị là snapshot lịch sử, không phải báo cáo toàn lượt hoặc năng lực bão hòa. "
             "Empty/NaN/Inf được giữ nguyên; không tự chuyển thành 0. "
             "Xem results.json để lấy đầy đủ PromQL, nhãn, cảnh báo và phản hồi gốc.", ""]
    for result in payload["queries"]:
        lines += [f"## {result['id']} — {result['title']}", "", result["unit"], ""]
        if result["export_status"] == "error":
            error = json.dumps(result.get("response", result.get("error")), ensure_ascii=False)
            lines += ["Lỗi: " + error, ""]
            continue
        data = result["response"]["data"]["result"]
        if not data:
            lines += ["Empty query result", ""]
            continue
        lines += ["| Nhãn | Giá trị | Timestamp mẫu UTC |", "|---|---:|---|"]
        for series in data:
            labels = json.dumps(series.get("metric", {}), ensure_ascii=False, sort_keys=True)
            labels = labels.replace("|", "\\|")
            timestamp, value = series["value"]
            lines.append(f"| `{labels}` | {value} | {utc(float(timestamp))} |")
        lines.append("")
        if result["response"].get("warnings") or result["response"].get("infos"):
            lines += ["Prometheus annotations: " + json.dumps(
                {k: result["response"][k] for k in ("warnings", "infos") if k in result["response"]},
                ensure_ascii=False), ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus", default="http://127.0.0.1:9090")
    parser.add_argument("--time", default=str(DEFAULT_TIME),
                        help="Unix timestamp chung cho 18 query, hoặc 'now'; mặc định là mốc E3 đã kiểm tra")
    parser.add_argument("--output", type=Path, help="thư mục mới; từ chối ghi đè thư mục đã có")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        parsed = urllib.parse.urlsplit(args.prometheus)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Dùng URL Prometheus HTTP(S) không chứa credential/query.")
        evaluation_time = int(time.time()) if args.time == "now" else int(args.time)
        evaluation_time_utc = utc(evaluation_time)
        if args.timeout <= 0:
            raise ValueError("Timeout phải lớn hơn 0.")
        queries = read_queries(QUERY_FILE)
        output = args.output or ROOT / ".generated/e3" / (
            "tuning-export-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-" + uuid.uuid4().hex[:8])
        output = output.expanduser().resolve()
        output.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError, OverflowError) as exc:
        parser.error(str(exc))
    payload = {"schema_version": 1, "status": "collecting", "started_at_utc": utc(time.time()),
               "prometheus_url": args.prometheus, "evaluation_time_unix": evaluation_time,
               "evaluation_time_utc": evaluation_time_utc, "rate_window_seconds": 120,
               "query_source": str(QUERY_FILE.resolve()), "queries": []}
    result_file = output / "results.json"
    save_json(result_file, payload)
    print("Đang xuất tại:", output, flush=True)
    for definition in queries:
        result = dict(definition)
        # Re-pin all selectors to one instant, including both sides of ratios.
        result["query"] = re.sub(r"@\s*\d+(?:\.\d+)?", f"@ {evaluation_time}", result["query"])
        try:
            response = query_api(args.prometheus, result["query"], evaluation_time, args.timeout)
            result["response"] = response
            if response.get("status") != "success":
                result["export_status"] = "error"
            elif response.get("data", {}).get("resultType") != "vector":
                result["export_status"] = "error"
                result["error"] = "Query yêu cầu kết quả instant vector."
            else:
                series = response["data"]["result"]
                result["series_count"] = len(series)
                result["export_status"] = "ok" if series else "empty"
        except (OSError, ValueError, TimeoutError) as exc:
            result["export_status"] = "error"
            result["error"] = str(exc)
        payload["queries"].append(result)
        save_json(result_file, payload)
        print(result["id"], result["export_status"],
              f"({result['series_count']} series)" if "series_count" in result else "", flush=True)
    errors = sum(q["export_status"] == "error" for q in payload["queries"])
    payload["status"] = "partial" if errors else "finished"
    payload["ended_at_utc"] = utc(time.time())
    payload["summary"] = {status: sum(q["export_status"] == status for q in payload["queries"])
                          for status in ("ok", "empty", "error")}
    save_json(result_file, payload)
    (output / "summary.md").write_text(markdown(payload), encoding="utf-8")
    print("Kết quả:", result_file)
    print("Bảng đọc nhanh:", output / "summary.md")
    print("Thống kê:", json.dumps(payload["summary"]))
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
