# E3 — KEDA + Karpenter: pod và node elasticity

## 1. Mục tiêu và câu hỏi

Đánh giá điều gì xảy ra khi KEDA cần thêm worker nhưng cluster không còn node capacity phù hợp:

```text
Workload tăng → SQS backlog tăng → KEDA tăng desired worker
→ worker Pending → Karpenter tạo EC2 → node Ready → worker Ready
→ processing capacity tăng → queue phục hồi
```

**Câu hỏi:** Thời gian provision node ảnh hưởng thế nào đến scaling latency, backlog, completion latency và lượng tài nguyên sử dụng?

E3 tương ứng **E3 của NT533** và **KS3 của NT531**. So sánh **warm node vs elastic node** của KS4 được trình bày trong [E4](../E4/README.md), dùng lại các nhánh phù hợp của E3; dữ liệu phù hợp có thể dùng tiếp cho E6.

> Đây là thiết kế thí nghiệm, chưa phải kết quả đã đo. Cấu hình E3 đã được chuẩn bị nhưng cần pilot và xác nhận trên cluster.

### Các file và lệnh thực hiện

- [autoscaled-values.yaml](autoscaled-values.yaml): chọn NodePool riêng `e3-orders` cho Orders worker.
- [keda.yaml](keda.yaml): TriggerAuthentication và ScaledObject riêng cho Orders, min 1/max 10.
- [karpenter-values.yaml](karpenter-values.yaml): overlay cho chart platform, tạo NodePool/EC2NodeClass riêng `e3-orders`; mặc định On-Demand `c7i-flex.large`, giới hạn 8 CPU/16 GiB và không consolidate. Xác nhận AMI, quota, subnet, instance/AZ và chi phí trước khi dùng.
- [warm-capacity.yaml](warm-capacity.yaml): 10 pod giữ chỗ tạm với requests như Orders worker, giúp tạo node sẵn cho nhánh warm; cần xác nhận chúng Ready và node còn ổn định sau khi gỡ.
- [run.sh](run.sh): trong mỗi terminal, trước tiên chạy `cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling/experiments/E3`; các lệnh Bash riêng biệt cho chuẩn bị, warm/elastic, KEDA, tạo tải và khôi phục. **Mở file và chạy từng lệnh**, chọn một nhánh cho mỗi lượt; dòng `exit 0` ngăn chạy cả file, không copy dòng đó vào terminal.
- Workload Step version 3 dùng lại [step.js của E1](../E1/step.js): pilot 5 → 10 → 15 → 20 → 15 → 10 → 5 request/s, mỗi bậc 2 phút. Kiểm tra pilot để nhánh elastic thực sự phát sinh pod Pending do thiếu capacity và node mới. Nếu tải này chưa đủ, thiết kế lịch riêng, version và cách báo cáo trước khi chốt; giữ workload giống nhau trong hai nhánh.

Nhánh warm tạo node trước bằng pod giữ chỗ rồi xóa các pod đó; nhánh elastic bắt đầu với NodePool riêng chưa có node dư và một worker ban đầu. Sau một nhánh, khôi phục Orders, gỡ release NodePool E3 và xác nhận node/NodeClaim/EC2 E3 đã thu hồi trước khi thiết lập nhánh còn lại. Giữ baseline `../../.generated/e3/` cho đến khi xong cả hai nhánh; values đã lưu có thể nhạy cảm.

Chỉ xóa release `e3-capacity` sau khi xác nhận đúng tài nguyên E3 và worker đã quay về node phù hợp; thao tác này có thể chấm dứt EC2. Không gỡ Karpenter controller hoặc NodePool chung. Thu metrics riêng theo thời gian; summary k6 không chứa backlog hoặc completion latency.

## 2. Thành phần và phạm vi

| Thành phần | Dự kiến |
|---|---|
| Producer / consumer | Orders API `POST /jobs` / `orders-worker` |
| Queue | `orders-queue` |
| Pod autoscaling | KEDA SQS ScaledObject cho Orders |
| Node autoscaling | Karpenter, EC2NodeClass và NodePool On-Demand |
| Tạo tải | k6, ưu tiên Step hoặc Burst |
| Quan sát | Prometheus/Grafana, Kubernetes/Karpenter events, AWS và SQS/CloudWatch |

System nodes phải đủ chỗ cho KEDA, Karpenter, monitoring, API và các pod hệ thống để chúng tiếp tục hoạt động trong lúc worker thiếu capacity.

## 3. Biến và điều kiện kiểm soát

| Loại | Nội dung |
|---|---|
| Biến độc lập | Worker node capacity ban đầu: warm capacity hoặc elastic capacity. |
| Biến phụ thuộc | Pending duration, node provisioning, end-to-end scale time, throughput, backlog, latency, Pod-minutes và node-minutes. |
| Biến kiểm soát | Worker image/digest, requests/limits, node type, workload, KEDA settings, database, queue và điều kiện mạng. |

Giữ cùng min/max worker, queue target, polling và workload khi so sánh hai nhánh. Chọn cùng loại node/kiến trúc, region/AZ và image cache/pull policy nếu khả thi; nếu khác, ghi nhận như một giới hạn thay vì quy toàn bộ chênh lệch cho provisioning.

Không có HPA CPU hoặc ScaledObject độc lập khác cùng điều khiển Orders. Các API/controller vẫn chạy trên system node; chỉ kiểm soát capacity dành cho worker thí nghiệm.

## 4. Hai cấu hình so sánh

| Điều kiện | A — Warm node | B — Elastic node |
|---|---|---|
| Worker capacity ban đầu | Node phù hợp đã `Ready`, đủ cho workload đo. | Cố ý không đủ cho lượng worker cần thiết. |
| Node mới trong lượt | Không cần provision; giữ node ổn định. | Karpenter được phép provision node phù hợp. |
| Pod Pending do thiếu capacity | Không mong đợi; kiểm tra và ghi nhận. | Cần quan sát được để chứng minh đường scale hai tầng. |
| Điều kiện còn lại | Cùng workload, worker và KEDA settings. | Cùng workload, worker và KEDA settings. |

Đây là **warm node**, không phải pre-warm pod của E5. Số worker khởi đầu phải được chốt giống nhau giữa A và B. Đủ node ở A không bảo đảm pod luôn được xếp đúng node; kiểm tra label, taint/toleration, affinity, requests và pod/IP capacity.

Ở B, thiếu capacity phải là do điều kiện thiết kế của lượt đo và NodePool phải có khả năng đáp ứng yêu cầu pod. Pod Pending do lỗi image, IAM, subnet, NodePool không tương thích hoặc quota không chứng minh phép đo provisioning thành công. Không dùng các thao tác cưỡng bức làm ảnh hưởng system controllers để tạo thiếu capacity.

## 5. Cấu hình cần ghi lại

| Thông số | Warm | Elastic |
|---|---|---|
| Ngày, cluster, region / AZ | | |
| System node type / số lượng | | |
| Worker node type / số lượng ban đầu | | |
| CPU/memory allocatable còn trống, pod/IP capacity | | |
| Worker image digest / cache / pull policy | | |
| Worker CPU/memory requests, limits, concurrency | | |
| Queue, visibility timeout, retry / DLQ | | |
| KEDA min/max, queue target, polling / cooldown | | |
| NodePool, EC2NodeClass, AMI alias, capacity type | | |
| Instance type / AZ được phép, quota và subnet capacity | | |
| NodePool limits và chính sách consolidation | | |
| Database mode / work units / batch size | | |
| Workload profile / tốc độ / thời lượng | | |
| Nguồn timestamp, độ phân giải, đồng bộ đồng hồ | | |

Cấu hình dev trong repo hiện mô tả NodePool `default` On-Demand với nhiều instance category và `WhenEmptyOrUnderutilized`; **không mặc định đây là cấu hình tối ưu hoặc đang được apply cho E3**. Cần thiết kế cách cố định instance type cho phép so sánh, kiểm soát consolidation và xác nhận NodePool/EC2NodeClass tương thích trước khi đo. Thay đổi NodePool có thể tạo hoặc thu hồi EC2 và phát sinh chi phí.

## 6. Workload

Ưu tiên **Step hoặc Burst**, dùng cùng một profile cho A và B:

| Giai đoạn | Tốc độ gửi | Thời lượng | Mục tiêu |
|---|---:|---:|---|
| Baseline | | | Xác nhận worker, node và queue ổn định. |
| Step / burst | | | Tạo backlog và scale-out. |
| Duy trì | | | Đủ thời gian để đo xử lý phục hồi. |
| Ngừng tải / drain | 0 | | Đo queue phục hồi và quan sát scale-in. |

| Tham số | Giá trị |
|---|---|
| `workUnits` / `dbMode` / `batchSize` | |
| Tổng job mục tiêu | |
| Tốc độ gửi thực tế / accepted jobs | |
| Tiêu chí xử lý ổn định | |
| Tiêu chí queue rỗng và kết thúc lượt | |

Chạy pilot để chọn tải đủ tạo pod Pending trong B nhưng không quá sức producer/database hoặc vượt quota. Ghi nhận `dropped_iterations`, HTTP errors và partial failure; API latency không phải completion latency.

## 7. Timeline và chỉ số

| Mốc | Ý nghĩa | Nguồn / độ phân giải dự kiến |
|---|---|---|
| `T0` | Workload bắt đầu tăng. | |
| `T1` | Quan sát backlog tăng. | |
| `T2` | Desired worker replicas tăng. | |
| `T3` | Worker pod không schedule được / Pending do thiếu capacity. | |
| `T4` | Karpenter bắt đầu provisioning theo bằng chứng có được. | |
| `T5` | EC2 instance / NodeClaim xuất hiện; ghi rõ dùng mốc nào. | |
| `T6` | Node mới Ready. | |
| `T7` | Worker pod trên node mới Ready. | |
| `T8` | Throughput / processing đạt ổn định theo tiêu chí đã chốt. | |

| Chỉ số | Công thức / cách tính |
|---|---|
| KEDA response | `T2 - T0`. |
| Scheduling pressure | `T3 - T2`, nếu quan sát được. |
| Node provisioning | `T6 - T4`, nếu T4 được ghi trực tiếp. |
| Pod startup trên node | `T7 - T6`, nếu hai mốc áp dụng đúng cùng node/pod. |
| End-to-end scale | `T8 - T0`. |
| Queue / application | Peak visible/in-flight, drain time, throughput, completion latency p50/p95/p99. |
| Resource | Desired/ready pods, Pending duration, CPU, Pod-minutes, node-minutes. |

Đối chiếu **cùng NodeClaim, instance, node và pod** khi tính timeline. `T5` là NodeClaim hoặc EC2 là hai mốc khác nhau: ghi đúng nguồn, không gộp thành mốc chính xác giả. Nếu không quan sát được T4/T8 thì ghi `N/A` hoặc proxy, nêu độ phân giải và giới hạn. Nhánh warm không có provisioning nên các chỉ số liên quan ghi `N/A`.

SQS metrics xấp xỉ và có độ trễ; xem cả visible, in-flight, delayed và nhiều mẫu liên tiếp khi xác nhận drain. [AWS: xác nhận queue rỗng](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/confirm-queue-is-empty.html)

## 8. Chuẩn bị và quy trình

### Checklist

- [ ] Hoàn thành pilot E1/E2; Orders API → SQS → worker hoạt động.
- [ ] Ghi image digest, worker requests, workload và KEDA config được giữ cố định.
- [ ] Xác nhận system nodes và controller đủ tài nguyên trong cả hai nhánh.
- [ ] Chuẩn bị warm worker capacity và phương án elastic capacity có thể tái lập.
- [ ] Xác nhận Karpenter controller, NodePool/EC2NodeClass, IAM, subnet và quota.
- [ ] Xác nhận điều kiện scheduling: pod phù hợp với warm node và node Karpenter tạo ra.
- [ ] Chốt kiểm soát node type/AZ, cache image, consolidation và số worker ban đầu.
- [ ] Chuẩn bị k6 và thu SQS, worker metrics, HPA, node/pod/NodeClaim events.
- [ ] Chốt tiêu chí thành công, queue drain, throughput ổn định và điều kiện loại lượt đo.
- [ ] Kiểm tra tác động chi phí của EC2 mới và cách khôi phục capacity sau thí nghiệm.

### Mỗi lượt đo

1. Chọn A hoặc B; ghi node capacity và xác nhận controller / API / DB sẵn sàng.
2. Xác nhận queue hết tải, kiểm tra DLQ và worker ở trạng thái bắt đầu đã chốt.
3. Bắt đầu thu metrics, logs, events và timestamp; ghi cấu hình thực tế.
4. Phát workload đã định, ghi T0 và tải thực tế được chấp nhận.
5. Theo dõi backlog, desired/ready worker; với B, ghi lý do Pending và timeline node mới.
6. Dừng tải, tiếp tục đo throughput và queue drain; ghi CPU, pod/node count.
7. Lưu số task thành công/lỗi/duplicate, DLQ và events; xác nhận tính hợp lệ.
8. Đưa môi trường về trạng thái khởi đầu, không xóa message hoặc node ngoài phạm vi thí nghiệm; lặp lại ít nhất **3 lần** cho mỗi nhánh quan trọng.

Thay đổi thứ tự A/B giữa các lần lặp nếu có thể, đồng thời ghi thứ tự thực tế. Nếu B không có pod Pending do thiếu capacity hoặc không tạo node, không dùng lượt đó làm bằng chứng cho đường scale hai tầng. Khi kết thúc, khôi phục cấu hình autoscaler/node theo hướng dẫn được chuẩn bị riêng.

## 9. Kết quả từng lượt

| Run ID | Nhánh | Workload / ngày | Hợp lệ? | Lý do / ghi chú |
|---|---|---|---|---|
| E3-A01 | Warm | | | |
| E3-A02 | Warm | | | |
| E3-A03 | Warm | | | |
| E3-B01 | Elastic | | | |
| E3-B02 | Elastic | | | |
| E3-B03 | Elastic | | | |

### 9.1. Timeline nhánh elastic

| Run ID | T0 | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | Nguồn / proxy |
|---|---|---|---|---|---|---|---|---|---|---|
| E3-B01 | | | | | | | | | | |
| E3-B02 | | | | | | | | | | |
| E3-B03 | | | | | | | | | | |

| Run ID | Pending reason | NodeClaim / instance / node | KEDA response (s) | Pending duration (s) | Node provisioning (s) | Pod Ready (s) | End-to-end scale (s) |
|---|---|---|---:|---:|---:|---:|---:|
| E3-B01 | | | | | | | |
| E3-B02 | | | | | | | |
| E3-B03 | | | | | | | |

### 9.2. So sánh kết quả

| Run ID | Accepted / success / error / duplicate | Throughput | p95 / p99 | Peak backlog | Drain time | Max ready pods | Pod-minutes | Node-minutes |
|---|---|---:|---|---:|---:|---:|---:|---:|
| E3-A01 | | | | | | | | |
| E3-A02 | | | | | | | | |
| E3-A03 | | | | | | | | |
| E3-B01 | | | | | | | | |
| E3-B02 | | | | | | | | |
| E3-B03 | | | | | | | | |

## 10. Tổng hợp và phân tích

Ghi rõ cách tổng hợp các lần lặp và cửa sổ tính node-minutes; tách node system và worker khi phục vụ E6.

| Chỉ số | Warm: trung vị / khoảng | Elastic: trung vị / khoảng | Ghi chú |
|---|---|---|---|
| Throughput ổn định | | | |
| Completion latency p95/p99 | | | |
| Peak backlog / drain time | | | |
| End-to-end scaling latency | | | |
| Pending duration | N/A nếu không có Pending | | |
| Pod-minutes | | | |
| Worker node-minutes | | | |

**Biểu đồ cần lưu:** workload/throughput; backlog visible/in-flight; desired/ready/Pending pod; NodeClaim/node count và các mốc; CPU; Pod-minutes và node-minutes.

**Phân tích warm vs elastic:** _Điền chênh lệch quan sát được và đánh đổi giữa response và capacity duy trì._

**Giới hạn / lượt không hợp lệ:** _Điền timestamp proxy, sai số metric, loại node/AZ khác, quota, lỗi Pending hoặc ảnh hưởng database._

**Kết luận:** _Trả lời câu hỏi bằng số liệu, chỉ kết luận trong điều kiện đã đo._
