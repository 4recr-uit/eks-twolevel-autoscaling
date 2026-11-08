# E3 — Lượt bổ sung Step/Burst r03–r04

Đã hoàn thành và audit 8/8 lượt bổ sung. Giữ nguyên cấu hình E3 gốc; không phải các lượt tuning.

| Run | Accepted | p95 ≈ s | p99 ≈ s | Peak queue ≈ | Worker/node peak | Pod-min | Node-min |
|---|---:|---:|---:|---:|---|---:|---:|
| [E3-hpa-step-r03](../results/E3/E3-hpa-step-r03/report.md) | 4799 | 0.243 | 0.249 | 3 | 7/3 | 40.05 | 18.88 |
| [E3-hpa-step-r04](../results/E3/E3-hpa-step-r04/report.md) | 4799 | 0.243 | 0.249 | 3 | 8/3 | 43.52 | 18.88 |
| [E3-keda-step-r03](../results/E3/E3-keda-step-r03/report.md) | 4799 | 2.392 | 5.064 | 68 | 4/2 | 22.01 | 12.81 |
| [E3-keda-step-r04](../results/E3/E3-keda-step-r04/report.md) | 4799 | 0.248 | 1.946 | 20 | 3/1 | 18.00 | 9.00 |
| [E3-hpa-burst-r03](../results/E3/E3-hpa-burst-r03/report.md) | 1799 | 28.617 | 34.245 | 561 | 6/2 | 10.73 | 6.05 |
| [E3-hpa-burst-r04](../results/E3/E3-hpa-burst-r04/report.md) | 1799 | 28.309 | 29.662 | 655 | 6/2 | 10.94 | 6.02 |
| [E3-keda-burst-r03](../results/E3/E3-keda-burst-r03/report.md) | 1799 | 57.002 | 59.400 | 924 | 10/4 | 9.53 | 7.70 |
| [E3-keda-burst-r04](../results/E3/E3-keda-burst-r04/report.md) | 1799 | 46.678 | 57.336 | 829 | 10/4 | 13.89 | 8.57 |

Node đầu của đợt bổ sung khác ngày 07/11 do node cũ đã thu hồi. Giữ cùng loại/AZ/AMI/cấu hình; các lượt cũ và mới cần được đọc theo hai đợt, không coi là kiểm soát hoàn toàn cache/ngày/tải nền.
