
# Danh sách kịch bản thí nghiệm, đánh giá

## 1. Tổng quan các kịch bản

E0 không so sánh autoscaler nào cả. Đầu ra của nó là **một con số μ** và **một bộ định nghĩa workload theo μ** (đặt trong repo để chạy lại được). Nó nhỏ, chỉ vài lượt chạy ngắn, nhưng nếu thiếu thì E1–E5 sẽ dựa trên tải chọn tùy ý và khó bảo vệ trước giảng viên.

| ID     | Kịch bản                                                  | Mức                                         | Câu hỏi / Nội dung                                                                                                                                                                | NT531 (4+) | NT533 (4+) | Đã hoàn thành |
| ------ | --------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------: | :--------: | :-----------: |
| **E0** | Nền tảng: Worker Capacity Calibration + Workload Modeling | **Core (optional)**                         | Đo μ (số task/s mà 1 Worker xử lý ổn định) và định nghĩa workload Steady/Step/Burst theo μ, làm cơ sở cho các kịch bản sau.                                                       |     ✓      |     ✓      |       —       |
| **E1** | Fixed vs CPU-HPA vs KEDA                                  | **Core**                                    | So sánh ba chiến lược trên cùng event-driven workload, với đủ node capacity.                                                                                                      |     ✓      |     ✓      |       —       |
| **E2** | KEDA scaling response + Scale-to-Zero (`0 → N → 0`)       | **Core**                                    | Đo toàn bộ vòng đời `0 → N → 0` và first-job latency.                                                                                                                             |     ✓      |     ✓      |       —       |
| **E3** | KEDA + Karpenter Two-Level Elasticity                     | **Core**                                    | Đo quá trình KEDA tăng pod và Karpenter tạo node khi thiếu capacity.                                                                                                              |     ✓      |     ✓      |       —       |
| **E4** | Warm Capacity vs Elastic Capacity (Node)                  | **Advanced**                                | So sánh giữ sẵn node capacity với tạo node theo nhu cầu.                                                                                                                          |     ✓      |     —      |       —       |
| **E5** | Cold start vs Pod pre-warming (Cron)                      | **Advanced**                                | So sánh không giữ sẵn worker với giữ sẵn worker; đánh giá latency và tài nguyên idle.                                                                                             |     —      |     ✓      |       —       |
| **E6** | Chi phí On-Demand/Karpenter; Spot (nếu còn thời gian)     | **Optional**: C1–C3 trọng tâm; Spot mở rộng | Ước tính chi phí compute (cost per 1,000 tasks) của HPA và KEDA trên Node cố định, và KEDA + Karpenter elastic, tính từ số liệu E1, E3, E4; khảo sát thêm Spot nếu còn thời gian. |     —      |     ✓      |       —       |
| **E7** | Queue Target Sensitivity                                  | **Optional**                                | Thay đổi `queueLength` của KEDA (thấp/vừa/cao) trên một workload đại diện, đo ảnh hưởng đến backlog, latency và số Pod.                                                           |     ✓      |     —      |       —       |
| **E8** | Chaos Engineering                                         | **Optional**                                | Làm gián đoạn worker và quan sát phục hồi, queue, duplicate và throughput.                                                                                                        |     —      |     ✓      |       —       |

Chú thích:
- **✓** nghĩa là kịch bản đó được trình bày trong báo cáo và demo ở môn tương ứng.
- Mức **Core** là bắt buộc hoàn thành. **Advanced** nên hoàn thành sau khi core ổn định. **Optional** chỉ làm khi còn thời gian.
- Mỗi kịch bản chạy ít nhất 3 lượt
- Mỗi môn nên có ít nhất 4 kịch bản

### 1.1. Nguồn dữ liệu đo (đề xuất)

|Loại dữ liệu|Nguồn|
|---|---|
|Tải đầu vào, latency phía client|k6|
|Queue depth, in-flight messages, queue age|Amazon SQS metrics (qua CloudWatch hoặc exporter vào Prometheus)|
|Replica count, Pending Pods, Node count, CPU/memory|Prometheus (kube-state-metrics, cAdvisor/metrics-server)|
|Desired replicas, trạng thái trigger|Metric của KEDA, `kubectl get scaledobject/hpa`|
|Thời điểm provisioning, Node Ready|Log và event của Karpenter, `NodeClaim`, Kubernetes events|
|Trực quan hóa|Grafana|
### 1.2. Thứ tự phụ thuộc giữa các kịch bản

```text
E0 (μ, workload)
 └── E1 (Fixed / HPA / KEDA)
      └── E2 (0 → N → 0)
           ├── E3 (KEDA + Karpenter)
           │     ├── E4 (Warm vs Elastic)
           │     ├── E6 (Spot)
           │     └── E8 (Chaos)
           └── E5 (Cold start vs Pre-warming)

E1 + E3 + E4  ──► E6 (Cost)   ──► E6 (Spot)
E1            ──► E7 (Queue target)
```

## 2. Chi tiết từng kịch bản

### E0 — Nền tảng: Worker Capacity Calibration + Workload Modeling

| **Vai trò**   | Không phải thí nghiệm về autoscaling. Đây là bước chuẩn bị để mọi kịch bản sau dùng tải dựa trên năng lực thực tế thay vì số tùy ý. |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------- |

**E0a. Worker Capacity Calibration**

- Tắt autoscaling, giữ **1 Worker** và Node capacity ổn định.
- Tăng dần arrival rate, tìm mức mà queue không tăng liên tục.
- Kết quả: `μ` = sustainable processing rate của 1 Worker (ví dụ `1 Worker ≈ 25 task/s`).

**E0b. Workload Modeling**

|Dạng|Mô tả|Dùng để đánh giá|
|---|---|---|
|**Steady**|Tải duy trì ổn định|Throughput, latency, resource efficiency ở trạng thái ổn định|
|**Step**|Tải chuyển từ thấp lên cao rồi giữ nguyên|Tốc độ phát hiện và phản ứng, backlog growth, recovery|
|**Burst**|Tải tăng rất cao trong thời gian ngắn rồi giảm|Peak backlog, tail latency, phản ứng autoscaling|

Mức tải được mô tả theo `μ` (ví dụ `5μ`, `10μ`). Khung thời gian chung có thể dùng 5 pha: Idle → Low → Burst → Sustained → Stop.

| Mục              | Nội dung                                                                                                                                             |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Đo gì**        | `μ` (task/s của 1 Worker), điểm queue bắt đầu tăng liên tục, throughput và CPU của 1 Worker ở từng mức tải                                           |
| **Dựa vào**      | Hạ tầng đã chạy ổn (App + SQS + Worker), Prometheus/Grafana thu metric đúng, k6 sinh tải                                                             |
| **Cung cấp cho** | E1 (chọn burst đủ lớn, hiệu chỉnh `queueLength`, chọn `maxReplicas`), E3 và E4 (tính số Pod và Node cần, từ đó biết thế nào là "thiếu capacity"), E7 |

**Phân bổ workload cho các kịch bản**

| Kịch bản | Workload                                                |
| -------- | ------------------------------------------------------- |
| E1       | Step và Burst (Steady làm tham chiếu nếu còn thời gian) |
| E2       | Một pha: idle → có tải → dừng                           |
| E3, E4   | Burst hoặc Step, đủ lớn để vượt capacity                |
| E5       | Idle rồi có tải đột ngột                                |
| E7       | Một workload đại diện (Step hoặc Burst)                 |

---

### E1 — Fixed vs CPU-HPA vs KEDA

| **Câu hỏi**   | Với cùng một event-driven application và cùng workload, ba chiến lược Fixed replicas, CPU-HPA và KEDA khác nhau thế nào về performance, queue behavior và resource usage? |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Mục đích**  | Cô lập tác động của **Pod-level autoscaling**. Karpenter không được trở thành biến ảnh hưởng.                                                                             |

**Cấu hình**

| Cấu hình | Thiết lập                                                |
| -------- | -------------------------------------------------------- |
| Fixed    | Số replica cố định _(cần chốt giá trị)_                  |
| CPU-HPA  | `min=1, max=30, CPU target=60%`                          |
| KEDA SQS | `min=1`, cùng `max`, `queueLength=Q` đã hiệu chỉnh từ E0 |

**Biến thí nghiệm**

|Loại|Nội dung|
|---|---|
|Biến độc lập|Autoscaling strategy (Fixed / HPA / KEDA)|
|Biến phụ thuộc|Throughput, latency p50/p95/p99, queue depth, drain time, Pod count, CPU utilization|
|Biến kiểm soát|Worker image, requests/limits, Node type, workload profile, `max` replicas|

**Điều kiện:** cluster có **đủ Node capacity** cho `maxReplicas`, để Karpenter không ảnh hưởng. KEDA dùng `min=1` ở đây; `min=0` được đo riêng ở E2.

**Đo gì**

|Nhóm|Metric|
|---|---|
|Application|Throughput (tasks/s), completion latency p50/p95/p99, error/failure rate|
|Queue|Queue depth theo thời gian, peak backlog, average backlog, queue drain time `T_drain = T_queue=0 − T_loadStop`|
|Autoscaling|Replica count theo thời gian, time to first scale-out, thời điểm đạt processing capacity ổn định|
|Resource|CPU utilization, Pod count, Pod-minutes (hoặc Pod-seconds)|
|Correctness|Completed tasks, error và duplicate nếu có|

| Mục              | Nội dung                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| **Dựa vào**      | E0 (μ, Step/Burst); k6; SQS metrics; Prometheus; metric của HPA và KEDA |
| **Cung cấp cho** | E6 (cấu hình C1, C2), E7, và là baseline để so sánh với E2, E3          |

---

### E2 — KEDA Scaling Response + Scale-to-Zero (`0 → N → 0`)

| **Câu hỏi**   | KEDA phản ứng thế nào trong toàn bộ vòng đời `0 Worker → scale-out → processing → queue empty → scale-in về 0`? |
| ------------- | --------------------------------------------------------------------------------------------------------------- |
| **Điều kiện** | Cluster đã có sẵn Node, để thời gian Pod startup không bị lẫn với Node provisioning.                            |

**Phần A: Scale-out / Cold Activation**

```text
T0 = workload/message đầu tiên xuất hiện
T1 = KEDA phát hiện trigger active
T2 = desired replicas tăng
T3 = Pod được tạo
T4 = Pod Ready
T5 = Worker xử lý/hoàn thành công việc đầu tiên
```

|Đại lượng|Công thức|
|---|---|
|Detection latency|`T1 − T0`|
|Pod startup latency|`T4 − T2`|
|Activation latency|`T4 − T0`|
|First-job completion latency (effective scaling latency)|`T5 − T0`|

**Phần B: Trong giai đoạn processing:** throughput, p95/p99 completion latency, queue depth, replica count.

**Phần C: Scale-in / Scale-to-Zero**

```text
T_idle = queue/trigger hết active
T_zero = replicas = 0
Scale-down-to-zero delay = T_zero − T_idle
```

|Mục|Nội dung|
|---|---|
|**Đo gì**|`T_detect`, desired replica change latency, Pod startup latency, first-job latency, queue peak trong cold activation, throughput recovery, scale-down-to-zero delay, Pod-seconds trong cả vòng đời|
|**Dựa vào**|E0 (workload), E1 (cấu hình KEDA, `queueLength`); `pollingInterval` và `cooldownPeriod` của ScaledObject (cần giải thích trong báo cáo); timestamp từ SQS, KEDA, Kubernetes events|
|**Cung cấp cho**|E5 (cấu hình A: cold start `min=0`), E6 (idle cost)|

---

### E3 — KEDA + Karpenter Two-Level Elasticity

| **Câu hỏi**   | Khi KEDA cần thêm Worker Pod nhưng Node hiện tại không còn capacity, Karpenter bổ sung bao nhiêu latency vào end-to-end scaling path? |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Thiết kế**  | Tạo cluster **cố ý có ít spare capacity**. Karpenter dùng On-Demand. Workload đủ lớn để tạo Pod `Pending`.                            |

```text
Workload spike → backlog tăng → KEDA tăng desired Pods
→ Một số Pods Pending → Karpenter provision EC2
→ Node Ready → Pods Ready → Queue recovery
```

**Timeline đo đạc**

```text
T0 = workload spike
T1 = backlog tăng
T2 = desired replicas tăng
T3 = Pod Pending
T4 = Karpenter bắt đầu provisioning
T5 = EC2 instance xuất hiện
T6 = Node Ready
T7 = Pod Ready
T8 = throughput/processing ổn định
```

|Khoảng|Tính toán|Ý nghĩa|
|---|---|---|
|KEDA response|`T2 − T0`|Tốc độ KEDA phản ứng với backlog|
|Scheduling pressure|`T3 − T2`|Từ desired replicas đến Pod Pending|
|Node provisioning|`T6 − T4`|Karpenter launch EC2 đến Node Ready|
|Pod startup|`T7 − T6`|Container startup trên Node mới|
|End-to-end scale|`T8 − T0`|Toàn bộ scaling path|

|Nhóm|Metric|
|---|---|
|Pod-level|KEDA response, desired replica change, số Pending Pod|
|Node-level|Pending Pod duration, Karpenter provisioning latency, Node Ready latency, Node count theo thời gian|
|End-to-end|End-to-end scaling latency, throughput recovery time, p95/p99, peak backlog, queue drain time|
|Resource|Pod-seconds, Node-seconds, CPU utilization|

| Mục              | Nội dung                                                                                                                                                       |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dựa vào**      | E0 (tính số Pod và Node cần để vượt capacity), E1 và E2 (cấu hình KEDA); NodePool/NodeClass của Karpenter; log và `NodeClaim` của Karpenter; Kubernetes events |
| **Cung cấp cho** | E4 (nhóm Elastic), E6 (cấu hình C3 và C4), E7, E8                                                                                                              |
| **Ghi chú**      | Nếu không thu được chính xác mọi timestamp, ghi rõ proxy đã dùng.                                                                                              |

---

### E4 — Warm Capacity vs Elastic Capacity

| **Câu hỏi**       | Giữ sẵn Node capacity và provision Node theo nhu cầu tạo ra trade-off gì giữa performance và resource efficiency? |
| ----------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Tầng tác động** | Node (EC2)                                                                                                        |

|Cấu hình|Mô tả|
|---|---|
|**A: Warm**|Node trống có sẵn, đủ chỗ cho các Pod mới. KEDA tăng Pod, Pod `Ready` nhanh, nhưng tốn Node nhàn rỗi.|
|**B: Elastic**|Không đủ Node. Pod `Pending`, Karpenter tạo Node mới, Pod `Ready` trễ hơn, nhưng không tốn Node nhàn rỗi. Chính là **E3**.|

**Biến độc lập:** lượng Node capacity có sẵn. **Biến kiểm soát:** workload, cấu hình KEDA, image, requests/limits.

|Metric|Warm|Elastic|
|---|---|---|
|p95/p99 latency|[TODO]|[TODO]|
|Throughput|[TODO]|[TODO]|
|Peak backlog|[TODO]|[TODO]|
|Queue recovery time|[TODO]|[TODO]|
|End-to-end scaling latency|[TODO]|[TODO]|
|Pending Pod duration|N/A|[TODO]|
|Pod-seconds|[TODO]|[TODO]|
|Node-seconds (kể cả Node nhàn rỗi)|[TODO]|[TODO]|

|Mục|Nội dung|
|---|---|
|**Dựa vào**|E3 (dùng lại số liệu làm nhóm Elastic, chỉ chạy thêm nhóm Warm), E0 (workload)|
|**Cung cấp cho**|E6 (so sánh chi phí giữ Node sẵn với Node theo nhu cầu)|
|**Cách kết luận**|Không tìm cấu hình "thắng tuyệt đối". Phân tích đánh đổi: Warm phản ứng nhanh hơn nhưng giữ nhiều idle resource hơn; Elastic giảm idle capacity nhưng có thêm Node provisioning delay.|

---

### E5 — Cold start vs Pod pre-warming

|Mục|Nội dung|
|---|---|
|**Môn / Mức**|NT533 / Advanced|
|**Nguồn gốc**|NT533 E4|
|**Câu hỏi**|Cron pre-warming giảm cold start bao nhiêu, và đánh đổi bao nhiêu idle cost?|
|**Tầng tác động**|Pod|
|**Điều kiện**|Cluster đã có sẵn Node, để Cron không kích hoạt Karpenter và làm lẫn độ trễ Node vào kết quả cold start.|

|Cấu hình|Mô tả|
|---|---|
|**A**|`min=0`, không Cron (dùng lại số liệu E2)|
|**B**|KEDA Cron pre-warm 1 replica|
|**C**|KEDA Cron pre-warm 2 replicas|

|Mục|Nội dung|
|---|---|
|**Đo gì**|First-job latency, p95 processing latency trong 1–2 phút đầu, queue peak, Pod-minutes idle, chi phí compute ước tính|
|**Dựa vào**|E2 (đường cơ sở cold start, định nghĩa T0–T5), E0 (workload "idle rồi có tải đột ngột"), cấu hình Cron trigger của KEDA|
|**Cách kết luận**|Mục tiêu là tìm trade-off, không phải tìm latency thấp nhất.|

---

### E6 — Phân tích chi phí

| **Câu hỏi**   | Mỗi cấu hình tốn bao nhiêu để xử lý cùng một khối lượng công việc, và phần tiết kiệm đến từ đâu?                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Cách làm**  | **Không chạy thí nghiệm riêng.** Tính từ số liệu đo của E1, E3, E4. Chi phí là mô hình ước tính từ metric, không đọc từ hóa đơn AWS. |

|Config|Autoscaler|Node capacity|Lấy số liệu từ|
|---|---|---|---|
|C1|HPA|Fixed On-Demand|E1|
|C2|KEDA|Fixed On-Demand|E1|
|C3|KEDA + Karpenter|On-Demand elastic|E3 (và E4 cho nhóm Warm)|

**Công thức**

```text
Cost_compute = Σ (Price_i × Runtime_i)
C_1000       = (TotalCost / ProcessedTasks) × 1000
Saving%      = (Cost_baseline − Cost_candidate) / Cost_baseline × 100
```

**Thành phần chi phí cần tách riêng**

- Chi phí cố định, không đổi theo autoscaling: EKS control plane, NAT, seed nodes, hai RDS.
- Chi phí compute co giãn: Node-hours theo từng instance type, Pod-minutes.
- Idle cost (khi không có workload) tách khỏi cost trong workload window, để thể hiện đúng giá trị của scale-to-zero.

|Mục|Nội dung|
|---|---|
|**Đo gì**|Node-hours, instance type, capacity type, Pod-minutes, tasks processed, tổng chi phí compute ước tính, cost per 1,000 tasks, saving %|
|**Dựa vào**|Node-minutes và Pod-minutes từ Prometheus (E1, E3, E4, và idle từ E2); bảng giá AWS tại thời điểm chạy (ghi rõ region và ngày); cùng workload và cùng độ dài cửa sổ cho mọi cấu hình, cửa sổ phải bao gồm đoạn idle sau khi tải dừng|
|**Lưu ý**|So sánh theo cost per 1,000 tasks, không so tổng tiền, vì số task xử lý của các cấu hình có thể khác nhau. Ghi rõ mọi giả định.|
#### Chi phí với Spot (C4)

| **Câu hỏi**   | Dùng EC2 Spot cho Node co giãn thay đổi chi phí và độ ổn định thế nào so với On-Demand?                  |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| **Cấu hình**  | C4: KEDA + Karpenter + Spot elastic, cùng workload với C3.                                               |
| **Điều kiện** | **Chạy tách riêng khỏi E3**, để độ trễ provisioning của E3 không bị lẫn với biến động capacity của Spot. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Node-hours và giá Spot theo thời điểm, cost per 1,000 tasks, số lần Spot interruption, Pending Pod duration, throughput dip khi bị thu hồi, duplicate message|
|**Dựa vào**|E3 (cấu hình Karpenter), E6 (mô hình chi phí); NodePool khai báo nhiều instance type; interruption handling của Karpenter; Worker xử lý SIGTERM gọn và chịu được message xử lý trùng (visibility timeout của SQS)|
|**Lưu ý**|Mức giảm giá của Spot phụ thuộc region, instance type và thời điểm. Dùng giá thực tế tại lúc chạy, không dùng con số cố định. Có thể thay bằng ước tính what-if từ Spot price history nếu không chạy thật.|

---

### E7 — Queue Target Sensitivity

| **Câu hỏi**  | Giá trị `queueLength` của KEDA ảnh hưởng thế nào đến performance và resource usage?                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Thiết kế** | Biến độc lập là `queueLength` với ba giá trị `Q_low`, `Q_medium`, `Q_high`. Dùng **một workload đại diện** (Step hoặc Burst). Các biến khác giữ nguyên. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Replica count, peak backlog, queue drain time, p95 latency, throughput, Pod-seconds|
|**Dựa vào**|E0 (μ, để chọn ba mức Q hợp lý), E1 (cấu hình KEDA cơ sở)|
|**Ghi chú**|Đồ án khóa trước dùng `queueLength = 20` cố định; ở đây nó trở thành biến độc lập. Cũng giúp biện minh cho giá trị Q chọn ở E1.|

---

### E8 — Chaos Engineering

| **Câu hỏi**   | Hệ thống phục hồi thế nào khi Worker Pod (hoặc Node) bị mất lúc queue đang backlog và đang scale-out?                            |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Thiết kế**  | Bản nhẹ: `kubectl delete pod` hoặc terminate một Node trong lúc chạy E3, thay vì cài Chaos Mesh/Litmus. Chỉ làm khi E1–E6 đã ổn. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Deployment recovery time, duplicate message, queue backlog, throughput dip, recovery time|
|**Dựa vào**|E3 (kịch bản scale-out làm nền); visibility timeout của SQS; số message gửi và số message đã xử lý để đối chiếu|
|**Lưu ý**|Không tuyên bố "loss-less" nếu chưa có phương pháp kiểm chứng message count và end state.|

---

## 3. Phân bổ theo môn học

Khi viết báo cáo và trình bày ở mỗi môn học chỉ dựa trên phần tương ứng
### NT531 — Đánh giá hiệu năng mạng máy tính

| Mức      | Kịch bản       |
| -------- | -------------- |
| Core     | E0, E1, E2, E3 |
| Advanced | E4             |
| Optional | E8             |
### NT533 — Hệ tính toán phân bố

|Mức|Kịch bản|
|---|---|
|Core|E0, E1, E2, E3, E6|
|Advanced|E5|
|Optional|E7, E9|

Điểm cần thống nhất trong nhóm:
1. **Số replica của cấu hình Fixed ở E1:** cần chốt giá trị cụ thể (đủ cho tải đỉnh, hay một mức trung bình theo `μ`).
2. **Số queue dùng khi đo:** `NT531_REPORT.md` mô tả ba Amazon SQS queue và ba Worker deployment, còn `NT533_REPORT.md` mô tả chung một Worker Service. Cần chốt thí nghiệm chạy trên queue nào hay trên cả ba.
3. **Dạng workload cho E1:** chạy cả Step và Burst, hay chỉ một dạng, vì số lượt chạy nhân lên theo số dạng workload.
