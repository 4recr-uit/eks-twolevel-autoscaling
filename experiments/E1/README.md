# E1 — Fixed Replicas, CPU-HPA và KEDA SQS

## Mục tiêu và phạm vi

So sánh throughput, latency, backlog, khả năng scale và tài nguyên của Fixed, CPU-HPA và KEDA SQS với cùng worker, workload và hạ tầng. Đây là thiết kế thí nghiệm, chưa phải kết quả đo.

| Thành phần | Giá trị |
|---|---|
| Worker Deployment | `orders-worker` |
| SQS queue | `orders-queue` |
| Namespace | `retailstore` |
| Database mode | _Điền trước khi chạy_ |

| Thành phần | Vai trò |
|---|---|
| Load generator | Tạo task theo profile Steady, Step hoặc Burst. |
| Amazon SQS | Lưu task chờ worker xử lý. |
| Worker | Nhận, xử lý và hoàn thành task. |
| Kubernetes HPA | Điều chỉnh số worker theo CPU trong phương án CPU-HPA. |
| KEDA | Theo dõi SQS và quản lý autoscaling trong phương án KEDA. |
| Metrics Server | Cung cấp CPU resource metrics cho CPU-HPA. |
| Prometheus / Grafana | Thu thập và quan sát metrics của workload và worker. |
| CloudWatch / SQS API | Quan sát thông tin queue. |

| Loại biến | Nội dung |
|---|---|
| Biến độc lập | Chiến lược: Fixed, CPU-HPA hoặc KEDA SQS. |
| Biến phụ thuộc | Throughput, latency p50/p95/p99, queue depth, drain time, replica count, CPU và Pod-minutes. |
| Biến kiểm soát | Worker image, requests/limits, concurrency, node type, số node, workload và cấu hình queue/database. |

Giữ cùng image/digest, requests/limits, concurrency, cấu hình queue/database và workload. Chuẩn bị node đủ cho `maxReplicas`, kiểm tra CPU/memory, pod/IP capacity và scheduling; giữ số node ổn định, không để Karpenter tạo hoặc thu gọn node trong lượt đo. Nếu node thay đổi hoặc pod Pending do thiếu capacity, ghi nhận và đánh giá lượt không hợp lệ.

Mỗi worker chỉ có một cơ chế điều khiển replica; HPA do KEDA tạo là một phần của cấu hình KEDA.

| Phương án | Fixed replicas | CPU-HPA | KEDA ScaledObject |
|---|---|---|---|
| Fixed | Bật | Tắt | Tắt |
| CPU-HPA | Không áp đặt số replica cố định | Bật | Tắt |
| KEDA SQS | Không áp đặt số replica cố định | Tắt | Bật |

## Chuẩn bị và cách chạy

- Cần Helm, kubectl, k6, ứng dụng, Metrics Server và monitoring hoạt động; KEDA Pod Identity phải đọc được Orders SQS.
- Kiểm tra không có HPA/ScaledObject khác điều khiển Orders; queue đã drain và DLQ được ghi nhận. Không purge message. Chuẩn bị và xác nhận node đủ cho 10 worker theo cấu hình pilot.
- Mở [run.sh](run.sh) trong Git Bash và chạy **từng lệnh hoặc nhóm lệnh**: chuẩn bị → Fixed → CPU-HPA → KEDA → khôi phục. Không chạy toàn bộ file; `exit 0` ở đầu chỉ để ngăn chạy nhầm.
- Lưu Helm values và replica gốc tại `.generated/e1/` trước khi thay đổi; không ghi đè, giữ cùng chart, bảo vệ file nhạy cảm và chỉ xóa sau khi xác nhận khôi phục. Không dùng `06-deploy-autoscaling.sh` song song cho cùng worker.
- Trước mỗi lượt, chờ queue drain, giữ port-forward, thu metrics/logs, chạy profile và lưu kết quả với tên riêng. Dừng nếu có lỗi. `DB_MODE=light` ghi dữ liệu thử vào DB; khôi phục cấu hình không xóa dữ liệu này.
- Lặp ít nhất **3 lượt hợp lệ cho mỗi tổ hợp chiến lược × workload**, ghi thứ tự và lý do loại lượt. k6 `LOW_RATE`/`HIGH_RATE` là request/s; batch và partial failure ảnh hưởng số job được chấp nhận. k6 summary không chứa SQS backlog hay completion latency.

Cấu hình trong repo là **pilot**, không phải kết quả: Fixed 2 replica; HPA và KEDA min 1/max 10; HPA CPU 60%; KEDA queue target 10, polling 30s, cooldown 300s. Chốt thông số sau E0/pilot; HPA và KEDA dùng cùng min/max trong so sánh chính.

## Cấu hình cần ghi

### Hạ tầng

| Thông số | Giá trị |
|---|---|
| Ngày chạy | |
| AWS region | us-east-1 |
| EKS cluster / Kubernetes version | 1.36 |
| Node type | |
| Số node | 2 |
| Tổng CPU/memory allocatable còn lại trước lượt chạy | |
| Giới hạn pod/IP trên node | |
| Metrics Server version | |
| KEDA version | |
| Prometheus / Grafana version | |

### Worker

| Thông số | Giá trị |
|---|---|
| Deployment | |
| Image và digest | |
| CPU request / limit | |
| Memory request / limit | |
| Worker concurrency | |
| SQS max messages mỗi lần nhận | |
| Database mode | |
| Cấu hình task / work units | |
| Visibility timeout | |
| Retry / DLQ policy | |

### Chiến lược scaling

| Thông số | Fixed | CPU-HPA | KEDA SQS |
|---|---|---|---|
| Số replica cố định | | Không áp dụng | Không áp dụng |
| Min replicas | Không áp dụng | | |
| Max replicas | Không áp dụng | | |
| CPU target | Không áp dụng | | Không áp dụng |
| Queue target | Không áp dụng | Không áp dụng | |
| Polling interval | Không áp dụng | | |
| Scale-down / cooldown | Không áp dụng | | |
| Tính message in-flight | Không áp dụng | Không áp dụng | |

**Lý do chọn Fixed và các ngưỡng:** _Điền sau pilot._

## Workload

Ghi tốc độ, thời lượng và tổng task thực tế. Chọn mức tải sau E0/pilot; Step và Burst có thể chạy trước để kiểm tra phản ứng.

### Steady

| Thông số | Giá trị |
|---|---|
| Tốc độ gửi mục tiêu | |
| Thời gian phát tải | |
| Tổng task mục tiêu | |
| Thời gian quan sát sau phát tải | |

### Step

| Giai đoạn | Tốc độ gửi | Thời lượng |
|---|---:|---:|
| Tải thấp | | |
| Tải cao | | |
| Giảm / ngừng tải | | |
| Quan sát drain | Không gửi task mới | |

### Burst

| Thông số | Giá trị |
|---|---|
| Tốc độ trước burst | |
| Tốc độ burst | |
| Thời lượng burst | |
| Tốc độ sau burst | |
| Tổng task mục tiêu | |
| Thời gian quan sát drain | |

## Chỉ số và quy ước

| Nhóm | Chỉ số | Định nghĩa / nguồn đo |
|---|---|---|
| Application | Throughput | Số task hoàn thành thành công mỗi giây. |
| Application | Completion latency p50/p95/p99 | Từ thời điểm enqueue đến thời điểm hoàn thành theo định nghĩa của thí nghiệm. |
| Application | Error / failure rate | Tỷ lệ task lỗi; ghi rõ cách tính retry và duplicate. |
| Queue | Visible messages | Số message chờ được nhận. |
| Queue | In-flight messages | Số message đã được nhận nhưng chưa hoàn tất/xóa. |
| Queue | Peak backlog | Giá trị backlog cao nhất trong lượt chạy. |
| Queue | Drain time | Từ khi ngừng phát tải đến khi đạt tiêu chí queue rỗng và task hoàn thành. |
| Scaling | Desired / ready replicas | Số pod được yêu cầu và số pod thực sự sẵn sàng theo thời gian. |
| Scaling | Time to first scale-out | Từ lúc tải tăng đến lúc desired replicas tăng; ghi thêm lúc pod mới Ready. |
| Scaling | Stable capacity time | Thời gian đến khi đạt năng lực xử lý ổn định theo tiêu chí đã định. |
| Resource | CPU utilization | CPU của worker theo thời gian; ghi rõ đơn vị và mẫu đo. |
| Resource | Pod-minutes | Tổng thời gian chạy của tất cả worker pod trong cửa sổ đo. |

### Quy ước cần chốt trước khi chạy

| Nội dung | Quy ước |
|---|---|
| Bắt đầu / kết thúc cửa sổ đo | |
| Cách tính backlog: visible hay visible + in-flight | |
| Tiêu chí queue rỗng | |
| Tiêu chí processing capacity ổn định | |
| Cách xác định một task hoàn thành thành công | |
| Cách xử lý retry / duplicate / DLQ | |
| Nguồn thời gian enqueue và completion | |
| Khoảng lấy mẫu / độ phân giải của từng nguồn metric | |

SQS metrics gần đúng: kiểm tra visible, in-flight, delayed và nhiều mẫu liên tiếp khi xác nhận drain. Kiểm tra histogram buckets, độ phân giải, retry và duplicate trước khi dùng p95/p99; đối chiếu task thành công thay vì coi queue rỗng là bằng chứng hoàn thành.

## Ma trận chạy

| Workload | Fixed | CPU-HPA | KEDA SQS |
|---|---|---|---|
| Steady | Lần 1 / 2 / 3 | Lần 1 / 2 / 3 | Lần 1 / 2 / 3 |
| Step | Lần 1 / 2 / 3 | Lần 1 / 2 / 3 | Lần 1 / 2 / 3 |
| Burst | Lần 1 / 2 / 3 | Lần 1 / 2 / 3 | Lần 1 / 2 / 3 |

## Kết quả từng lượt

| Run ID | Workload | Chiến lược | Lần | Hợp lệ? | Ghi chú |
|---|---|---|---:|---|---|
| | Steady | Fixed | | | |
| | Steady | CPU-HPA | | | |
| | Steady | KEDA SQS | | | |
| | Step | Fixed | | | |
| | Step | CPU-HPA | | | |
| | Step | KEDA SQS | | | |
| | Burst | Fixed | | | |
| | Burst | CPU-HPA | | | |
| | Burst | KEDA SQS | | | |

### Application performance

| Run ID | Tasks gửi thành công | Tasks hoàn thành | Throughput (tasks/s) | p50 (s) | p95 (s) | p99 (s) | Error / duplicate / DLQ |
|---|---:|---:|---:|---:|---:|---:|---|
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |

### Queue behavior

| Run ID | Peak visible | Peak in-flight | Peak backlog theo quy ước | Drain time (s) | Message còn lại |
|---|---:|---:|---:|---:|---|
| | | | | | |
| | | | | | |
| | | | | | |

### Scaling và resource usage

| Run ID | Desired replicas tối đa | Ready replicas tối đa | First scale-out (s) | Pod mới Ready (s) | Stable capacity (s) | CPU | Pod-minutes |
|---|---:|---:|---:|---:|---:|---|---:|
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |

Với Fixed, ghi `N/A` cho chỉ số scale-out không áp dụng.

## Tổng hợp kết quả

Ghi trung vị, khoảng quan sát và cách xử lý lượt không hợp lệ.

| Workload | Chiến lược | Throughput | p95 latency | Peak backlog | Drain time | Pod-minutes |
|---|---|---:|---:|---:|---:|---:|
| Steady | Fixed | | | | | |
| Steady | CPU-HPA | | | | | |
| Steady | KEDA SQS | | | | | |
| Step | Fixed | | | | | |
| Step | CPU-HPA | | | | | |
| Step | KEDA SQS | | | | | |
| Burst | Fixed | | | | | |
| Burst | CPU-HPA | | | | | |
| Burst | KEDA SQS | | | | | |

**Biểu đồ cần lưu:** tải gửi/throughput; visible/in-flight; completion latency; desired/ready replicas; CPU; drain time, Pod-minutes; node count và Pending.

### Phân tích

- **Fixed:** _Điền nhận xét về throughput, backlog, latency và tài nguyên._
- **CPU-HPA:** _Điền tương quan giữa CPU, thời điểm scale và backlog._
- **KEDA SQS:** _Điền tương quan giữa queue depth, thời điểm scale và drain time._
- **So sánh:** _Điền đánh đổi hiệu năng và Pod-minutes theo từng workload._

### Giới hạn và sự cố

| Nội dung | Ghi nhận |
|---|---|
| Lượt bị loại và lý do | |
| Thiếu mẫu / độ phân giải metric | |
| Retry, duplicate hoặc DLQ | |
| Node thay đổi / pod Pending | |
| Database hoặc dịch vụ khác trở thành nút thắt | |
| Giới hạn khác | |

**Kết luận:** _Trả lời câu hỏi bằng dữ liệu, trong phạm vi cấu hình đã đo._

Nếu còn thời gian, khảo sát thêm Fixed replicas, CPU/queue target hoặc workload CPU và I/O; scale-to-zero và tương tác Karpenter có thí nghiệm riêng.
