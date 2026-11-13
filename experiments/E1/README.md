# E1 — Warm vs Elastic với KEDA và Karpenter

E1 khảo sát hai yếu tố: **node capacity** có sẵn và **số worker tối thiểu** đang Ready trước tải. Câu hỏi là các yếu tố này ảnh hưởng thế nào đến latency, backlog và tài nguyên khi tải thay đổi. Một lượt không tạo node mới vẫn là dữ liệu quan sát, nhưng không chứng minh đường provisioning.

| Cấu hình | KEDA min | KEDA max | Kết quả hiện có |
|---|---:|---:|---|
| Config 1 — `keda-config1.yaml` | 1 | 10 | Đã chạy Warm/Elastic với Step/Burst; xem bên dưới |
| Config 2 — `keda-config2.yaml` | 3 | 10 | Đã chạy Warm/Elastic với Burst |
| Config 3 — `keda-config3.yaml` | 5 | 10 | Đã chạy Warm/Elastic với Burst |

Mỗi config có hai nhánh: **Warm** chuẩn bị 4 node E1 Ready; **Elastic** không giữ node E1 rảnh không có worker. Bắt đầu khi tất cả worker tối thiểu đã Ready. Elastic Config 3 có thể cần từ 2 node; xác định từ requests, allocatable và Pod thực tế, không giả định 5 worker sẽ vừa 1 node. Ghi số node và phân bố worker vì có thể còn capacity trống trên các node đang chạy worker. Giữ workload, worker, queue và thông số autoscaler khác giống nhau. Lượt min=1 cũ giữ nguyên tên và được xem là Config 1.

## Cấu hình và workload


| File | Vai trò |
|---|---|
| `karpenter-values.yaml` | NodePool/NodeClass `e1-orders`, On-Demand, `c7i-flex.large`, consolidation `Never` |
| `autoscaled-values.yaml`, `keda-config1.yaml`, `keda-config2.yaml`, `keda-config3.yaml` | Worker chọn NodePool E1; KEDA SQS min lần lượt 1/3/5, max 10, queueLength 10, polling 30s, cooldown 300s |
| `warm-capacity.yaml` | 10 Pod tạm giữ chỗ để chuẩn bị warm; requests 500m/256Mi khớp overlay worker E1 |
| `step.js`, `burst.js`, `workload-common.js` | workload E0 tại chỗ: Step 5→10→15→20→15→10→5/s, mỗi bậc 1 phút; Burst 5/s 1 phút → 40/s 30 giây → 5/s 1 phút |
| `run.py`, `run.sh` | Tạo hồ sơ/kiểm tra target và các lệnh tắt; `run.sh` không apply hoặc xóa tài nguyên |
| `collect.py` | Thu SQS, Prometheus, Pod, Node/NodeClaim/event, gồm histogram queue wait và thời gian xử lý |
| `report.py`, `compare.py` | Tóm tắt một lượt và so sánh các report cùng workload/cửa sổ |

Các giá trị trên là **cấu hình trong repo**; kiểm tra cấu hình thực tế trên cluster trước mỗi lượt. E1 đặt CPU request worker thành **500m** thay cho mức 128m đã dùng trong E0, nhằm làm rõ giới hạn scheduling trên node 2 vCPU; cả hai nhánh đều dùng cùng request này. Thay đổi request có thể ảnh hưởng chia sẻ CPU, nên cần pilot lại throughput trước khi dùng ước lượng μ từ E0. Cấu hình vẫn không bảo đảm workload sẽ tạo Pending: phải kiểm chứng bằng dữ liệu. Hai nhánh phải cùng image/digest, requests/limits, concurrency, queue, KEDA, loại node và workload; ghi cả khác biệt không kiểm soát. KEDA/Karpenter, API và monitoring cần node hệ thống độc lập. Kiểm tra quota, IAM, subnet, AMI, IP và chi phí; warm có thể tạo nhiều node, và `Never` giữ node sau khi hết tải.

## Kết quả E1


### Config 1 — min 1 worker

Đã chạy hai lượt cho mỗi nhánh và profile. Warm bắt đầu với **4 node E1**, Elastic với **1 node E1**; cả hai bắt đầu với **1 worker Ready**. Các lượt dùng cùng image worker, CPU request `500m`, concurrency `1` và cùng workload trong mỗi profile. Step tăng từ 5 lên 20 request/s theo bậc; Burst tăng từ 5 lên 40 request/s trong 30 giây rồi trở về 5 request/s.

Biểu đồ: [Step tổng hợp](figures/config-1/step_summary.png) · [Step theo thời gian](figures/config-1/step_timeline.png) · [Burst tổng hợp](figures/config-1/burst_summary.png) · [Burst theo thời gian](figures/config-1/burst_timeline.png) · [Kết luận trung bình](figures/config-1/conclusion_average.png).

| Profile | Nhánh | Lượt | Node E1 đầu → cao nhất | Đỉnh queue ≈ | p95 E2E ≈ (s) | Node-phút ≈ |
|---|---|---|---:|---:|---:|---:|
| Step | Warm | r01 | 4 → 4 | 50 | 1,39 | 36,00 |
| Step | Warm | r02 | 4 → 4 | 103 | 4,50 | 36,01 |
| Step | Elastic | r01 | 1 → 1 | 24 | 0,25 | 9,00 |
| Step | Elastic | r02 | 1 → 2 | 47 | 1,11 | 14,91 |
| Burst | Warm | r01 | 4 → 4 | 626 | 27,02 | 18,00 |
| Burst | Warm | r02 | 4 → 4 | 545 | 18,51 | 18,02 |
| Burst | Elastic | r01 | 1 → 4 | 881 | 53,80 | 8,27 |
| Burst | Elastic | r02 | 1 → 4 | 714 | 29,09 | 8,39 |

Đỉnh queue là tổng visible và in-flight lớn nhất quan sát được từ các mẫu SQS. p95 là ước lượng từ histogram E2E của worker. Node-phút tính theo node Kubernetes thuộc NodePool E1, trong cửa sổ từ 60 giây trước đến 60 giây sau tải; **không phải chi phí EC2** và chưa bao gồm toàn bộ thời gian chuẩn bị hoặc giữ node ngoài cửa sổ.

Ở Burst, cả hai lượt Elastic có Pod không xếp lịch được do thiếu CPU request và Karpenter tạo thêm ba node. Theo mẫu metric, Warm ghi nhận 10 worker Ready sau khi Burst bắt đầu khoảng **62–66 giây**, Elastic khoảng **108–113 giây**. Đây là thời điểm đầu tiên quan sát được, không phải timestamp chính xác lúc Pod Ready. Warm vẫn có backlog vì việc scale và khởi động Pod cần thời gian. Ở Step, Elastic r01 không cần node mới, còn r02 tạo thêm một node; hai lượt Elastic có p95 và đỉnh queue quan sát thấp hơn Warm.

Cả tám lượt có 100% request được API chấp nhận theo check k6, nhưng điều này không xác nhận mọi job đã hoàn thành. Counter success chưa khớp số job được nhận và có thể thiếu dữ liệu từ Pod mới hoặc sống ngắn; chưa đối soát theo job ID. SQS và histogram là ước lượng, CPU chưa đủ dữ liệu đồng đều để so sánh chắc chắn. Các report vẫn ghi `validity: not_assessed`; cần xem [kết quả gốc](../results/E1/) và hoàn thiện `notes.md` khi đánh giá chính thức.

#### Trung bình và kết luận Config 1

Bảng sau lấy **trung bình số học của hai lượt** cho từng nhánh và profile; đây là kết quả thăm dò, chưa đủ để khẳng định khác biệt ổn định.

| Profile | p95 Warm / Elastic ≈ (s) | Đỉnh queue Warm / Elastic ≈ | Node-phút Warm / Elastic ≈ | Kết luận từ các lượt đã chạy |
|---|---:|---:|---:|---|
| Step | 2,94 / 0,68 | 76,5 / 35,5 | 36,01 / 11,96 | Elastic có p95 và đỉnh queue quan sát thấp hơn; Warm giữ nhiều capacity hơn. |
| Burst | 22,77 / 41,45 | 585,5 / 797,5 | 18,01 / 8,33 | Warm đạt p95 và đỉnh queue thấp hơn, đổi lại sử dụng nhiều node-phút hơn. |

### Config 2 — min 3 worker

Đã chạy hai lượt Burst cho mỗi nhánh. Warm bắt đầu với **4 node E1**, Elastic với **2 node E1**; cả hai bắt đầu với **3 worker Ready**. Chưa chạy Step cho config này.

Biểu đồ: [Burst tổng hợp](figures/config-2/burst_summary.png) · [Burst theo thời gian](figures/config-2/burst_timeline.png).

| Profile | Nhánh | Lượt | Node E1 đầu → cao nhất | Đỉnh queue ≈ | p95 E2E ≈ (s) | Node-phút ≈ |
|---|---|---|---:|---:|---:|---:|
| Burst | Warm | r01 | 4 → 4 | 374 | 11,95 | 18,02 |
| Burst | Warm | r02 | 4 → 4 | 362 | 14,20 | 18,00 |
| Burst | Elastic | r01 | 2 → 4 | 378 | 14,31 | 11,33 |
| Burst | Elastic | r02 | 2 → 3 | 182 | 6,61 | 10,47 |

So với min 1, p95 và đỉnh queue trung bình giảm ở cả hai nhánh, nhưng vẫn còn backlog đáng kể. Hai lượt Elastic có Pod Pending và thay đổi tập node; Warm không ghi nhận Pending. p95 Elastic dao động từ **6,61 đến 14,31 giây**, nên hai lượt chưa đủ để kết luận Elastic nhanh hơn Warm.

### Config 3 — min 5 worker

Đã chạy hai lượt Burst cho mỗi nhánh. Warm bắt đầu với **4 node E1**, Elastic với **2 node E1**; cả hai bắt đầu với **5 worker Ready**. Chưa chạy Step cho config này.

Biểu đồ: [Burst tổng hợp](figures/config-3/burst_summary.png) · [Burst theo thời gian](figures/config-3/burst_timeline.png).

| Profile | Nhánh | Lượt | Node E1 đầu → cao nhất | Đỉnh queue ≈ | p95 E2E ≈ (s) | Node-phút ≈ |
|---|---|---|---:|---:|---:|---:|
| Burst | Warm | r01 | 4 → 4 | 6 | 0,243 | 18,00 |
| Burst | Warm | r02 | 4 → 4 | 10 | 0,245 | 18,00 |
| Burst | Elastic | r01 | 2 → 2 | 7 | 0,244 | 9,00 |
| Burst | Elastic | r02 | 2 → 2 | 6 | 0,244 | 9,00 |

Cả bốn lượt có p95 E2E gần **0,244 giây**, peak SQS từ **6 đến 10 message**, không ghi nhận Pending hoặc scale-out trong cửa sổ báo cáo. p95 thời gian xử lý task ước lượng khoảng **0,242–0,243 giây**; điều này phù hợp với việc hàng đợi không tích tụ đáng kể. Các percentile được nội suy từ histogram, không thể xem là số đo chính xác đến từng mili giây.

### So sánh các config với Burst

Các giá trị là **trung bình số học của hai lượt**. p95 trung bình là trung bình p95 từng lượt, không phải p95 gộp mọi job. Ready Pod-phút tính từ đầu tải đến 60 giây sau tải; Node-phút còn gồm 60 giây trước tải.

Biểu đồ: [So sánh trung bình ba config](figures/comparison/burst_comparison_average.png).

| Config | Nhánh | p95 E2E ≈ (s) | Đỉnh queue ≈ | Ready Pod-phút ≈ | Node-phút ≈ |
|---|---|---:|---:|---:|---:|
| 1 — min 1 | Warm | 22,77 | 585,5 | 17,91 | 18,01 |
| 1 — min 1 | Elastic | 41,45 | 797,5 | 13,69 | 8,33 |
| 2 — min 3 | Warm | 13,08 | 368 | 20,87 | 18,01 |
| 2 — min 3 | Elastic | 10,46 | 280 | 18,35 | 10,90 |
| 3 — min 5 | Warm | 0,244 | 8 | 17,50 | 18,00 |
| 3 — min 5 | Elastic | 0,244 | 6,5 | 17,50 | 9,00 |
