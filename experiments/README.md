
# Danh sách kịch bản thí nghiệm, đánh giá

## 1. Tổng quan các kịch bản

| ID | Kịch bản | Mức | Câu hỏi / Nội dung | NT531 (4+) | NT533 (4+) | Đã hoàn thành |
| --- | --- | --- | --- | :---: | :---: | :---: |
| **E0** | Nền tảng: Worker Capacity Calibration + Workload Modeling | **Core (optional)** | Đo μ (số task/s mà 1 worker xử lý ổn định) và định nghĩa workload Steady/Step/Burst theo μ, làm cơ sở cho các kịch bản sau. | ✓ | ✓ | — |
| **E1** | Warm Capacity vs Elastic Capacity (Node) | **Core** | So sánh Warm/Elastic và khảo sát số worker tối thiểu 1/3/5 với KEDA + Karpenter. | ✓ | ✓ | — |
| **E2** | KEDA + Karpenter Two-Level Elasticity | **Core** | Đo đường từ spike, backlog và Pod Pending đến Karpenter provision node, Pod Ready và throughput phục hồi; phân tích độ trễ từng giai đoạn. | ✓ | ✓ | — |
| **E3** | CPU-HPA vs KEDA trên Karpenter | **Core** | So sánh hai bộ điều khiển trên cùng workload, bắt đầu với một node worker được giữ sẵn và capacity trống tương đương. | ✓ | ✓ | — |
| **E4** | KEDA scaling response + Scale-to-Zero (`0 → N → 0`) | **Core** | Đo vòng đời worker `0 → N → 0` trên node sẵn và first-job latency; mở rộng đo node worker về 0 nếu thực hiện. | ✓ | ✓ | — |
| **E5** | Cold start vs Pod pre-warming (Cron) | **Advanced** | So sánh không giữ sẵn worker với giữ sẵn worker; đánh giá latency và tài nguyên idle. | — | ✓ | — |
| **E6** | Chi phí On-Demand/Karpenter; Spot (nếu còn thời gian) | **Optional**: C1–C3 trọng tâm; Spot mở rộng | Ước tính chi phí compute của HPA và KEDA trên Karpenter, cùng các phương án warm/elastic từ dữ liệu E1–E4; khảo sát thêm Spot nếu còn thời gian. | — | ✓ | — |
| **E7** | Queue Target Sensitivity | **Optional** | Thay đổi `queueLength` của KEDA (thấp/vừa/cao) trên một workload đại diện, đo ảnh hưởng đến backlog, latency và số Pod. | ✓ | — | — |
| **E8** | Chaos Engineering | **Optional** | Làm gián đoạn worker và quan sát phục hồi, queue, duplicate và throughput. | — | ✓ | — |

Chú thích:

- **✓**: kịch bản được dự kiến trình bày trong báo cáo và demo ở môn tương ứng.
- **Core**: nội dung chính; **Advanced**: thực hiện sau khi core ổn định; **Optional**: thực hiện khi còn thời gian.
- Mỗi tổ hợp cấu hình và workload dự kiến có ít nhất 3 lượt hợp lệ; mỗi môn nên có ít nhất 4 kịch bản.

Mỗi kịch bản có cấu hình, workload và công cụ cần thiết trong thư mục của chính nó; E6 tính chi phí offline từ dữ liệu và giá do người chạy cung cấp. Các workload được sao chép theo cùng định nghĩa E0; khi thay đổi một profile cần cập nhật phiên bản và đối chiếu các kịch bản liên quan. KEDA, Karpenter và thành phần hệ thống phải có nơi chạy độc lập với node worker. Ghi điều kiện đầu, xác nhận drain và giữ nguyên run ID kết quả cũ.

README của từng E mô tả điều kiện, cách chạy, thu thập và khôi phục. E1 Config 1 đã chạy Warm/Elastic với Step/Burst; Config 2/3 đã chạy Warm/Elastic với Burst. E2 có thể phân tích lại các lượt E1 Elastic Burst Config 1 để khảo sát scale-out hai tầng, giữ nguyên run ID và điều kiện E1; đây không phải lượt E2 độc lập. Cấu hình mặc định E2 (min 0, consolidation 1 phút) khác E1 (min 1/3/5, consolidation Never), nên không coi dữ liệu tái sử dụng là bằng chứng cho scale-from-zero hoặc consolidation của E2, hay gộp các lượt khác điều kiện như cùng cấu hình. Xem [thiết kế và timeline E2](E2/README.md#thiết-kế-đo-và-timeline).

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
|**A**|`min=0`, không Cron (dùng lại số liệu E4)|
|**B**|KEDA Cron pre-warm 1 replica|
|**C**|KEDA Cron pre-warm 2 replicas|

|Mục|Nội dung|
|---|---|
|**Đo gì**|First-job latency, p95 processing latency trong 1–2 phút đầu, queue peak, Pod-minutes idle, chi phí compute ước tính|
|**Dựa vào**|E4 (đường cơ sở cold start, định nghĩa T0–T5), E0 (workload "idle rồi có tải đột ngột"), cấu hình Cron trigger của KEDA|
|**Cách kết luận**|Mục tiêu là tìm trade-off, không phải tìm latency thấp nhất.|

---

### E6 — Phân tích chi phí

| **Câu hỏi**   | Mỗi cấu hình tốn bao nhiêu để xử lý cùng một khối lượng công việc, và phần tiết kiệm đến từ đâu?                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Cách làm**  | **Không chạy thí nghiệm riêng.** Tính từ số liệu đo của E1, E2, E3, E4. Chi phí là mô hình ước tính từ metric, không đọc từ hóa đơn AWS. |

|Config|Autoscaler|Node capacity|Lấy số liệu từ|
|---|---|---|---|
|C1|HPA + Karpenter|Node worker sẵn và mở rộng|E3|
|C2|KEDA + Karpenter|Node worker sẵn và mở rộng|E3|
|C3|KEDA + Karpenter|Warm / Elastic|E1 và E2|

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
|**Dựa vào**|Node-minutes và Pod-minutes từ Prometheus (E1, E2, E3, E4, và idle từ E4); bảng giá AWS tại thời điểm chạy (ghi rõ region và ngày); cùng workload và cùng độ dài cửa sổ cho mọi cấu hình, cửa sổ phải bao gồm đoạn idle sau khi tải dừng|
|**Lưu ý**|So sánh theo cost per 1,000 tasks, không so tổng tiền, vì số task xử lý của các cấu hình có thể khác nhau. Ghi rõ mọi giả định.|
#### Chi phí với Spot (C4)

| **Câu hỏi**   | Dùng EC2 Spot cho Node co giãn thay đổi chi phí và độ ổn định thế nào so với On-Demand?                  |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| **Cấu hình**  | C4: KEDA + Karpenter + Spot elastic, cùng workload với C3.                                               |
| **Điều kiện** | **Chạy tách riêng khỏi E2**, để độ trễ provisioning của E2 không bị lẫn với biến động capacity của Spot. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Node-hours và giá Spot theo thời điểm, cost per 1,000 tasks, số lần Spot interruption, Pending Pod duration, throughput dip khi bị thu hồi, duplicate message|
|**Dựa vào**|E2 (cấu hình Karpenter), E6 (mô hình chi phí); NodePool khai báo nhiều instance type; interruption handling của Karpenter; Worker xử lý SIGTERM gọn và chịu được message xử lý trùng (visibility timeout của SQS)|
|**Lưu ý**|Mức giảm giá của Spot phụ thuộc region, instance type và thời điểm. Dùng giá thực tế tại lúc chạy, không dùng con số cố định. Có thể thay bằng ước tính what-if từ Spot price history nếu không chạy thật.|

---

### E7 — Queue Target Sensitivity

| **Câu hỏi**  | Giá trị `queueLength` của KEDA ảnh hưởng thế nào đến performance và resource usage?                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Thiết kế** | Biến độc lập là `queueLength` với ba giá trị `Q_low`, `Q_medium`, `Q_high`. Dùng **một workload đại diện** (Step hoặc Burst). Các biến khác giữ nguyên. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Replica count, peak backlog, queue drain time, p95 latency, throughput, Pod-seconds|
|**Dựa vào**|E0 (μ, để chọn ba mức Q hợp lý), E2/E3 (cấu hình KEDA cơ sở)|
|**Ghi chú**|Đồ án khóa trước dùng `queueLength = 20` cố định; ở đây nó trở thành biến độc lập. Cũng giúp biện minh cho giá trị Q chọn ở E1.|

---

### E8 — Chaos Engineering

| **Câu hỏi**   | Hệ thống phục hồi thế nào khi Worker Pod (hoặc Node) bị mất lúc queue đang backlog và đang scale-out?                            |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Thiết kế**  | Bản nhẹ: `kubectl delete pod` hoặc terminate một Node trong lúc chạy E2, thay vì cài Chaos Mesh/Litmus. Chỉ làm khi E1–E6 đã ổn. |

|Mục|Nội dung|
|---|---|
|**Đo gì**|Deployment recovery time, duplicate message, queue backlog, throughput dip, recovery time|
|**Dựa vào**|E2 (kịch bản scale-out làm nền); visibility timeout của SQS; số message gửi và số message đã xử lý để đối chiếu|
|**Lưu ý**|Không tuyên bố "loss-less" nếu chưa có phương pháp kiểm chứng message count và end state.|

---

## 3. Phân bổ theo môn học

Khi viết báo cáo và trình bày ở mỗi môn học chỉ dựa trên phần tương ứng
### NT531 — Đánh giá hiệu năng mạng máy tính

| Mức      | Kịch bản       |
| -------- | -------------- |
| Core     | E0, E1, E2, E3, E4 |
| Optional | E7                |
### NT533 — Hệ tính toán phân bố

|Mức|Kịch bản|
|---|---|
|Core|E0, E1, E2, E3, E4|
|Advanced|E5|
|Optional|E6, E8|

Điểm cần thống nhất trong nhóm:
1. **Số queue dùng khi đo:** `NT531_REPORT.md` mô tả ba Amazon SQS queue và ba Worker deployment, còn `NT533_REPORT.md` mô tả chung một Worker Service. Cần chốt thí nghiệm chạy trên queue nào hay trên cả ba.
2. **Dạng workload cho E1:** chạy cả Step và Burst, hay chỉ một dạng, vì số lượt chạy nhân lên theo số dạng workload.
