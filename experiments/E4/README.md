# E4 — Warm node capacity so với elastic capacity

## Mục tiêu

So sánh giữ sẵn node capacity với provision node theo nhu cầu khi KEDA tăng worker. E4 tương ứng KS4 của NT531; nhánh elastic cũng là đường scale hai tầng của [E3](../E3/README.md). Đây là kế hoạch, không phải kết quả đã đo.

## Các nhánh

| Nhánh | Điều kiện đầu | Mục đích |
|---|---|---|
| A — Warm | Node phù hợp đã Ready, có đủ capacity cho các worker dự kiến. | Đo phản ứng khi không phải chờ tạo node. |
| B — Elastic | Capacity phù hợp không đủ; Karpenter có thể tạo node. | Đo Pending và thời gian provisioning khi tải đến. |

Giữ cùng workload, worker ban đầu, image digest, requests/limits, KEDA settings và loại node/AZ khi khả thi. Ghi khác biệt cache/image pull, capacity và consolidation. Warm **node** không đồng nghĩa giữ sẵn worker pod; pod pre-warming được khảo sát ở [E5](../E5/README.md).

## Chuẩn bị và thực hiện

1. Hoàn thành pilot E0–E3, kiểm tra queue/DLQ, KEDA, Karpenter, quota, subnet và system capacity; chuẩn bị chi phí và cách khôi phục.
2. Trong mỗi terminal, vào `experiments/E4`. Dùng [run.sh của E4](run.sh) và tham khảo [E3 README](../E3/README.md); runbook E4 dùng lại manifest/tài nguyên E3 và bản lưu `../../.generated/e3/`. Mở `run.sh` và chạy từng nhóm lệnh, không chạy cả file.
3. Chuẩn bị một nhánh cho mỗi lượt; ghi node/pod ban đầu, run ID và thời gian UTC. Thu metrics, events, logs và SQS trước khi tạo tải.
4. Phát cùng workload, dừng producer và theo dõi queue drain; lặp ít nhất 3 lượt hợp lệ cho từng nhánh. Có thể dùng lại lượt E3 elastic nếu toàn bộ điều kiện so sánh phù hợp.
5. Khôi phục worker và tài nguyên E3 theo hướng dẫn. Chỉ thu hồi node/NodeClaim sau khi xác nhận đúng phạm vi; việc này có thể chấm dứt EC2.

Nhánh elastic chỉ chứng minh đường scale hai tầng khi quan sát được pod Pending **do thiếu capacity** và node phù hợp được tạo. Đối chiếu cùng pod, NodeClaim và node; mốc thiếu phải ghi `N/A` hoặc proxy.

## Chỉ số và kết quả

Đo throughput, p95/p99 completion latency, peak backlog, drain time, Pending duration, timeline scale, Pod-minutes và node-minutes gồm cả node idle trong cửa sổ đo.

| Run ID | Nhánh | Throughput | p95/p99 | Peak backlog | Pending / node Ready | Pod-minutes | Node-minutes | Hợp lệ? |
|---|---|---:|---|---:|---|---:|---:|---|
| | | | | | | | | |

Tổng hợp trung vị và khoảng của từng nhánh; phân tích đánh đổi theo dữ liệu thay vì giả định trước warm hoặc elastic luôn tốt hơn.
