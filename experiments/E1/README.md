# E1 — Fixed vs CPU-HPA vs KEDA SQS

## Mục tiêu và cấu hình

So sánh ba chiến lược trên cùng Orders worker, SQS queue và workload, với node capacity đủ và số node ổn định. E0 chọn μ sơ bộ ≈ **8,9 task/s/worker**; kết quả E1 vẫn cần pilot và đo thực tế.

| Phương án | Cấu hình pilot | Điều kiện đầu mỗi lượt |
|---|---|---|
| Fixed | 2 worker | 2 desired/Ready, không có HPA/ScaledObject |
| CPU-HPA | min 1, max 10, CPU target 60% request | 1 desired/Ready, chỉ có `e1-orders-cpu` |
| KEDA SQS | min 1, max 10, target 10 message/Pod, tính in-flight | 1 desired/Ready, chỉ có `e1-orders-sqs` và HPA do nó tạo |

Workload pilot theo E0, với batch 1 và `LOW_RATE=5`, `HIGH_RATE=27` khi chạy [workload.js](workload.js): Steady 5 request/s × 2 phút; Step 5 × 1 phút → 27 × 2 phút → 5 × 1 phút; Burst 5 × 1 phút → 27 × 30 giây → 5 × 1 phút. K6 đo request/s; số task thực tế phải dựa vào accepted jobs. `WORK_UNITS=100` đã được người chạy xác nhận cho E0; giữ `DB_MODE=light`, `BATCH_SIZE=1` và cùng cấu hình giữa ba nhánh pilot. DB mode `light` ghi dữ liệu thử vào database.

Lưu ý khi pilot: ở E0, 5 request/s đã dùng trung bình khoảng 511m CPU trên một worker, tương đương gần 399% request 128m, cao hơn target HPA 60%. Vì vậy CPU-HPA có thể scale ngay trong pha tải thấp; ghi nhận diễn biến này, không giả định đến pha 27 request/s mới scale. CPU E0 là số đo của một lượt và còn phụ thuộc cấu hình workload thực tế.

Giữ request 128m và target 60% cho pilot để nhất quán với E0. Với một Pod dùng 511m, công thức lý tưởng đề xuất khoảng 7 Pod tại target 60%; target 70%, 80%, 90% vẫn đề xuất lần lượt khoảng 6, 5, 5 Pod. Số thực tế phụ thuộc metric, dung sai, tốc độ scale và cách tải được chia. Nếu pilot cho thấy HPA dùng quá nhiều Pod, một hướng khảo sát riêng là tăng CPU request, ví dụ 1000m với target 60% tương ứng 600m/Pod. Khi đó phải chuẩn bị đủ node capacity, vì 10 Pod request 1000m cần ít nhất 10 CPU allocatable dành riêng cho chúng, và xác nhận lại μ. Không thay request chỉ cho HPA trong phép so sánh chính.

## Chuẩn bị

- Cần Helm, kubectl, AWS CLI, Python, k6, Metrics Server, KEDA, Prometheus, Orders API/worker và SQS; giữ Prometheus port-forward 9090 và Orders API port-forward 8082. Các lệnh dùng Git Bash sau khi `cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling/experiments/E1`; mỗi terminal thao tác với file cần vào cùng thư mục E1.
- Kiểm tra AWS context/region, image digest, CPU/memory requests, concurrency, DB mode, queue URL, visibility timeout và DLQ. Giữ chúng cố định. Không có producer/consumer khác; queue và DLQ phải rỗng trước từng lượt, không purge.
- Chuẩn bị đủ CPU, memory, pod/IP capacity cho 10 worker. Giữ node ổn định; kiểm tra Pending và node count. Collector không tự đảm bảo điều kiện capacity này.
- Dùng [run.sh](run.sh) **từng nhóm lệnh**, không chạy cả file: lưu Helm values và replica gốc → chuyển sang Fixed → CPU-HPA → KEDA → khôi phục. Các file baseline ở `../../.generated/e1/` có thể nhạy cảm, không chia sẻ/ghi đè. Kiểm tra tên, label, owner và autoscaler trỏ tới worker trước khi xóa hoặc chuyển nhánh. Trong mỗi nhánh chỉ chạy một cơ chế điều khiển replica. Sau mỗi nhánh chờ queue drain trước khi chuyển.
- HPA/KEDA cần trở về **1 desired/Ready** trước mỗi lượt; có thể phải chờ scale-down. Fixed cần 2 Ready. `cooldownPeriod` của KEDA liên quan scale về 0, không phải quy tắc giảm N→1 của E1.

Ví dụ mở Prometheus và Orders trong **hai terminal riêng**:

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80
```

## Một lượt đo

Ví dụ Fixed + Step, lần 1. Đổi `--variant` thành `fixed`, `hpa` hoặc `keda`; `--profile` thành `steady`, `step` hoặc `burst`; tăng `--attempt` cho mỗi lượt. Lệnh tạo hồ sơ mới, từ chối ghi đè. Giá trị mặc định là context `twolevel-dev`, namespace `retailstore`, Deployment `orders-worker`, queue `orders-queue`, region `us-east-1`; xem `python init.py init --help` để đổi.

```bash
python init.py init --variant fixed --profile step --attempt 1
RUN_DIR=../results/E1/E1-fixed-step-r01
```

Trong terminal collector, đặt đúng `RUN_DIR`, chạy kiểm tra và sau đó bắt đầu thu:

```bash
RUN_DIR=../results/E1/E1-fixed-step-r01
python collect.py --run-dir "$RUN_DIR" --check
python collect.py --run-dir "$RUN_DIR"
```

Collector kiểm tra nhánh, số Pod Ready, autoscaler, queue worker, SQS/DLQ và Prometheus; chờ dòng **ĐANG THU**, sau đó thu baseline 15–30 giây. Kiểm tra cũng cần quyền AWS/kubectl và KEDA CRD. Collector chỉ đọc tài nguyên, không apply/scale/purge.

Trong terminal khác, đặt cùng `RUN_DIR`, chạy k6 và lưu summary. Giữ `WORK_UNITS`, `DB_MODE`, `BATCH_SIZE`, rate và thời lượng như nhau giữa các chiến lược; đổi profile cho đúng hồ sơ:

```bash
RUN_DIR=../results/E1/E1-fixed-step-r01
k6 run -e PROFILE=step -e LOW_RATE=5 -e HIGH_RATE=27 -e WORK_UNITS=100 -e DB_MODE=light -e BATCH_SIZE=1 \
  --summary-export "$RUN_DIR/raw/k6-summary.json" ./workload.js
```

Summary cũng lưu rate, batch size, work units, DB mode và profile thực tế; report từ chối nếu profile không khớp hồ sơ. K6 ghi mốc UTC vào console và summary (`workload_started_at_unix_ms`, `workload_finished_at_unix_ms`). Mốc kết thúc là sau các iteration đang chạy, không bao gồm drain; dừng cưỡng bức có thể không ghi được mốc này. Ghi các biến đã dùng vào `notes.md`.

Sau khi k6 kết thúc, **tiếp tục thu ít nhất 300 giây** để mọi lượt có cùng cửa sổ so sánh tài nguyên. Đồng thời chờ queue drain: visible, in-flight, delayed đều 0 qua ít nhất ba mẫu liên tiếp, đối chiếu DLQ và task thành công. Nếu chưa drain sau 300 giây, tiếp tục thu đến khi drain; không purge. Sau đó nhấn Ctrl+C **một lần** ở collector và chờ ghi xong. Lập báo cáo:

```bash
python report.py --run-dir "$RUN_DIR"
```

`report.json` không ghi đè. Mặc định `--after 300` tính tài nguyên trong cửa sổ từ bắt đầu k6 đến 300 giây sau khi k6 kết thúc; giữ cùng giá trị cho mọi lượt. Drain được xét trên toàn bộ mẫu thu sau k6. Nếu thay đổi `--after`, phải thu ít nhất đúng khoảng đó ở mọi lượt và ghi lại trong `notes.md`.

## Output và cách đọc

Mỗi hồ sơ ở `../results/E1/` gồm `metadata.json`, `notes.md`, `raw/k6-summary.json`, `collection.json`, `collection-summary.md`, các mẫu SQS/worker trong `metrics/` và `events/`, metric Prometheus theo thời gian trong `metrics/`, và `report.json`. Thư mục results bị Git bỏ qua; sao lưu riêng nếu cần. File `collect-errors.jsonl` chỉ xuất hiện khi có lỗi thu.

Báo cáo có accepted jobs, throughput thành công trung bình trong lúc k6 phát tải, số task theo status, p50/p95/p99 E2E, peak visible + in-flight, thời gian xác nhận drain, ready Pod-minutes, CPU trung bình và thời điểm scale-out đầu tiên từ lúc bắt đầu, cũng như sau pha tải cao của Step/Burst. Giữ raw data để vẽ đồ thị và đối chiếu desired/ready, Pending và node. Report không tự chấm lượt hợp lệ.

- SQS counts và drain là xấp xỉ. Drain là mốc xác nhận sau **ba mẫu 0**, không phải thời điểm chính xác queue rỗng; queue rỗng không chứng minh mọi job đã thành công.
- `completed_by_status_approx` và latency dùng cửa sổ cố định như Pod-minutes; nếu drain muộn hơn cửa sổ, dùng thêm `completed_by_status_through_drain_approx` để đối chiếu. Các bộ đếm này vẫn chỉ là ước lượng từ metric, không thay thế đối soát job ID.
- Counter là chênh lệch các mẫu **nằm trong cửa sổ**; có thể thiếu đầu series, pod sống ngắn hoặc dữ liệu khi pod bị xóa. Histogram E2E của worker gồm cả error/duplicate; phân vị là ước lượng bucket, `null` khi thiếu dữ liệu hoặc vượt bucket hữu hạn. Không coi các giá trị này là đối soát job ID.
- Kiểm tra `collection.json` và warnings, k6 failed/dropped iterations, success/error/duplicate, DLQ, target Prometheus, image, node, Pending và mức coverage trước khi kết luận. Nếu thiếu metric, queue chưa drain, node thay đổi hoặc workload không đạt, ghi nguyên nhân và đánh giá lại lượt; không thay giá trị thiếu bằng 0.
- Chạy pilot trước để xác nhận tải phân biệt được các nhánh và giữ kết quả pilot riêng. Khi chốt cấu hình, chạy ít nhất **3 lượt hợp lệ cho mỗi strategy × profile**, cùng workload và cửa sổ. Step/Burst là chính; Steady làm tham chiếu. Tổng hợp trung vị, khoảng biến thiên, throughput, p95, peak backlog, drain và Pod-minutes.

Sau khi tự đánh giá lượt hợp lệ, có thể dùng [compare.py](compare.py) để in bảng trung vị và min–max của các lượt **cùng profile**. Truyền đường dẫn `report.json` của từng lượt được chọn; ví dụ với một lượt mỗi nhánh (lượt chính thức nên có ít nhất ba mỗi nhánh):

```bash
python compare.py \
  ../results/E1/E1-fixed-step-r01/report.json \
  ../results/E1/E1-hpa-step-r01/report.json \
  ../results/E1/E1-keda-step-r01/report.json
```

Script kiểm tra profile, tham số workload và cửa sổ trùng nhau, nhưng không tự xác nhận các lượt hợp lệ hay cùng image/node. Đối chiếu warnings, điều kiện và dữ liệu gốc trước khi dùng bảng.

## Kết quả

| Profile | Chiến lược | Run ID | Accepted / success | p95 E2E | Peak backlog | Drain | Ready Pod-minutes | Hợp lệ / ghi chú |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

E1 hiện chưa có kết quả chính thức. Sau các lượt đo, ghi số liệu và kết luận dựa trên cùng cửa sổ, không suy ra kết quả trước khi chạy.
