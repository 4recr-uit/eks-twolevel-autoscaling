
# Danh sách thực nghiệm đánh giá

## 1. Tổng quan

| ID | Kịch bản | Câu hỏi / Nội dung |
| --- | --- | --- |
| **E0** | Nền tảng: Worker Capacity Calibration + Workload Modeling | Đo μ (số task/s mà 1 worker xử lý ổn định) và định nghĩa workload Steady/Step/Burst theo μ, làm cơ sở cho các kịch bản sau. |
| **E1** | Warm Capacity vs Elastic Capacity (Node) | So sánh Warm/Elastic và khảo sát số worker tối thiểu 1/3/5 với KEDA + Karpenter. |
| **E2** | KEDA + Karpenter Two-Level Elasticity | Đo đường từ spike, backlog và Pod Pending đến Karpenter provision node, Pod Ready và throughput phục hồi; phân tích độ trễ từng giai đoạn. |
| **E3** | CPU-HPA vs KEDA trên Karpenter | So sánh hai bộ điều khiển trên cùng workload, bắt đầu với một node worker được giữ sẵn và capacity trống tương đương. |
| **E4** | Queue Target Sensitivity | Thay đổi `queueLength` của KEDA (thấp/vừa/cao) trên một workload đại diện, đo ảnh hưởng đến backlog, latency và số Pod. |
| **E5** | Chaos Engineering | Làm gián đoạn worker và quan sát phục hồi, queue, duplicate và throughput. |

## 2. Nguồn dữ liệu đo

|Loại dữ liệu|Nguồn|
|---|---|
|Tải đầu vào, latency phía client|k6|
|Queue depth, in-flight messages, queue age|Amazon SQS metrics (qua CloudWatch hoặc exporter vào Prometheus)|
|Replica count, Pending Pods, Node count, CPU/memory|Prometheus (kube-state-metrics, cAdvisor/metrics-server)|
|Desired replicas, trạng thái trigger|Metric của KEDA, `kubectl get scaledobject/hpa`|
|Thời điểm provisioning, Node Ready|Log và event của Karpenter, `NodeClaim`, Kubernetes events|
|Trực quan hóa|Grafana|

## 3. Thông tin các thực nghiệm

### E0 — Worker Capacity Calibration + Workload Modeling

| Mục | Nội dung |
|---|---|
| **Câu hỏi** | Một worker xử lý ổn định được bao nhiêu task mỗi giây? |
| **Thiết kế** | Giữ một worker, không bật autoscaler và tăng dần tải để quan sát vùng bão hòa. Dùng kết quả xây dựng workload Steady, Step và Burst. |
| **Đo gì** | Throughput thành công, backlog, CPU và p95 thời gian hoàn thành job. |
| **Kết quả** | Ước lượng sơ bộ μ ≈ 8,9 task/s/worker cho cấu hình đã đo. Xem [E0](E0/README.md). |

---

### E1 — Warm Capacity vs Elastic Capacity

| Mục | Nội dung |
|---|---|
| **Câu hỏi** | Node capacity có sẵn và số worker tối thiểu ảnh hưởng thế nào đến hiệu năng và tài nguyên? |
| **Thiết kế** | So sánh Warm có node chuẩn bị sẵn với Elastic không giữ node worker rảnh; khảo sát KEDA min 1, 3 và 5 trên cùng workload. |
| **Đo gì** | Latency, backlog, throughput, số worker và node, Pod-minutes và Node-minutes. |
| **Dựa vào** | Workload E0 và cấu hình KEDA + Karpenter. Xem [E1](E1/README.md). |

---

### E2 — KEDA + Karpenter Two-Level Elasticity

| Mục | Nội dung |
|---|---|
| **Câu hỏi** | Hệ thống khởi động worker, mở rộng Pod/node và thu hẹp sau tải như thế nào? |
| **Thiết kế** | Bắt đầu với 0 worker và một node worker Ready; phát Burst, theo dõi KEDA scale Pod và Karpenter bổ sung node nếu thiếu capacity, rồi quan sát queue drain và worker về 0. |
| **Đo gì** | Cold start Pod, các mốc Pending/NodeClaim/node Ready/Pod Ready, backlog, throughput, latency và thời gian drain. |
| **Lưu ý** | Chỉ tính provisioning khi quan sát đủ bằng chứng; node mới không mặc định được tạo. Xem [E2](E2/README.md). |

---

### E3 — CPU-HPA vs KEDA trên Karpenter

| Mục | Nội dung |
|---|---|
| **Câu hỏi** | HPA theo CPU và KEDA theo queue khác nhau thế nào về phản ứng, hiệu năng và tài nguyên? |
| **Thiết kế** | So sánh hai controller trên cùng workload; mỗi lượt bắt đầu với một worker và một node worker Ready, giữ các điều kiện còn lại tương đương. |
| **Đo gì** | Số worker/node, backlog, thời gian drain, throughput, p95/p99 latency và tài nguyên sử dụng. |
| **Dựa vào** | Workload E0 và Karpenter để mở rộng node khi cần. Xem [E3](E3/README.md). |

---

### E4 — Queue Target Sensitivity

| **Câu hỏi**  | Giá trị `queueLength` của KEDA ảnh hưởng thế nào đến performance và resource usage?                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Thiết kế** | Biến độc lập là `queueLength` với ba giá trị `Q_low`, `Q_medium`, `Q_high`. Các lượt đã thực hiện dùng workload Step và giữ các biến khác không đổi. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Replica count, peak backlog, queue drain time, p95 latency, throughput, Pod-seconds|
|**Dựa vào**|E0 (μ, để chọn ba mức Q hợp lý), E2/E3 (cấu hình KEDA cơ sở)|
|**Ghi chú**|Kết quả giúp đánh giá giá trị queue target được chọn ở E1.|

---

### E5 — Chaos Engineering

| **Câu hỏi**   | Hệ thống phục hồi thế nào khi Worker Pod (hoặc Node) bị mất lúc queue đang backlog và đang scale-out?                            |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Thiết kế**  | So sánh baseline với trường hợp gián đoạn một Pod hoặc Node khi đang có tải; công cụ hiện hỗ trợ phân tích gián đoạn Pod. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Deployment recovery time, duplicate message, queue backlog, throughput dip, recovery time|
|**Dựa vào**|E2 (kịch bản scale-out làm nền); visibility timeout của SQS; số message gửi và số message đã xử lý để đối chiếu|
|**Lưu ý**|Không tuyên bố "loss-less" nếu chưa có phương pháp kiểm chứng message count và end state.|
