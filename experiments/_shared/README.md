# Quy ước dùng chung cho E0–E5

E0 và E1 có bộ công cụ độc lập trong [E0](../E0/README.md) và [E1](../E1/README.md); dùng runbook tương ứng cho các lượt mới. Các lệnh E0 bên dưới là bộ cũ được giữ để tương thích với dữ liệu/quy trình trước đây.

Thư mục này hỗ trợ cấu hình mục tiêu, tạo hồ sơ và kiểm tra trạng thái. `collect.py` chỉ thu dữ liệu E0; các công cụ không phát tải, thay đổi replica, apply manifest hay khôi phục cluster. Xem runbook từng kịch bản để thực hiện những bước đó.

## 1. Chuẩn bị

Chạy trong thư mục của kịch bản, ví dụ `experiments/E0`, trong Git Bash. Cần Python 3.10+, `kubectl` và các công cụ trong runbook; collector E0 cần thêm AWS CLI. `inspect` cần quyền đọc namespace, Deployment, HPA và ScaledObject.

```bash
cp -n ../_shared/config.example.sh ../_shared/config.local.sh
```

Mở `config.local.sh`, kiểm tra và sửa context, namespace, Deployment, **tên** queue và region, rồi nạp:

```bash
source ../_shared/config.local.sh
```

Các giá trị mẫu không chứng minh tài nguyên đã tồn tại; `cp -n` giữ file cũ nếu có. Không lưu credential, Secret, kubeconfig hoặc dữ liệu nhạy cảm trong cấu hình, metadata hay kết quả.

## 2. Kiểm tra mục tiêu

```bash
python ../_shared/run.py inspect \
  --context "$EXPERIMENT_CONTEXT" \
  --namespace "$EXPERIMENT_NAMESPACE" \
  --deployment "$EXPERIMENT_DEPLOYMENT"
```

Lệnh chỉ đọc desired/ready replicas và các HPA/ScaledObject cùng target, kể cả HPA do KEDA tạo. Lỗi kết nối, quyền hoặc thiếu CRD không có nghĩa là không có controller. Kiểm tra thêm queue/DLQ, node capacity, scheduling, image, database, IAM, monitoring và quota theo runbook; lưu baseline và chuẩn bị cách khôi phục trước khi thay đổi tài nguyên.

## 3. Tạo hồ sơ từng lượt

Ví dụ lượt E0, một worker, steady, lần 1:

```bash
python ../_shared/run.py init \
  --scenario E0 --variant single-worker --profile steady --attempt 1 \
  --context "$EXPERIMENT_CONTEXT" --namespace "$EXPERIMENT_NAMESPACE" \
  --deployment "$EXPERIMENT_DEPLOYMENT" --queue "$EXPERIMENT_QUEUE" \
  --region "$EXPERIMENT_AWS_REGION"
```

Lệnh tạo `../results/E0/E0-single-worker-steady-r01/`. Mỗi lượt dùng attempt mới; lệnh không ghi đè hồ sơ đã tồn tại. Variant/profile dùng chữ thường, số và dấu `-`; attempt từ 1 đến 999. Mỗi tổ hợp cần tối thiểu ba lượt hợp lệ theo thiết kế.

- `metadata.json`: mục tiêu, commit, thời điểm chuẩn bị và trạng thái đánh giá.
- `notes.md`: cấu hình, thời gian các pha, nguồn dữ liệu và lý do đánh giá.
- `raw/`, `metrics/`, `events/`, `logs/`: summary k6 và dữ liệu quan sát.

`prepared_at_utc` không phải lúc bắt đầu workload. Sau lượt, tự điền `started_at_utc`, `ended_at_utc` và `validity` (`valid`, `invalid` hoặc `not_assessed`) vào metadata. `dirty` chỉ báo repo hạ tầng có thay đổi chưa commit, không lưu nội dung thay đổi hay commit backend.

`experiments/results/` bị Git bỏ qua: sao lưu riêng nếu cần và rà soát dữ liệu vận hành trước khi chia sẻ. Nếu dùng `--results-dir`, tự bảo đảm nơi lưu phù hợp và không bị commit nhầm.

## 4. Quy trình mỗi lượt

1. Kiểm tra điều kiện đầu, lưu baseline và ghi cấu hình thực tế, image digest, commit hạ tầng/backend, workload, tiêu chí drain và các mốc UTC.
2. Phát tải theo runbook, lưu k6 summary và ghi accepted jobs, lỗi gửi, partial failure và `dropped_iterations`. Request/s không mặc định bằng task/s; HTTP latency không phải completion latency.
3. Thu SQS visible/in-flight/delayed, Prometheus, replica, node, events và log theo yêu cầu của kịch bản. SQS là ước lượng; kiểm tra nhiều mẫu và đối chiếu accepted/success/error/duplicate/DLQ và job ID khi có thể. Ghi `N/A` hoặc proxy kèm giới hạn khi thiếu dữ liệu.
4. Dừng producer, chờ drain theo tiêu chí đã chọn, đánh giá lượt và lưu dữ liệu. Không purge queue để làm sạch kết quả.
5. Khôi phục theo baseline và runbook; kiểm tra lại Deployment, replica, autoscaler và node. Giữ baseline và dữ liệu nếu khôi phục thất bại.

Với Orders benchmark, `enqueuedAt` được tạo trước khi gửi SQS, nên chỉ là mốc gần đúng. Histogram percentile là ước lượng; log của một Deployment không đảm bảo bao phủ mọi pod đã biến mất.

## 5. Vai trò các kịch bản

E0 hiệu chuẩn μ và workload; E1 so Fixed/HPA/KEDA; E2 đo 0→N→0; E3 đo KEDA + Karpenter; E4 so warm/elastic **Node**; E5 so cold/pre-warm **Pod**. Chỉ dùng lại lượt E3 cho E4 hoặc E2 cho E5 khi điều kiện và cửa sổ đo phù hợp, đồng thời ghi run ID nguồn.

## 6. Kiểm tra cục bộ

```bash
python -m unittest discover -s tests -p 'test_experiment*.py'
```

Test dùng dữ liệu giả, không thay thế kiểm tra thực tế trên AWS/EKS.

## 7. Thu dữ liệu E0 bằng collect.py

Collector đọc target từ `metadata.json` và kiểm tra một worker Ready, không có HPA/ScaledObject cùng target, queue/DLQ rỗng và target Prometheus UP. Vẫn cần xác nhận không có producer/consumer khác. Collector chỉ đọc SQS attributes, không receive/delete/purge message.

**Terminal 1:** mở và giữ Prometheus port-forward:

```bash
kubectl --context twolevel-dev -n monitoring port-forward \
  service/monitoring-kube-prometheus-prometheus 9090:9090
```

**Terminal 2:** dùng đúng thư mục đã init; `--check` chỉ kiểm tra, không thu:

```bash
RUN_DIR='../results/E0/E0-single-worker-steady-r01'
python ../_shared/collect.py --run-dir "$RUN_DIR" --check
python ../_shared/collect.py --run-dir "$RUN_DIR"
```

Chờ **ĐANG THU**, lấy 15–30 giây baseline, rồi chạy workload ở terminal khác; đặt lại `RUN_DIR` trong terminal đó và xuất k6 summary vào `$RUN_DIR/raw/k6-summary.json`. Ghi UTC bắt đầu/kết thúc workload và các pha vào `notes.md`. Dùng lượt `steady` riêng để xác nhận μ; `step` dùng thăm dò và cần phân tích từng pha.

Sau khi producer dừng, tiếp tục thu đến khi drain: kiểm tra nhiều mẫu visible/in-flight/delayed bằng 0, DLQ và kết quả job. Nhấn **Ctrl+C một lần** ở terminal collector và chờ thoát; script thu thêm phần đuôi mặc định 10 giây, xuất metric, snapshot và log. Không đóng cửa sổ hay kill process giữa lúc hoàn tất.

Mở `collection-summary.md` trước, rồi kiểm tra `collection.json`, `raw/k6-summary.json`, `metrics/`, `events/` và `logs/`. Collector lấy mẫu khoảng 5 giây/lần, nhưng các nguồn không đồng thời; log chỉ được lấy lúc kết thúc và có thể thiếu nếu pod biến mất hoặc restart. `--prometheus-url` đổi endpoint; `--duration` giới hạn thời gian smoke test và không chạy k6.

`finished` chỉ xác nhận kết thúc thu, không xác nhận lượt hợp lệ hay tính μ. `partial` và mã thoát 2 báo nguồn lỗi: xem `logs/collect-errors.jsonl`. Không thay dữ liệu thiếu bằng 0; giữ dữ liệu và init attempt mới nếu cần chạy lại. Collector không dùng lại thư mục đã có `collection.json` hoặc `collect-*`.

Cửa sổ thu gồm baseline và drain, không phải cửa sổ tính throughput bão hòa. Prometheus `query_range` là các mẫu đánh giá biểu thức, không phải scrape thô; đối chiếu counter, reset/retry, histogram và job ID theo đúng cửa sổ workload. Điền bảng kết quả E0 sau khi đánh giá các lượt.
