# E0 — Worker capacity calibration và workload modeling

## Mục tiêu

Ước lượng throughput thành công của một worker khi có đủ việc, rồi dùng kết quả làm cơ sở chọn tải Steady, Step và Burst cho các pilot tiếp theo. E0 là bước chuẩn bị, không so sánh autoscaler. Kết quả của phiên thu hiện có được tổng hợp ở cuối tài liệu.

## Phạm vi và điều kiện

- Bắt đầu với `orders-worker` và `orders-queue`; xác nhận không có consumer khác đọc queue.
- Không có HPA hoặc ScaledObject điều khiển Orders, giữ đúng một worker Ready và node capacity ổn định.
- Ghi image digest, node type, CPU/memory requests và limits, worker concurrency, SQS polling/batch, `workUnits`, `dbMode` và batch size. Giữ chúng cố định trong từng nhóm so sánh.
- Kiểm tra metric worker, Prometheus/Grafana, SQS/CloudWatch, queue và DLQ trước khi chạy. Không purge hoặc xóa message ngoài phạm vi thí nghiệm.
- Lưu cấu hình và replica ban đầu; chuẩn bị cách khôi phục trước khi đổi deployment. Workload `dbMode=light` ghi dữ liệu thử vào database.

## Quy trình đề xuất

1. Xác định mức tải thấp; chạy khoảng 2–3 phút và đo số job thực tế được chấp nhận, task thành công/lỗi, CPU/memory và backlog.
2. Dừng producer, tiếp tục thu dữ liệu đến khi queue drain theo tiêu chí đã định. Kiểm tra lỗi, retries và DLQ.
3. Lặp ở khoảng 3–5 mức tải tăng dần, hoặc thêm mức khi chưa tìm được vùng bão hòa. Dừng và điều tra khi producer, database hoặc worker gặp lỗi hay giới hạn ngoài dự kiến.
4. Khi có backlog liên tục và throughput thành công gần ổn định, chọn mức đại diện và chạy 3 lượt độc lập. Ghi cửa sổ đo ổn định, trung vị và khoảng min–max.
5. Dùng khoảng throughput đo được (`μ`) để đề xuất workload cho E1–E3, rồi pilot. `λ/μ` chỉ là ước lượng ban đầu; nhiều worker có thể không scale tuyến tính và KEDA dựa trên queue, không trực tiếp trên λ/μ.
6. Lưu cấu hình, thời gian UTC, kết quả producer, metrics và logs; khôi phục worker và xác nhận trạng thái ban đầu.

Workload riêng ở [workload.js](workload.js) tính tốc độ theo **request/s**. Số task được chấp nhận còn phụ thuộc batch size và kết quả từng request. SQS backlog là xấp xỉ; Prometheus counters không thay thế đối soát job ID. Nếu không thấy plateau hoặc không đủ mẫu đáng tin cậy, ghi `μ: chưa xác định`.

## Chạy lại E0 khi cần

Công cụ E0 nằm trong thư mục này, độc lập với E1. Mỗi terminal thực hiện lệnh file phải vào thư mục E0 trước: `cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling/experiments/E0`. Cần Python, AWS CLI, kubectl, k6, Prometheus, Orders API và SQS. Giữ 1 worker Ready, tắt autoscaler cho worker; kiểm tra queue/DLQ rỗng và không có producer/consumer khác. Không purge queue. `DB_MODE=light` ghi dữ liệu thử vào database.

Khi cần chuyển worker sang cấu hình E0, dùng từng nhóm lệnh trong [run.sh](run.sh) để lưu cấu hình, áp dụng [fixed-values.yaml](fixed-values.yaml) và khôi phục sau khi đo. Không chạy cả file; kiểm tra autoscaler trước khi thay đổi. Không ghi đè hoặc chia sẻ bản lưu `../../.generated/e0/`.

1. Tạo hồ sơ mới (mỗi lượt đổi `--attempt`):

```bash
python run.py init --variant single-worker --profile steady --attempt 3
RUN_DIR=../results/E0/E0-single-worker-steady-r03
```

2. Mở hai terminal để giữ port-forward Prometheus và Orders API:

```bash
kubectl --context twolevel-dev -n monitoring port-forward service/monitoring-kube-prometheus-prometheus 9090:9090
kubectl --context twolevel-dev -n retailstore port-forward service/orders 8082:80
```

3. Trong terminal thu, đặt lại `RUN_DIR` và chạy bộ thu. Chờ `ĐANG THU`, lấy 15–30 giây baseline:

```bash
RUN_DIR=../results/E0/E0-single-worker-steady-r03
python collect.py --run-dir "$RUN_DIR"
```

4. Trong terminal khác, chạy một mức tải, dùng file summary riêng cho từng lượt. Ví dụ 8 request/s trong 2 phút:

```bash
RUN_DIR=../results/E0/E0-single-worker-steady-r03
k6 run -e RATE=8 -e DURATION=2m -e WORK_UNITS=100 -e DB_MODE=light -e BATCH_SIZE=1 \
  --summary-export "$RUN_DIR/raw/k6-summary.json" ./workload.js
```

Người chạy xác nhận E0 dùng `WORK_UNITS=100`; metadata cũ không lưu giá trị này. Tốc độ là request/s; kiểm tra job được chấp nhận và dropped iterations. Mốc UTC in ra console và có trong summary dưới dạng Unix milliseconds.

5. Dừng gửi, tiếp tục thu đến khi visible/in-flight/delayed đều 0 qua nhiều mẫu và đối chiếu kết quả, sau đó Ctrl+C **một lần** ở collector và chờ xuất xong. Mở `collection-summary.md`, `collection.json`, `raw/k6-summary.json`, `metrics/` và log; trạng thái `finished` chỉ cho biết thu xong, không chứng minh lượt hợp lệ. Lặp ở mức tải khác bằng hồ sơ mới, chờ drain trước từng lượt. Giữ nguyên files gốc; không ghi đè kết quả.

Collector E0 xuất counter published/success, CPU, desired/ready, trạng thái node và mẫu SQS cùng log worker để xác định μ; không thu histogram latency không cần cho mục đích E0. Xác nhận image, tài nguyên, concurrency và DB mode giống nhau giữa các lượt.

## Kết quả

Nguồn: `E0-single-worker-steady-r02` ngày 05/11/2026 cho mức 5 request/s; `E0-single-worker-steady-r01/E0-single-worker-steady-r01` ngày 04/11/2026 cho các mức 8–15 request/s. Run ID trong bảng là nhãn sắp theo tải, không phải tên thư mục: **r02–r09 là tám pha của cùng một phiên thu**, không phải tám lượt độc lập. Mỗi pha 8–15 phát tải khoảng 2 phút, sau đó nghỉ khoảng 1 phút trước pha tiếp theo.

**Điều kiện ghi nhận:** một `orders-worker` Ready, không có HPA/ScaledObject điều khiển worker; CPU request 128m, memory request/limit 256Mi; concurrency 1, SQS max messages 1, DB mode `light`. Số worker desired/ready giữ ở 1 và hai node không thay đổi trong cửa sổ thu. `workUnits=100` theo xác nhận của người chạy; metadata gốc không lưu giá trị này.

| Run ID | Tải đặt (request/s) | Published trung bình (task/s) | Thành công trung bình (task/s) | Peak visible trong pha | CPU trung bình | Lỗi / retry / DLQ |
|---|---:|---:|---:|---:|---:|---|
| r01 | 5 | 5,00 | 5,00 | 0 | 511m | Không thấy / N/A / 0* |
| r02 | 8 | 8,00 | 7,99 | 4 | 915m | Không thấy / N/A / 0* |
| r03 | 9 | 9,00 | 8,86 | 23 | 962m | Không thấy / N/A / 0* |
| r04 | 10 | 10,00 | 8,88 | 137 | 865m | Không thấy / N/A / 0* |
| r05 | 11 | 11,00 | 8,87 | 226 | 1.031m | Không thấy / N/A / 0* |
| r06 | 12 | 12,00 | 8,89 | 331 | 982m | Không thấy / N/A / 0* |
| r07 | 13 | 13,00 | 8,88 | 397 | 980m | Không thấy / N/A / 0* |
| r08 | 14 | 14,00 | 8,86 | 583 | 1.036m | Không thấy / N/A / 0* |
| r09 | 15 | 15,00 | 8,90 | 737 | 1.086m | Không thấy / N/A / 0* |

**Cách tính:** nhận diện từng pha bằng khoảng `enqueuedAt` trong log job; lấy một cửa sổ 90 giây bên trong pha, bắt đầu từ mẫu Prometheus đầu tiên sau ít nhất 20 giây tính từ job đầu pha. Published và thành công bằng chênh lệch counter chia cho 90 giây; đây là throughput **trong cửa sổ đang phát tải**, không tính toàn bộ đoạn nghỉ/drain. CPU trung bình được tính từ chênh lệch `container_cpu_usage_seconds_total` trong cùng cửa sổ; 1.000m tương đương một lõi CPU. Peak visible là mẫu SQS `ApproximateNumberOfMessages` lớn nhất trong khoảng từ job đầu đến job cuối pha, không cộng in-flight. SQS là số gần đúng và các mẫu không đồng bộ; peak thực tế có thể cao hơn.

Cửa sổ UTC của r01 là 03:40:20–03:41:50 ngày 05/11/2026. Các cửa sổ r02–r09 lần lượt là 07:36:14–07:37:44, 07:39:19–07:40:49, 07:42:19–07:43:49, 07:45:19–07:46:49, 07:48:19–07:49:49, 07:51:19–07:52:49, 07:54:19–07:55:49 và 07:57:19–07:58:49 ngày 04/11/2026.

Trong cột lỗi, “không thấy” nghĩa là không quan sát lỗi worker trong log đã thu, không chứng minh mọi loại lỗi bằng 0. Retry là `N/A` vì không có dữ liệu đủ để đếm. DLQ `0*` nghĩa là các mẫu DLQ quan sát được đều bằng 0, không chứng minh không có message giữa các mẫu. Summary k6 của mức 5 và 15 request/s đều ghi 0 request lỗi; không có summary riêng để xác định lỗi request của các mức 8–14.

Trong phiên thu 8–15 request/s, counter published và success đều tăng 11.033; log thu được có 11.033 job ID khác nhau với status `success`. Summary k6 còn lưu chỉ thuộc pha cuối: 1.799 job được chấp nhận, không có check lỗi. Với lượt 5 request/s, k6 ghi nhận 599 job được chấp nhận và log có 599 job ID thành công trong thời gian workload; thêm 40 job xuất hiện trước khi k6 bắt đầu và không được tính vào cửa sổ r01.

**Chốt μ dùng cho pilot: khoảng 8,9 task/s/worker.** Từ tải 9 đến 15 request/s, throughput thành công trong cửa sổ đo dao động 8,86–8,90 task/s trong khi backlog tăng: đây là bằng chứng về vùng bão hòa. Giá trị này là **ước lượng sơ bộ của một phiên**, chưa phải trung vị của ba lượt xác nhận độc lập. Các pha tải cao còn chịu ảnh hưởng backlog từ pha trước: cuối thời gian nghỉ sau pha 13 và 14, mẫu visible vẫn lần lượt khoảng 76 và 339. Khi cần độ tin cậy cao hơn, lặp các lượt độc lập ở vùng bão hòa và chờ drain giữa lượt.

## Workload modeling cho E1

Với μ ≈ 8,9 task/s, đề xuất bộ tải **pilot** sau; cùng profile và thông số được dùng cho Fixed, CPU-HPA và KEDA. Chọn `batchSize=1` và kiểm tra job thực tế được chấp nhận để đối chiếu request/s với task/s. Đây là thiết kế mới dựa trên E0, không phải kết quả đã đo của E1.

| Profile | Các pha phát tải đề xuất | Mục đích |
|---|---|---|
| Steady | 5 request/s trong 2 phút | Tham chiếu tải ổn định, khoảng 0,56μ. |
| Step | 5 request/s trong 1 phút → 27 request/s trong 2 phút → 5 request/s trong 1 phút | Tải cao khoảng 3,03μ; quan sát scale và xử lý backlog khi tải duy trì. |
| Burst | 5 request/s trong 1 phút → 27 request/s trong 30 giây → 5 request/s trong 1 phút | Quan sát phản ứng với tải cao ngắn hạn và quá trình phục hồi. |

Sau mỗi profile, dừng gửi và tiếp tục đo đến khi queue drain theo tiêu chí đã chốt. Tải 27 task/s tương ứng khoảng `ceil(27 / 8,9) = 4` worker nếu năng lực scale tuyến tính; hai worker Fixed ước tính xử lý 17,8 task/s. Đây chỉ là dự báo ban đầu, không phải số replica do HPA/KEDA bảo đảm. Cần pilot để xác nhận workload đủ phân biệt các phương án, và chốt lại trước các lượt chính thức. Truyền `LOW_RATE=5` và `HIGH_RATE=27` khi chạy [workload.js E1](../E1/workload.js); mặc định của script vẫn là 1/5 request/s để tương thích các kịch bản khác.
