# E4 — Queue Target Sensitivity

## Mục tiêu

Đánh giá ảnh hưởng của `queueLength` trong KEDA đến backlog, latency và tài nguyên worker.

## Thiết kế

So sánh ba mức queue target: **5**, **10** và **20 message/worker**. Các nhánh dùng cùng workload, cấu hình worker, node capacity và giới hạn 1–10 worker.

Các chỉ số chính gồm số worker, peak backlog, thời gian queue drain, p95 latency, throughput và Pod-phút.

## Cấu hình và workload

- KEDA có polling 30 giây, cooldown 300 giây; worker yêu cầu 500m CPU và 256Mi memory. NodePool `e4-orders` dùng On-Demand và giữ node với `consolidateAfter: Never`.
- Workload đã thực hiện là Step 5 → 10 → 15 → 20 → 15 → 10 → 5 request/s, mỗi bậc 1 phút.
- Với `minReplicaCount=1`, không có `idleReplicaCount` hoặc cached metrics, polling/cooldown không điều khiển scale thông thường; HPA dùng metric KEDA để scale. CPU request khác E0 nên throughput có thể thay đổi.

## Kết quả

### Step v4 — một lượt mỗi mức

Mỗi lượt dùng Step 5 → 10 → 15 → 20 → 15 → 10 → 5 request/s, mỗi bậc 60 giây; batch size 1, `workUnits=100`, `dbMode=light` và concurrency 1. Cả ba lượt dùng cùng image, bốn node On-Demand `c7i-flex.large` và worker request 500m/256Mi; bắt đầu với một worker Ready và queue/DLQ rỗng.

| Chỉ số | q-low = 5 | q-medium = 10 | q-high = 20 |
|---|---:|---:|---:|
| Accepted / request lỗi | 4.799 / 0 | 4.799 / 0 | 4.799 / 0 |
| Replica desired/ready cao nhất quan sát được | 9/9 | 6/6 | 3/3 |
| Peak backlog visible + in-flight ≈ | 26 | 51 | 43 |
| p95 E2E ≈ (giây) | 0,572 | 1,659 | 1,344 |
| Throughput thành công trong workload ≈ (job/s) | 11,12 | 11,16 | 11,25 |
| Ready Pod-phút ≈ | 45,7 | 33,0 | 18,5 |
| Xác nhận drain đầu tiên sau tải ≈ (giây) | 99,0 | 92,3 | 117,1 |
| CPU worker trung bình cộng các Pod ≈ (core) | 1,14 | 1,13 | 1,15 |
| Node-phút Kubernetes ≈ | 36,01 | 36,00 | 36,00 |
| Chạm max=10 theo mẫu | Không | Không | Không |

Trong các lượt đo, target tăng từ 5 lên 20 đi cùng đỉnh replica giảm từ 9 xuống 3 và Pod-phút giảm khoảng 59,5%; throughput tổng gần nhau. q-low có p95 thấp nhất, còn q-high dùng ít Pod-phút nhất. q-medium có p95 và peak backlog cao nhất, nên kết quả không thay đổi đều theo target.

Cả ba lượt không ghi nhận request lỗi hoặc dropped iteration; CloudWatch ghi 4.799 sent và deleted mỗi lượt. Kết quả phù hợp để so sánh mô tả trong phạm vi một lượt mỗi mức, chưa đo được độ biến động hay chứng minh quan hệ nhân quả. Các nhánh giữ bốn node, nên giảm Pod-phút không trực tiếp chứng minh giảm chi phí EC2.

p95 được ước lượng từ histogram E2E và có thể gồm error/duplicate; throughput dựa trên counter và có thể thiếu mẫu của Pod sống ngắn. Backlog SQS là xấp xỉ; drain là lần đầu ghi nhận ba mẫu queue rỗng liên tiếp sau tải. Chưa đối soát job ID nên không kết luận mọi job hoàn thành đúng một lần. Dữ liệu thô của các lượt hiện không có trong thư mục kết quả cục bộ.
