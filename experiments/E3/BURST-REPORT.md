# E3 — So sánh HPA và KEDA, Burst hai lượt mỗi nhánh

Đã hoàn thành bốn lượt Burst theo kế hoạch ngày 2026-11-07. Mỗi lượt bắt đầu một
worker và một node E3 Ready; cùng node gốc, image và cấu hình ứng dụng. Burst v3:
5 request/s trong 60 giây → 40 trong 30 giây → 5 trong 60 giây; batch 1,
work_units 100, DB_MODE light, max VU 50. Node được phép mở rộng qua Karpenter.

## Kết quả từng lượt

| Lượt | Accepted | p95 ≈ s | p99 ≈ s | Peak queue ≈ | Peak worker/node | Ready Pod-min | Node-min |
|---|---:|---:|---:|---:|---|---:|---:|
| HPA r01 | 1.799 | 29,385 | 50,990 | 632 | 6/2 | 10,99 | 6,09 |
| HPA r02 | 1.800 | 28,919 | 45,291 | 608 | 6/2 | 10,50 | 6,02 |
| KEDA r01 | 1.799 | 28,702 | 29,781 | 698 | 10/4 | 14,55 | 9,07 |
| KEDA r02 | 1.799 | 55,359 | 59,072 | 931 | 10/4 | 13,90 | 8,34 |

Accepted thực tế được giữ nguyên, không sửa để ép mọi lượt cùng số job. Profile
phát tải theo thời gian và tham số giống nhau; HPA r02 nhận nhiều hơn các lượt
khác một request. Chưa đối soát job ID.

## Trung vị [min–max], n=2 mỗi nhánh

| Chỉ số | HPA | KEDA |
|---|---:|---:|
| Throughput success delta ≈ task/s | 11,520 [11,480–11,560] | 10,575 [10,560–10,590] |
| p95 E2E ≈ s | 29,152 [28,919–29,385] | 42,031 [28,702–55,359] |
| p99 E2E ≈ s | 48,141 [45,291–50,990] | 44,427 [29,781–59,072] |
| Peak visible + in-flight ≈ | 620 [608–632] | 814,5 [698–931] |
| Xác nhận drain ≈ s | 34,85 [27,70–42,00] | 24,70 [16,30–33,10] |
| Ready Pod-minutes ≈ | 10,745 [10,50–10,99] | 14,225 [13,90–14,55] |
| Worker Node-minutes ≈ | 6,055 [6,02–6,09] | 8,705 [8,34–9,07] |

Trong cấu hình đã đo, KEDA dùng nhiều worker/node hơn, có p95 biến thiên lớn hơn.
p99 và drain không cùng thứ tự với p95; không kết luận từ một chỉ số rằng một
controller tốt hơn toàn diện. Throughput delta có thể thấp do thiếu đầu/cuối
series, nhất là khi tạo nhiều Pod; không coi đây là throughput xử lý chính xác.
Hai lượt mỗi nhánh chưa đủ khẳng định khác biệt có ý nghĩa thống kê.

## Đối chiếu phản ứng bằng raw

Trong mẫu worker cuối trước khi bắt đầu đoạn 40/s (giây 60), cả hai lượt HPA đã có
2 desired/Ready worker, còn hai lượt KEDA vẫn 1 desired/Ready. Các mốc mẫu raw
đầu tiên có desired>1 sau khi bắt đầu workload lần lượt khoảng 33,4/53,0 giây ở
HPA và 83,7/94,2 giây ở KEDA. Mốc raw đầu có ready>1 khoảng 39,2/58,3 giây và
89,2/99,6 giây tương ứng. Đây là thời điểm quan sát, không phải thời điểm quyết
định chính xác; không gán toàn bộ khác biệt latency cho một nguyên nhân duy nhất.

Các mốc first_scale_out trong report lấy từ Prometheus có thể muộn hơn raw worker
do scrape/lấy mẫu. Query step 5 giây không làm metric gốc mới hơn; cần đối chiếu
Pod UID, scheduler event và NodeClaim trước khi kết luận về phản ứng controller.

## Giới hạn dữ liệu

- Bốn lượt không có lỗi request/check k6 hay mẫu DLQ khác 0; queue/DLQ cuối lượt rỗng, không ghi nhận worker restart hoặc đổi digest. Summary không có metric dropped_iterations.
- Có bằng chứng Pod thiếu CPU request và Karpenter tạo node mới. Pending/node thay đổi phù hợp thiết kế, không tự làm lượt vô hiệu.
- HPA r01 còn chênh counter 13 sau phép bổ sung đầu series. Các lượt tự chạy còn lại có ước lượng bổ sung khớp accepted; điều đó vẫn chưa thay đối soát job ID để chứng minh không mất/trùng job.
- Histogram cũng là counter theo Pod, có thể thiếu đầu/cuối series; percentile là ước lượng từ mẫu, không phải phân vị xác minh trên toàn bộ job. SQS gần đúng và mốc drain là xác nhận qua mẫu.
- Giữ cùng cửa sổ trước/sau tải 60 giây. Node-minutes không phải EC2 billing; không gồm toàn bộ thời gian chuẩn bị hoặc giữ node ngoài cửa sổ. Không so tổng Pod/Node-minutes Burst và Step như cùng workload.

Nguồn: [bảng compare Burst](../results/E3/comparison-burst-complete.md), raw
report/notes/audit của [HPA r01](../results/E3/E3-hpa-burst-r01/report.md),
[HPA r02](../results/E3/E3-hpa-burst-r02/report.md),
[KEDA r01](../results/E3/E3-keda-burst-r01/report.md),
[KEDA r02](../results/E3/E3-keda-burst-r02/report.md).
