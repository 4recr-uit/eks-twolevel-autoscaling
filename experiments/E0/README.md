# E0 — Worker capacity calibration và workload modeling

## Mục tiêu

Ước lượng throughput thành công của một worker khi có đủ việc, rồi dùng kết quả làm cơ sở chọn tải Steady, Step và Burst cho các pilot tiếp theo. E0 là bước chuẩn bị, không so sánh autoscaler. Chưa có kết quả thực nghiệm; dùng bộ công cụ trong [_shared](../_shared/README.md) để tạo hồ sơ và thu dữ liệu.

## Phạm vi và điều kiện

- Bắt đầu với `orders-worker` và `orders-queue`; xác nhận không có consumer khác đọc queue.
- Không có HPA hoặc ScaledObject điều khiển Orders, giữ đúng một worker Ready và node capacity ổn định.
- Ghi image digest, node type, CPU/memory requests và limits, worker concurrency, SQS polling/batch, `workUnits`, `dbMode` và batch size. Giữ chúng cố định trong từng nhóm so sánh.
- Kiểm tra metric worker, Prometheus/Grafana, SQS/CloudWatch, queue và DLQ trước khi chạy. Không purge hoặc xóa message ngoài phạm vi thí nghiệm.
- Lưu cấu hình và replica ban đầu; chuẩn bị cách khôi phục trước khi đổi deployment. Workload `dbMode=light` ghi dữ liệu thử vào database.

## Quy trình đề xuất

1. Xác định mức tải thấp; chạy khoảng 2–3 phút và đo số job thực tế được chấp nhận, task thành công/lỗi, CPU/memory và backlog.
2. Dừng producer, tiếp tục thu dữ liệu đến khi queue drain theo tiêu chí đã định. Kiểm tra lỗi, retries và DLQ.
3. Lặp ở khoảng 3–5 mức tải tăng dần, hoặc thêm mức khi chưa tìm được vùng bão hòa. Dừng và điều tra khi producer, database hoặc worker gặp lỗi hay giới hạn ngoài dự kiến.
4. Khi có backlog liên tục và throughput thành công gần ổn định, chọn mức đại diện và chạy 3 lượt độc lập. Ghi cửa sổ đo ổn định, trung vị và khoảng min–max.
5. Dùng khoảng throughput đo được (`μ`) để đề xuất workload cho E1–E3, rồi pilot. `λ/μ` chỉ là ước lượng ban đầu; nhiều worker có thể không scale tuyến tính và KEDA dựa trên queue, không trực tiếp trên λ/μ.
6. Lưu cấu hình, thời gian UTC, kết quả producer, metrics và logs; khôi phục worker và xác nhận trạng thái ban đầu.

Workload hiện có ở [E1/workload.js](../E1/workload.js) tính tốc độ theo **request/s**. Số task được chấp nhận còn phụ thuộc batch size và kết quả từng request. SQS backlog là xấp xỉ; Prometheus counters không thay thế đối soát job ID. Nếu không thấy plateau hoặc không đủ mẫu đáng tin cậy, ghi `μ: chưa xác định`.

## Cách chạy

1. Terminal 1: mở Prometheus và giữ terminal chạy:
```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090
```
2. Terminal 2: bắt đầu thu vào đúng thư mục đã init:
```bash
python experiments/_shared/collect.py --run-dir experiments/results/E0/E0-single-worker-step-r01
```
3. Chờ dòng ĐANG THU, lấy khoảng 15–30 giây baseline, rồi chạy k6 ở terminal 3. Lệnh k6 cần xuất summary vào:
```bash
experiments/results/E0/E0-single-worker-step-r01/raw/k6-summary.json
```
4. Khi tải dừng và queue drain, nhấn Ctrl+C một lần ở terminal 2. Chờ thông báo Đã lưu; script sẽ lấy mẫu cuối, xuất Prometheus và lưu log/snapshot.
5. Mở collection-summary.md trước, kiểm tra cảnh báo rồi đối chiếu các file trong metrics/, events/, logs/ và kết quả k6 để điền bảng E0.
Script ghi thời gian thu trong collection.json, giữ nguyên metadata.json và notes.md. Bạn cần ghi riêng thời gian các pha workload để tính throughput ở đúng đoạn ổn định. Trạng thái thu finished chưa tự chứng minh lượt hợp lệ hay xác định được μ.

## Thu và lưu dữ liệu

Tạo hồ sơ bằng `_shared/run.py init`, mở port-forward Prometheus và chạy [_shared/collect.py](../_shared/collect.py) với `--run-dir` trỏ đến hồ sơ. Chờ **ĐANG THU** trước khi phát tải; k6 xuất summary vào `raw/k6-summary.json` của lượt đó. Sau khi dừng producer và queue drain, nhấn Ctrl+C ở collector và chờ xuất xong. Lệnh đầy đủ và ý nghĩa từng file ở [mục 7 của hướng dẫn dùng chung](../_shared/README.md#7-thu-dữ-liệu-e0-bằng-collectpy).

Kiểm tra `collection-summary.md`, cảnh báo/lỗi và các file trong `metrics/`, `events/`, `logs/`; ghi thời gian workload, cấu hình và đánh giá hợp lệ trước khi điền bảng. Cửa sổ thu gồm baseline/drain, không tự động là cửa sổ tính μ. Lượt `step` có thể dùng thăm dò; các lượt xác nhận năng lực ở một mức tải nên dùng `steady` và phân tích phần ổn định.

## Kết quả

| Run ID | Tải dự kiến / accepted task/s | Throughput thành công | Peak visible / in-flight | CPU | Lỗi / retry / DLQ | Hợp lệ? |
|---|---|---|---|---|---|---|
| | | | | | | |

| Cấu hình đo | Khoảng μ / trung vị | Mức Steady | Mức Step | Mức Burst | Giới hạn và ghi chú |
|---|---|---|---|---|---|
| | | | | | |

Các bảng là mẫu để điền sau pilot; các con số không được suy ra trước khi đo.
