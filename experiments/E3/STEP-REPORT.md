# E3 — So sánh CPU-HPA và KEDA, workload Step

## Phạm vi đã hoàn thành

Đã thu và đánh giá hai lượt HPA và hai lượt KEDA vào ngày 2026-11-07, đúng phạm vi
Step của đợt chạy. Giữ cả bốn lượt để so sánh hiệu năng có giới hạn. Đây là n=2 mỗi
nhánh, không khẳng định ý nghĩa thống kê hay một controller luôn tốt hơn.

Các lượt dùng Step v4 5→10→15→20→15→10→5 request/s, mỗi bậc một phút, batch 1,
work_units 100, DB_MODE light, max VU 50. Mỗi lượt bắt đầu một node E3 và một worker
Ready; cùng node gốc ip-10-0-11-127.ec2.internal, c7i-flex.large On-Demand,
us-east-1b. Worker request CPU 500m/memory 256Mi, memory limit 256Mi, concurrency
1, SQS_MAX_MESSAGES 1, cùng image digest. HPA dùng CPU target 60%; KEDA dùng SQS
queueLength 10, scaleOnInFlight=true; cả hai min 1/max 10 và cho Karpenter mở rộng.

Các trường profile/workload/configuration/cửa sổ được công cụ compare xác nhận
khớp. Cùng node không tự bảo đảm mọi yếu tố cache, tải nền và spare capacity/IP
đều giống nhau; Pod đầu HPA r02 đã được tạo lại sau lần chuyển controller.

## Kết quả từng lượt

| Nhánh/lượt | Accepted | Throughput ≈ task/s | p95 ≈ s | p99 ≈ s | Peak queue ≈ | Drain ≈ s | Peak worker | Node đầu→peak | Ready Pod-min | Node-min |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| HPA r01 | 4.799 | 11,20 | 0,243 | 0,249 | 3 | 19,6 | 8 | 1→3 | 43,60 | 18,60 |
| HPA r02 | 4.799 | 11,18 | 0,243 | 0,249 | 3 | 25,8 | 8 | 1→3 | 42,41 | 18,75 |
| KEDA r01 | 4.799 | 11,23 | 0,249 | 2,709 | 27 | 52,0 | 3 | 1→1 | 17,00 | 9,00 |
| KEDA r02 | 4.799 | 11,17 | 1,668 | 6,661 | 49 | 90,7 | 5 | 1→2 | 27,00 | 14,85 |

## Trung vị [min–max], hai lượt mỗi nhánh

| Chỉ số | HPA | KEDA |
|---|---:|---:|
| Throughput success ≈ task/s | 11,19 [11,18–11,20] | 11,20 [11,17–11,23] |
| p95 E2E ≈ s | 0,243 [0,243–0,243] | 0,959 [0,249–1,668] |
| p99 E2E ≈ s | 0,249 [0,249–0,249] | 4,685 [2,709–6,661] |
| Peak visible + in-flight ≈ | 3 [3–3] | 38 [27–49] |
| Xác nhận drain ≈ s | 22,70 [19,60–25,80] | 71,35 [52,00–90,70] |
| Ready Pod-minutes ≈ | 43,005 [42,41–43,60] | 22,00 [17,00–27,00] |
| Worker Node-minutes ≈ | 18,675 [18,60–18,75] | 11,925 [9,00–14,85] |

Trung vị p95 là trung vị hai giá trị p95 của các lượt, không phải p95 gộp toàn bộ
job. Điều tương tự áp dụng cho p99 và các chỉ số theo lượt. Histogram có nội suy;
hai kết quả bằng nhau sau làm tròn không chứng minh phân phối độ trễ giống nhau.

## Nhận xét trong cấu hình đã đo

HPA quan sát được queue peak và latency thấp hơn, nhưng tăng tới tám worker và
ba node ở cả hai lượt. KEDA dùng ba đến năm worker và một đến hai node, có queue
peak và tail latency cao hơn, biến thiên rõ giữa hai lượt. Throughput delta gần
nhau. So theo trung vị, KEDA dùng ít hơn khoảng 48,8% Ready Pod-minutes và 36,1%
Worker Node-minutes; đây là tài nguyên ước lượng trong cửa sổ, không phải tỷ lệ
tiết kiệm hóa đơn AWS. Không kết luận KEDA luôn chỉ dùng một node hoặc luôn ít tốn
tài nguyên hơn trên mọi workload.

## Độ tin cậy và giới hạn

- Bốn lượt đều có 4.799 check k6 đạt, failed request rate=0; không có mẫu DLQ khác 0, main/DLQ cuối lượt rỗng. Không ghi nhận worker restart hoặc đổi digest trong mẫu. Summary không có metric dropped_iterations.
- HPA r01/r02 và KEDA r02 có Pod thiếu CPU request, NodeClaim/node mới; cảnh báo Pending/node thay đổi có bằng chứng phù hợp thiết kế. KEDA r01 có Pending khởi động ngắn đã được xếp lịch, không có bằng chứng thiếu capacity.
- Success delta HPA r01/r02 là 4.726/4.738; mẫu đầu series mới cộng 73/61, bổ sung khớp accepted. KEDA r01/r02 là 4.741/4.707; mẫu đầu cộng 48/88, còn chênh 10/4 chưa đối soát. Chưa có kiểm chứng theo job ID, không kết luận không mất/trùng job.
- Giữ cửa sổ trước/sau tải 60 giây. Drain KEDA r02 90,7 giây nằm ngoài tail; percentile và nhiều chỉ số hiệu năng không mô tả toàn bộ thời gian đến drain. Số success đến drain tính riêng nhưng vẫn có giới hạn counter. Drain là xác nhận qua các mẫu SQS gần đúng, không phải thời điểm job cuối hoàn thành.
- Baseline HPA r02≈69,8 giây, thấp hơn hướng dẫn 75 giây nhưng đủ cửa sổ trước tải 60 giây của report; ghi nhận sai khác giao thức này.
- Node-minutes dựa trên node Kubernetes hiện diện, không phải EC2 billing. CPU delta có thể thiếu đầu/cuối series, không dùng để khẳng định hiệu quả CPU từ n=2.

## Nguồn dữ liệu

- [HPA r01](../results/E3/E3-hpa-step-r01/report.md), [HPA r02](../results/E3/E3-hpa-step-r02/report.md).
- [KEDA r01](../results/E3/E3-keda-step-r01/report.md), [KEDA r02](../results/E3/E3-keda-step-r02/report.md).
- [Bảng compare đủ bốn lượt](../results/E3/comparison-step-final.md).

Các link kết quả cần dữ liệu local trong experiments/results (được gitignore).
Phần Step đã hoàn thành phạm vi hai lượt/nhánh; Burst và Steady cũng đã hoàn thành theo
[lịch chạy](RUNS.md). Xem [báo cáo tổng hợp E3](FINAL-REPORT.md).

## Bổ sung kiểm tra drain toàn cửa sổ

HPA Step r01 có một mẫu SQS khác 0 sau mốc drain đầu 19,6 giây. Mốc trong bảng là lần đầu có ba mẫu rỗng, không phải bảo đảm queue rỗng mãi sau đó. Xem audit và bảng chuỗi rỗng cuối trong [FINAL-REPORT.md](FINAL-REPORT.md).
