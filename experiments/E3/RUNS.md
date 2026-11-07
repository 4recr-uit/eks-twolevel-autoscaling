# Lịch chạy E3 — đã hoàn thành 12/12 lượt

Phạm vi đã chọn: hai lượt mỗi nhánh HPA/KEDA cho từng profile, theo thứ tự Step → Burst → Steady. Bốn lượt mỗi profile, tổng 12 lượt; không chạy r03 trong đợt này.

| Thứ tự | Run ID | Trạng thái |
|---:|---|---|
| 1 | [E3-hpa-step-r01](../results/E3/E3-hpa-step-r01/report.md) | Thu xong, đã đánh giá giới hạn |
| 2 | [E3-keda-step-r01](../results/E3/E3-keda-step-r01/report.md) | Thu xong, đã đánh giá giới hạn |
| 3 | [E3-keda-step-r02](../results/E3/E3-keda-step-r02/report.md) | Thu xong, đã đánh giá giới hạn |
| 4 | [E3-hpa-step-r02](../results/E3/E3-hpa-step-r02/report.md) | Thu xong, đã đánh giá giới hạn |
| 5 | [E3-hpa-burst-r01](../results/E3/E3-hpa-burst-r01/report.md) | Thu xong, đã đánh giá giới hạn |
| 6 | [E3-keda-burst-r01](../results/E3/E3-keda-burst-r01/report.md) | Thu xong, đã đánh giá giới hạn |
| 7 | [E3-keda-burst-r02](../results/E3/E3-keda-burst-r02/report.md) | Thu xong, đã đánh giá giới hạn |
| 8 | [E3-hpa-burst-r02](../results/E3/E3-hpa-burst-r02/report.md) | Thu xong, đã đánh giá giới hạn |
| 9 | [E3-hpa-steady-r01](../results/E3/E3-hpa-steady-r01/report.md) | Thu xong, đã đánh giá giới hạn |
| 10 | [E3-keda-steady-r01](../results/E3/E3-keda-steady-r01/report.md) | Thu xong, đã đánh giá giới hạn |
| 11 | [E3-keda-steady-r02](../results/E3/E3-keda-steady-r02/report.md) | Thu xong, đã đánh giá giới hạn |
| 12 | [E3-hpa-steady-r02](../results/E3/E3-hpa-steady-r02/report.md) | Thu xong, đã đánh giá giới hạn |

Mỗi lượt bắt đầu một worker desired/Ready và đúng một node E3 Ready (ip-10-0-11-127.ec2.internal); capacity thêm được thu hồi ngoài cửa sổ đo. Giữ cùng digest, batch=1, work_units=100, DB_MODE=light, max VU=50, worker request CPU=500m, memory=256Mi, concurrency=1 và SQS_MAX_MESSAGES=1. HPA CPU target=60%; KEDA queueLength=10; min=1/max=10.

| Profile | Workload | Thời gian phát tải |
|---|---|---:|
| Step v4 | 5→10→15→20→15→10→5 request/s, một phút mỗi bậc | 420 giây |
| Burst v3 | 5/s một phút → 40/s trong 30 giây → 5/s một phút | 150 giây |
| Steady v3 | 5 request/s cố định | 120 giây |

Cửa sổ báo cáo trước/sau tải đều 60 giây. Collector tự chạy chờ baseline 75 giây và tiếp tục đến khi có đủ tail, ba mẫu SQS rỗng liên tiếp và DLQ rỗng. Các lượt thủ công được đối chiếu dữ liệu thực tế: baseline HPA Step r02 khoảng 69,8 giây, đủ cửa sổ 60 giây nhưng lệch hướng dẫn 75 giây. Drain KEDA Step r02 khoảng 90,7 giây vượt tail, đã ghi giới hạn percentile.

Báo cáo dùng trung vị và min–max với n=2 mỗi nhánh; chưa đủ khẳng định ý nghĩa thống kê. Không sửa raw/report để ép số accepted/counter khớp. Xem [FINAL-REPORT.md](FINAL-REPORT.md) và [CLEANUP.md](CLEANUP.md) cho kết quả và trạng thái khôi phục.
