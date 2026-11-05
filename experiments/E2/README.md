# E2 — KEDA scaling response và scale-to-zero

## Mục tiêu và phạm vi

Đo vòng đời `0 → N → 0`: thời gian activation, job đầu tiên hoàn thành, xử lý backlog và scale về 0. E2 tương ứng E2 của NT533 và KS2 của NT531. Đây là thiết kế đã có cấu hình pilot, chưa phải kết quả đo; workload phải đủ lớn nếu muốn quan sát `N > 1`.

| Thành phần | Dự kiến |
|---|---|
| Producer | Orders API `POST /jobs` |
| Queue | `orders-queue` |
| Consumer | `orders-worker` trong namespace `retailstore` |
| Autoscaler | KEDA SQS ScaledObject, `minReplicaCount: 0` |
| Tạo tải | k6, qua Orders API |
| Quan sát | Prometheus/Grafana, Kubernetes events/logs, SQS/CloudWatch |

| Loại | Nội dung |
|---|---|
| Biến độc lập | Workload theo thời gian: idle → job đầu tiên → tải để scale-out → dừng tải. |
| Biến phụ thuộc | Activation, first-job latency, backlog, throughput, pod count, thời gian về 0, Pod-minutes. |
| Biến kiểm soát | Image/digest, requests/limits, concurrency, queue, database mode, node type/capacity, KEDA settings và workload. |

Giữ node phù hợp và đủ capacity cho max worker, ổn định trong lượt đo; ghi node thay đổi và pod Pending. Giữ cùng image/digest, requests/limits, concurrency, queue, database, workload và cấu hình KEDA. Chỉ KEDA điều khiển Orders; HPA do KEDA tạo là bình thường, không chạy thêm CPU-HPA độc lập.

## Chuẩn bị và cách chạy

Vào thư mục E2 ở mỗi terminal trước khi chạy các lệnh trong runbook: `cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling/experiments/E2`.

- Kiểm tra Orders API, worker, SQS, DB, IAM, monitoring và khả năng đối chiếu `jobId`; queue đã drain, kiểm tra visible/in-flight/delayed và DLQ. Không purge message ngoài kế hoạch.
- Mở [run.sh](run.sh) và chạy **từng lệnh hoặc nhóm lệnh** trong Git Bash: chuẩn bị → bật KEDA → chờ worker về 0 → gửi first job → tạo tải → chờ drain và scale về 0 → khôi phục. Không chạy toàn bộ file; `exit 0` ở đầu ngăn chạy nhầm.
- Script lưu Helm values và replica ban đầu trong `../../.generated/e2/`. Không ghi đè bản lưu, giữ cùng chart và chỉ xóa bản lưu sau khi xác nhận khôi phục. Dừng nếu gặp lỗi; `dbMode=light` ghi dữ liệu thử vào DB.
- [keda.yaml](keda.yaml) là pilot: min 0/max 10, queue target 10, polling 30s và cooldown 300s; cần xác nhận thực tế. Workload Step dùng [workload.js của E1](../E1/workload.js) sau khi ghi nhận first job.
- Ghi nhận producer được chấp nhận, `dropped_iterations`, errors, events/logs và metrics, kể cả khi worker biến mất. Lặp ít nhất **3 lượt hợp lệ**; k6 HTTP latency không phải completion latency.

## Cấu hình cần ghi lại

| Thông số | Giá trị thực tế |
|---|---|
| Ngày, cluster và Kubernetes version | |
| Node type, số node và capacity còn trống | |
| Worker image digest | |
| CPU/memory requests và limits | |
| Worker concurrency / SQS batch | |
| Database mode / work units | |
| Queue, visibility timeout, retry / DLQ | |
| KEDA version / ScaledObject name | |
| `minReplicaCount` / `maxReplicaCount` | `0` / |
| `queueLength`, `scaleOnInFlight`, `scaleOnDelayed` | |
| `pollingInterval` / `cooldownPeriod` | |
| Image đã cache trên node? / image pull policy | |
| Nguồn timestamp, độ phân giải và đồng bộ đồng hồ | |

## Workload

| Giai đoạn | Mục đích | Giá trị thực tế |
|---|---|---|
| Idle | Queue rỗng, worker về 0, xác nhận node sẵn sàng. | |
| First job | Gửi một job có thể đối chiếu `jobId` và timestamp. | |
| Tải tăng / burst | Tạo đủ backlog để quan sát scale-out, có thể lên N > 1. | |
| Duy trì | Quan sát xử lý và biến động pod. | |
| Dừng tải | Không gửi job mới; theo dõi drain và scale về 0. | |

Chốt tốc độ gửi, thời lượng, tổng job, `workUnits`, `dbMode` và batch size sau pilot. Cần nhiều mẫu liên tiếp để đánh giá queue drain vì SQS metrics gần đúng; không chỉ dựa vào `visible=0`.

## Timeline và chỉ số

| Mốc | Ý nghĩa | Nguồn / độ phân giải dự kiến |
|---|---|---|
| `T0` | Job đầu tiên được enqueue thành công; lưu `jobId`. | |
| `T1` | Quan sát KEDA nhận trigger active, nếu thu được trực tiếp. | |
| `T2` | Desired replicas của worker tăng từ 0. | |
| `T3` | Worker pod được tạo. | |
| `T4` | Worker pod Ready. | |
| `T5` | Job `jobId` đầu tiên hoàn thành thành công. | |
| `T_idle` | Lần cuối trigger còn active hoặc mốc gần đúng đã ghi rõ. | |
| `T_zero` | Desired và pod worker về 0 theo quy ước đã chọn. | |

| Đại lượng | Công thức / cách tính |
|---|---|
| Detection latency | `T1 - T0`, nếu quan sát được T1. |
| Time to desired | `T2 - T0`. |
| Pod Ready latency | `T4 - T0`. |
| First-job completion latency | `T5 - T0`; đối chiếu đúng job đã enqueue ở T0. |
| Scale-down-to-zero delay | `T_zero - T_idle`. |
| Throughput / completion latency | Task thành công mỗi giây; p50/p95/p99 theo quy ước đo. |
| Queue và tài nguyên | Peak visible/in-flight, drain time, desired/ready pods, CPU và Pod-minutes. |

Đối chiếu đúng `jobId` tại T0/T5. Worker có thể xử lý job trước khi pod được quan sát Ready; các mốc không nhất thiết theo đúng thứ tự. Nếu không ghi trực tiếp T1 hoặc `T_idle`, ghi `N/A` hoặc proxy và độ phân giải. Cooldown KEDA liên quan scale về 0; giai đoạn 1 → N còn chịu tác động của HPA.

## Kết quả từng lượt

| Run ID | Ngày / profile | Hợp lệ? | Lý do / ghi chú |
|---|---|---|---|
| E2-01 | | | |
| E2-02 | | | |
| E2-03 | | | |

### Activation và first job

| Run ID | Job ID | T0 | T1 | T2 | T3 | T4 | T5 | Nguồn / proxy |
|---|---|---|---|---|---|---|---|---|
| E2-01 | | | | | | | | |
| E2-02 | | | | | | | | |
| E2-03 | | | | | | | | |

| Run ID | Detection (s) | Time to desired (s) | Pod Ready (s) | First-job completion (s) | Max ready pods |
|---|---:|---:|---:|---:|---:|
| E2-01 | | | | | |
| E2-02 | | | | | |
| E2-03 | | | | | |

### Processing và scale-in

| Run ID | Tasks accepted / success / error / duplicate | Peak backlog | Throughput | p95 / p99 | Drain time | T_idle | T_zero | Delay về 0 | Pod-minutes |
|---|---|---:|---:|---|---:|---|---|---:|---:|
| E2-01 | | | | | | | | | |
| E2-02 | | | | | | | | | |
| E2-03 | | | | | | | | | |

## Tổng hợp và phân tích

| Chỉ số | Trung vị | Khoảng giá trị | Ghi chú |
|---|---:|---|---|
| Pod Ready latency | | | |
| First-job completion latency | | | |
| Peak backlog | | | |
| Scale-down-to-zero delay | | | |
| Pod-minutes | | | |

**Biểu đồ cần lưu:** workload/throughput, visible/in-flight, desired/ready pods, activation/completion, scale-in về 0 và node count/Pending.

**Nhận xét:** _Điền kết quả về activation, cold start, bottleneck và scale-in._

**Giới hạn / lượt không hợp lệ:** _Điền timestamp thiếu, retry, sai số metric, node thay đổi hoặc thiếu capacity._

**Kết luận:** _Trả lời câu hỏi dựa trên số liệu và phạm vi thực nghiệm._
