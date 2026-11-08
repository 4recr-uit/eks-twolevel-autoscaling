# E3 — Trạng thái chiến dịch tự chạy

Đã có report 12/12 lượt; hai lượt mỗi nhánh/profile. Thứ tự Step → Burst → Steady.

| Run ID | Accepted | p95 ≈ s | p99 ≈ s | Peak queue ≈ | Peak worker/node | Pod-min | Node-min | Đánh giá |
|---|---:|---:|---:|---:|---|---:|---:|---|
| E3-hpa-step-r01 | 4799 | 0.243 | 0.249 | 3 | 8/3 | 43.6 | 18.6 | usable_with_limitations |
| E3-keda-step-r01 | 4799 | 0.249 | 2.709 | 27 | 3/1 | 17.0 | 9.0 | usable_with_limitations |
| E3-keda-step-r02 | 4799 | 1.668 | 6.661 | 49 | 5/2 | 27.0 | 14.85 | usable_with_limitations |
| E3-hpa-step-r02 | 4799 | 0.243 | 0.249 | 3 | 8/3 | 42.41 | 18.75 | usable_with_limitations |
| E3-hpa-burst-r01 | 1799 | 29.385 | 50.990 | 632 | 6/2 | 10.99 | 6.09 | usable_with_limitations |
| E3-keda-burst-r01 | 1799 | 28.702 | 29.781 | 698 | 10/4 | 14.55 | 9.07 | usable_with_limitations |
| E3-keda-burst-r02 | 1799 | 55.359 | 59.072 | 931 | 10/4 | 13.9 | 8.34 | usable_with_limitations |
| E3-hpa-burst-r02 | 1800 | 28.919 | 45.291 | 608 | 6/2 | 10.5 | 6.02 | usable_with_limitations |
| E3-hpa-steady-r01 | 600 | 0.243 | 0.249 | 1 | 2/1 | 5.27 | 4.0 | usable_with_limitations |
| E3-keda-steady-r01 | 599 | 0.243 | 0.249 | 1 | 1/1 | 3.0 | 4.0 | usable_with_limitations |
| E3-keda-steady-r02 | 599 | 0.243 | 0.249 | 1 | 1/1 | 3.0 | 4.0 | usable_with_limitations |
| E3-hpa-steady-r02 | 599 | 0.242 | 0.248 | 1 | 2/1 | 5.35 | 4.0 | usable_with_limitations |

Các chỉ số là ước lượng; đánh giá metric không thay đối soát job ID. Giữ report.json gốc và xem notes/report.md/audit.json từng lượt. n=2 không chứng minh khác biệt thống kê.
