# E3 — CPU-HPA vs KEDA trên Karpenter

## Mục tiêu

So sánh phản ứng, hiệu năng và tài nguyên của HPA theo CPU với KEDA theo queue trên cùng workload.

## Thiết kế

Mỗi lượt bắt đầu với một worker và một node worker Ready. Hai nhánh dùng cùng workload, min 1/max 10 worker; HPA có CPU target 60%, KEDA có queueLength 10. Karpenter mở rộng node khi cần.

Step và Burst có bốn lượt mỗi nhánh; Steady có hai lượt mỗi nhánh.

## Cấu hình và workload

| File | Chức năng |
|---|---|
| `karpenter-values.yaml`, `warm-capacity.yaml` | NodePool `e3-orders` On-Demand `c7i-flex.large`, consolidation `Never`; một Pod tạm để giữ sẵn một node |
| `autoscaled-values.yaml` | Worker chọn NodePool E3, CPU request 500m, memory request 256Mi |
| `hpa.yaml`, `keda.yaml` | HPA CPU target 60%, hoặc KEDA SQS queueLength 10; cả hai min 1/max 10 |
| `stead.js`, `step.js`, `burst.js`, `workload-common.js` | Steady 5/s 2 phút; Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5/s 1 phút → 40/s 30 giây → 5/s 1 phút |
| `run.py`, `run.sh`, `collect.py` | Hồ sơ, lệnh tắt và thu SQS, Prometheus, Pod, NodeClaim, node và event |
| `report.py`, `compare.py` | Báo cáo từng lượt và so sánh HPA/KEDA cùng profile/cửa sổ |

Các cấu hình này đã được kiểm tra trên cluster trong đợt ngày 2026-11-07; điều kiện và giới hạn được ghi trong báo cáo. CPU request 500m khác 128m của E0; HPA target 60% được tính theo request này. Một node Ready không tự chứng minh capacity trống tương đương: kiểm tra CPU, memory, Pod/IP trống và image cache từng nhánh. Pod Pending và node mới được ghi nhận; chênh lệch kết quả có thể bao gồm ảnh hưởng provisioning. KEDA/Karpenter, API và monitoring cần node hệ thống độc lập. Kiểm tra quota, IAM, subnet và chi phí; `Never` có thể giữ node sau khi tải đã dừng.

## Kết quả

Giá trị trong bảng là trung vị của các lượt ở từng nhánh.

| Profile | Nhánh | p95 E2E ≈ (giây) | Peak queue ≈ | Ready Pod-phút ≈ | Node-phút ≈ |
|---|---|---:|---:|---:|---:|
| Step | HPA | 0,243 | 3 | 42,97 | 18,82 |
| Step | KEDA | 0,959 | 38 | 20,01 | 10,91 |
| Burst | HPA | 28,77 | 620 | 10,84 | 6,04 |
| Burst | KEDA | 51,02 | 876,5 | 13,90 | 8,46 |
| Steady | HPA | 0,243 | 1 | 5,31 | 4,00 |
| Steady | KEDA | 0,243 | 1 | 3,00 | 4,00 |

Với Step, HPA có p95 và backlog thấp hơn trong các lượt đo, còn KEDA dùng ít Pod-phút và node-phút hơn. Với Burst, HPA có p95 và backlog trung vị thấp hơn; Steady cho p95 gần nhau ở hai nhánh.

Số lượt còn ít và các chỉ số là ước lượng; kết quả không chứng minh khác biệt có ý nghĩa thống kê hoặc mọi job hoàn thành duy nhất. Node-phút là thời gian node Kubernetes hiện diện trong cửa sổ đo, không phải chi phí EC2.
