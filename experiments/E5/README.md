# E5 — Cold start và pod pre-warming

## Mục tiêu

So sánh thời gian xử lý job đầu tiên và tài nguyên idle giữa worker scale-to-zero và worker được giữ sẵn theo lịch. E5 trong danh sách chung tương ứng E4 của báo cáo NT533. Đây là thiết kế, chưa có manifest Cron hoặc script E5 được triển khai và chưa có kết quả đo.

## Cấu hình so sánh

| Nhánh | Thiết lập dự kiến |
|---|---|
| A — Cold | KEDA `min=0`, không Cron; có thể dùng lại lượt [E2](../E2/README.md) nếu workload, node và cửa sổ đo phù hợp. |
| B — Warm 1 | Cấu hình Cron giữ tối thiểu một worker trong cửa sổ đã định. |
| C — Warm 2 | Cấu hình Cron giữ tối thiểu hai worker trong cửa sổ đã định. |

Giữ sẵn node capacity trong cả ba nhánh để tách pod startup khỏi node provisioning. Cố định image digest, requests/limits, node, queue, database, workload, SQS trigger, Cron timezone/lịch và cửa sổ đo. Không tạo CPU-HPA độc lập cùng điều khiển worker với KEDA; Cron phải được thiết kế cùng ScaledObject thay vì tạo bộ điều khiển cạnh tranh.

## Thực hiện dự kiến

1. Chuẩn bị cấu hình riêng và cách khôi phục; kiểm tra queue/DLQ, IAM và monitoring. Dừng nếu đã có autoscaler khác điều khiển Orders.
2. Với mỗi nhánh, xác nhận node ổn định và số worker ban đầu đúng; ghi thời điểm, cấu hình và run ID.
3. Sau giai đoạn idle xác định trước, gửi job đầu tiên, đối chiếu job ID và ghi thời điểm gửi, pod Ready và hoàn thành. Sau đó tạo cùng workload trong các nhánh.
4. Dừng tải, theo dõi queue drain và worker; lưu logs/events, SQS, Prometheus và kết quả producer. Lặp ít nhất 3 lượt hợp lệ mỗi nhánh.
5. Khôi phục cấu hình và số replica ban đầu, xác nhận không còn tài nguyên thí nghiệm ngoài ý muốn.

## Chỉ số và kết quả

Đo first-job completion latency, p95/p99 completion latency ở giai đoạn đầu, peak backlog, throughput, pod Ready, Pod-minutes idle và chi phí compute ước tính. Nêu nguồn và độ phân giải timestamp; ghi `N/A` nếu thiếu mốc. Histogram percentiles là ước lượng và có thể thiếu chính xác khi số mẫu nhỏ.

| Run ID | Nhánh | Worker ban đầu | First-job latency | p95/p99 | Peak backlog | Idle Pod-minutes | Ghi chú / hợp lệ? |
|---|---|---:|---:|---|---:|---:|---|
| | | | | | | | |

Phân tích đánh đổi latency và idle capacity theo dữ liệu; không mặc định giữ sẵn worker luôn tốt hơn.
