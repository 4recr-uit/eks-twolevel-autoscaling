# Kết quả E3 — hoàn thành 12/12 lượt

Đã hoàn thành hai lượt cho mỗi tổ hợp CPU-HPA/KEDA và Step/Burst/Steady ngày 2026-11-07. Thứ tự đo: Step → Burst → Steady; mỗi profile HPA r01 → KEDA r01 → KEDA r02 → HPA r02. Đánh giá hiệu năng: dùng được với các giới hạn lấy mẫu; chưa đối soát job ID.

- [Báo cáo tổng hợp và biểu đồ](FINAL-REPORT.md).
- Báo cáo riêng: [Step](STEP-REPORT.md), [Burst](BURST-REPORT.md), [Steady](STEADY-REPORT.md).
- [Lịch và giao thức đo](RUNS.md); [khôi phục sau đo](CLEANUP.md).

| Run ID | Accepted | p95 ≈ s | p99 ≈ s | Peak queue ≈ | Peak worker/node | Ready Pod-min | Node-min |
|---|---:|---:|---:|---:|---|---:|---:|
| [E3-hpa-step-r01](../results/E3/E3-hpa-step-r01/report.md) | 4799 | 0.243 | 0.249 | 3 | 8/3 | 43.60 | 18.60 |
| [E3-keda-step-r01](../results/E3/E3-keda-step-r01/report.md) | 4799 | 0.249 | 2.709 | 27 | 3/1 | 17.00 | 9.00 |
| [E3-keda-step-r02](../results/E3/E3-keda-step-r02/report.md) | 4799 | 1.668 | 6.661 | 49 | 5/2 | 27.00 | 14.85 |
| [E3-hpa-step-r02](../results/E3/E3-hpa-step-r02/report.md) | 4799 | 0.243 | 0.249 | 3 | 8/3 | 42.41 | 18.75 |
| [E3-hpa-burst-r01](../results/E3/E3-hpa-burst-r01/report.md) | 1799 | 29.385 | 50.990 | 632 | 6/2 | 10.99 | 6.09 |
| [E3-keda-burst-r01](../results/E3/E3-keda-burst-r01/report.md) | 1799 | 28.702 | 29.781 | 698 | 10/4 | 14.55 | 9.07 |
| [E3-keda-burst-r02](../results/E3/E3-keda-burst-r02/report.md) | 1799 | 55.359 | 59.072 | 931 | 10/4 | 13.90 | 8.34 |
| [E3-hpa-burst-r02](../results/E3/E3-hpa-burst-r02/report.md) | 1800 | 28.919 | 45.291 | 608 | 6/2 | 10.50 | 6.02 |
| [E3-hpa-steady-r01](../results/E3/E3-hpa-steady-r01/report.md) | 600 | 0.243 | 0.249 | 1 | 2/1 | 5.27 | 4.00 |
| [E3-keda-steady-r01](../results/E3/E3-keda-steady-r01/report.md) | 599 | 0.243 | 0.249 | 1 | 1/1 | 3.00 | 4.00 |
| [E3-keda-steady-r02](../results/E3/E3-keda-steady-r02/report.md) | 599 | 0.243 | 0.249 | 1 | 1/1 | 3.00 | 4.00 |
| [E3-hpa-steady-r02](../results/E3/E3-hpa-steady-r02/report.md) | 599 | 0.242 | 0.248 | 1 | 2/1 | 5.35 | 4.00 |

Mỗi lượt có report.json, report.md, notes.md, audit.json và dữ liệu raw. Các bảng so sánh đầy đủ: [Step](../results/E3/comparison-step-complete.md), [Burst](../results/E3/comparison-burst-complete.md), [Steady](../results/E3/comparison-steady-complete.md).

Peak queue là visible + in-flight gần đúng; Node-minutes là node Kubernetes hiện diện trong cửa sổ trước/sau tải 60 giây, không phải EC2 billing. Ready Pod-minutes/latency/CPU dùng từ bắt đầu tải đến sau tải 60 giây; throughput chỉ trong tải. Percentile có nội suy histogram và giới hạn counter; không chứng minh phân phối toàn bộ job. HPA Step r02 có baseline khoảng 69,8 giây; drain KEDA Step r02 khoảng 90,7 giây vượt tail báo cáo 60 giây. Chênh counter chưa đối soát và các sai khác giao thức được giữ rõ trong báo cáo tổng hợp.
