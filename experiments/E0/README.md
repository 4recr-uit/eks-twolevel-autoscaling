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

Với μ sơ bộ ≈ 8,9 task/s/worker, bộ tải sau dùng cho **pilot E1**. Giữ cùng profile và thông số giữa Fixed, CPU-HPA và KEDA; `batchSize=1`, `workUnits=100`, `dbMode=light` theo E0. Rate là request/s đặt cho k6; đối chiếu accepted jobs để biết task thực tế. `dbMode=light` ghi dữ liệu thử vào database.

| Profile | Lịch phát tải | Tổng thời gian / request dự kiến | Script |
|---|---|---|---|
| Steady | 5/s trong 2 phút | 2 phút / 600 | [stead.js](../E1/stead.js) |
| Step | 5 → 10 → 15 → 20 → 15 → 10 → 5/s, mỗi bậc 2 phút | 14 phút / 9.600 | [step.js](../E1/step.js) |
| Burst | 5/s trong 1 phút → **40/s** trong 30 giây → 5/s trong 1 phút | 2 phút 30 giây / 1.800 | [burst.js](../E1/burst.js) |

Steady và Step cố định lịch trong file, không truyền `LOW_RATE`, `HIGH_RATE` hay `PROFILE`. Step chuyển bậc tức thời và giữ mỗi mức cố định; đây là staircase, không phải ramp tuyến tính. Burst cố định baseline và thời lượng; mức đỉnh **tạm chốt cho pilot là 40/s**, nhưng script vẫn yêu cầu truyền `HIGH_RATE` là số nguyên lớn hơn 5. Từ thư mục E1: `k6 run -e HIGH_RATE=40 ./burst.js`. Ghi mức đỉnh thực tế trong mỗi lượt.

Với μ hiện có, các mức Step tương ứng khoảng 0,56; 1,12; 1,69; 2,25 μ. Nếu hai worker Fixed có capacity tuyến tính 17,8 task/s, bậc 20/s vượt khoảng 2,2 task/s, tương đương 264 task trong 2 phút. Đây là phép tính thăm dò, không phải dự đoán backlog: μ chưa được xác nhận bằng ba lượt độc lập, nhiều worker và database có thể không scale tuyến tính. Vì mức đỉnh chỉ cao hơn capacity ước tính một ít, cần pilot xác nhận nó đủ tạo khác biệt giữa các chiến lược.

### Cách đánh giá Step

Hai phút mỗi bậc là thời lượng được chọn, không bảo đảm trạng thái ổn định. Kiểm tra chu kỳ metrics, thời gian worker Ready, backlog và biến động replica; ghi rõ nếu bậc kết thúc trước khi ổn định. Bậc cuối 5/s kéo dài 2 phút, nên tiếp tục thu sau khi dừng tải để đo drain và scale-in. Giữ lịch và cửa sổ đo cố định giữa các nhánh.

- Các mức được chọn quanh capacity ước tính: 5/s là baseline, 10/s vượt μ một worker và 20/s cao hơn 2μ. Nếu có trace lưu lượng thật, đối chiếu phân phối và tốc độ thực tế; khi không có trace, ghi rõ đây là workload tổng hợp.
- Mỗi bậc đánh giá cả chuyển tiếp và cuối bậc: accepted rate, throughput thành công, backlog/queue age, E2E latency, desired/ready, CPU và lỗi. Với latency theo bậc, ưu tiên nhóm job theo thời điểm enqueue rồi theo dõi đến hoàn thành; ghi rõ nếu chỉ có histogram theo thời điểm hoàn thành, hoặc không đủ dữ liệu. Pha giảm có thể vẫn xử lý backlog tích lũy, nên không coi cùng rate tăng và giảm là cùng trạng thái; so sánh thêm queue đầu pha.
- Ghi riêng các mốc pha, chất lượng dữ liệu và actual rate theo thời gian. Tổng summary không chứng minh từng bậc đạt tải; phân vị toàn lượt không thay được latency từng bậc. Pilot để xác định VU đủ, producer/DB không trở thành nút thắt và workload thực sự phân biệt các nhánh; cân nhắc chi phí và số job tăng theo thời lượng.
- Giữ chung workload, cấu hình worker và cửa sổ phân tích; lặp ít nhất 3 lượt hợp lệ theo thứ tự xen kẽ giữa các chiến lược, đối chiếu job, retry và DLQ. Ghi rõ trạng thái đầu, đặc biệt HPA có thể scale ở 5/s. Nếu điều chỉnh lịch, cần sửa script, tăng version workload và cập nhật mốc đỉnh/so sánh trong `report.py` trước khi dùng.

### Đánh giá Burst pilot

Burst 40/s tương đương khoảng 4,49μ. Với capacity Fixed giả định 17,8 task/s, lượng việc vượt capacity trong pha đỉnh khoảng `(40 − 17,8) × 30 = 666` task; đây không phải peak backlog thực đo. Sau pha đỉnh trở về 5/s, rồi dừng và tiếp tục quan sát drain. Pilot cần xác nhận producer/DB chịu được tải, kiểm tra accepted rate, dropped iterations, lỗi và thời gian phục hồi; không suy ra hiệu quả autoscaler từ rate đặt. Giữ 40/s giữa các nhánh trong phép so sánh; nếu khảo sát mức hoặc thời lượng khác, ghi riêng và không gộp với lượt chính.

Tài liệu tham khảo: [k6 về thiết kế load profile](https://grafana.com/docs/learning-hub/k6-performance-testing/03-establishing-a-baseline/17-designing-load-profile/), [k6 về arrival-rate executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/), [Kubernetes HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/), [KEDA FAQ 2.21](https://keda.sh/docs/2.21/reference/faq/).
