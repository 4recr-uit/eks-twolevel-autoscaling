# PromQL hỗ trợ tuning HPA/KEDA

Đã tự xuất và phân tích dữ liệu lịch sử ngày 08/11/2026:
[TUNING-ANALYSIS.md](TUNING-ANALYSIS.md).

Xuất cả 18 query thành một file JSON, từ thư mục gốc repo:

```bash
python experiments/E3/export_tuning.py
```

Script đọc chính các query trong tài liệu này, chỉ truy cập HTTP API đọc của
Prometheus tại `http://127.0.0.1:9090`. Mỗi lần tạo thư mục mới trong
`.generated/e3/tuning-export-*`, gồm `results.json` và `summary.md`. Gửi lại
`results.json` là đủ; file giữ query, nhãn, đơn vị, timestamp, cảnh báo và phản hồi gốc.
Nếu có lỗi kết nối/query, script vẫn giữ kết quả đã thu và báo `partial`.

Đổi thời điểm chung bằng `--time UNIX_TIMESTAMP`, hoặc `--time now` khi đang chạy
pilot mới. Nếu đang đứng trong `experiments/E3`, dùng `python ./export_tuning.py`.

Dùng tab Table. Tất cả query cố định tại Unix timestamp 1794047517, tức 17:31:57 ngày 07/11/2026 (UTC+7), thuộc E3-keda-step-r01. Các rate/latency dùng cửa sổ 2 phút trước mốc này. Đây là cửa sổ tải thay đổi, không phải phép đo năng lực bão hòa ổn định và không thay các report toàn lượt.

Mỗi query gửi lại theo ID Q01…Q18, giữ nguyên tên Pod/nhãn. Nếu Empty, NaN hoặc Inf, ghi đúng trạng thái đó; không thay bằng 0. Muốn dùng pilot mới: bỏ mọi `@ 1794047517` hoặc thay tất cả bằng cùng timestamp khác. Dùng Graph với timestamp cố định sẽ cho đường ngang; muốn xem diễn biến, bỏ @ và chọn khoảng lịch sử trên UI.

## Q01 — Tốc độ published vào queue

Đơn vị/diễn giải: job/s; trung bình 2 phút.

```promql
sum(rate(app_sqs_messages_published_total{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
```

## Q02 — Throughput success mỗi Pod

Đơn vị/diễn giải: job/s mỗi Pod.

```promql
sum by (pod) (rate(worker_tasks_processed_total{namespace="retailstore",queue="orders-queue",status="success"}[2m] @ 1794047517))
```

## Q03 — Throughput theo status

Đơn vị/diễn giải: job/s theo status; status chưa có series không được tự coi là 0.

```promql
sum by (status) (rate(worker_tasks_processed_total{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
```

## Q04 — CPU mỗi Pod

Đơn vị/diễn giải: millicore; 1000m = 1 lõi.

```promql
1000 * sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="retailstore",pod=~"orders-worker-.*",container="orders-worker"}[2m] @ 1794047517))
```

## Q05 — CPU sử dụng so với request

Đơn vị/diễn giải: %; tham khảo từ cAdvisor, không phải chính metric CPU mà HPA đọc từ metrics-server.

```promql
100 * sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="retailstore",pod=~"orders-worker-.*",container="orders-worker"}[2m] @ 1794047517))
/
sum by (pod) (kube_pod_container_resource_requests{namespace="retailstore",container="orders-worker",resource="cpu",unit="core"} @ 1794047517)
```

## Q06 — CPU trên mỗi job thành công

Đơn vị/diễn giải: CPU-giây/job mỗi Pod; có cả chi phí chung của worker.

```promql
sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="retailstore",pod=~"orders-worker-.*",container="orders-worker"}[2m] @ 1794047517))
/
sum by (pod) (rate(worker_tasks_processed_total{namespace="retailstore",queue="orders-queue",status="success"}[2m] @ 1794047517))
```

## Q07 — Thời gian xử lý trung bình mỗi Pod

Đơn vị/diễn giải: giây.

```promql
sum by (pod) (rate(worker_task_duration_seconds_sum{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
/
sum by (pod) (rate(worker_task_duration_seconds_count{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
```

## Q08 — Thời gian chờ trước xử lý trung bình mỗi Pod

Đơn vị/diễn giải: giây; tính từ timestamp trước khi gửi SQS.

```promql
sum by (pod) (rate(worker_job_queue_wait_seconds_sum{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
/
sum by (pod) (rate(worker_job_queue_wait_seconds_count{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
```

## Q09 — p95 E2E của nhóm worker

Đơn vị/diễn giải: giây; histogram tổng hợp các Pod, không phải trung bình p95 từng Pod.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(worker_job_e2e_latency_seconds_bucket{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
)
```

## Q10 — p99 E2E của nhóm worker

Đơn vị/diễn giải: giây.

```promql
histogram_quantile(
  0.99,
  sum by (le) (rate(worker_job_e2e_latency_seconds_bucket{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
)
```

## Q11 — p95 thời gian xử lý

Đơn vị/diễn giải: giây.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(worker_task_duration_seconds_bucket{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
)
```

## Q12 — p95 thời gian chờ trước xử lý

Đơn vị/diễn giải: giây.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(worker_job_queue_wait_seconds_bucket{namespace="retailstore",queue="orders-queue"}[2m] @ 1794047517))
)
```

## Q13 — Desired replicas

Đơn vị/diễn giải: Pod tại mốc lịch sử.

```promql
kube_deployment_spec_replicas{namespace="retailstore",deployment="orders-worker"} @ 1794047517
```

## Q14 — Ready replicas

Đơn vị/diễn giải: Pod tại mốc lịch sử.

```promql
kube_deployment_status_replicas_ready{namespace="retailstore",deployment="orders-worker"} @ 1794047517
```

## Q15 — Worker Pending

Đơn vị/diễn giải: số Pod; mẫu tức thời có thể bỏ qua Pending ngắn.

```promql
sum(kube_pod_status_phase{namespace="retailstore",pod=~"orders-worker-.*",phase="Pending"} @ 1794047517)
```

## Q16 — Worker nằm trên node nào

Đơn vị/diễn giải: số Pod theo node; không phải tổng node trong NodePool.

```promql
count by (node) (kube_pod_info{namespace="retailstore",pod=~"orders-worker-.*",node!=""} @ 1794047517)
```

## Q17 — Tình trạng scrape worker

Đơn vị/diễn giải: 1 = scrape thành công; 0 = scrape lỗi.

```promql
up{namespace="retailstore",pod=~"orders-worker-.*",job="orders-worker"} @ 1794047517
```

## Q18 — Số mẫu counter trong cửa sổ

Đơn vị/diễn giải: số mẫu mỗi Pod; ít hơn 2 không đủ tính rate.

```promql
count_over_time(worker_tasks_processed_total{namespace="retailstore",queue="orders-queue",status="success"}[2m] @ 1794047517)
```

## Phần cần dữ liệu khác

- Tổng node E3: kube_node_labels không có dữ liệu tại mốc đã chọn. Q16 chỉ cho biết node đang chứa worker, không đếm node trống. Dùng events/collect-topology-samples.jsonl để đếm toàn bộ e3-orders.
- Backlog/DLQ: bộ thu E3 lưu trực tiếp SQS trong metrics/collect-sqs-samples.jsonl; không suy backlog từ throughput hoặc số job in-flight của worker.
- HTTP latency: lấy từ raw/k6-summary.json, khác E2E job.
- Độ trễ tăng Pod/node: xem chuỗi thời gian raw; một snapshot không đủ đo phản ứng.
- Histogram có nội suy và counter có thể thiếu đầu/cuối series khi Pod thay đổi. Trung bình xử lý không được đảo ngược thành năng lực tối đa mà bỏ qua polling/nhận message hoặc CPU contention.
- Nếu không có counter cho error/duplicate, Q03 chỉ hiện success; điều này chưa chứng minh error/duplicate bằng 0 theo đối soát job ID.

Tài liệu: [Prometheus @ modifier](https://prometheus.io/docs/prometheus/latest/querying/basics/#-modifier), [rate/histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/).
