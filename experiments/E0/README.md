# E0 — Hiệu chuẩn worker và xây dựng workload

## Mục tiêu

Ước lượng năng lực xử lý của một worker và xây dựng workload Steady, Step, Burst cho các thí nghiệm tiếp theo.

## Kết quả

Thí nghiệm dùng một `orders-worker`, không bật autoscaler, với concurrency 1, `workUnits=100` và `dbMode=light`. Worker có CPU request 128m, memory request/limit 256Mi và SQS max messages 1.

| Pha | Tải đặt (request/s) | Published trung bình (task/s) | Thành công trung bình (task/s) | Peak visible trong pha | CPU trung bình | p95 hoàn thành job (s) |
|---|---:|---:|---:|---:|---:|---:|
| r01 | 5 | 5,00 | 5,00 | 0 | 511m | 0,129 |
| r02 | 8 | 8,00 | 7,99 | 4 | 915m | 0,265 |
| r03 | 9 | 9,00 | 8,86 | 23 | 962m | 7,211 |
| r04 | 10 | 10,00 | 8,88 | 137 | 865m | 20,717 |
| r05 | 11 | 11,00 | 8,87 | 226 | 1.031m | 27,014 |
| r06 | 12 | 12,00 | 8,89 | 331 | 982m | 33,716 |
| r07 | 13 | 13,00 | 8,88 | 397 | 980m | 35,742 |
| r08 | 14 | 14,00 | 8,86 | 583 | 1.036m | 42,569 |
| r09 | 15 | 15,00 | 8,90 | 737 | 1.086m | 58,105 |

Từ mức tải 9–15 request/s, throughput duy trì khoảng **8,9 task/s** trong khi backlog tăng. Đây là dấu hiệu worker đạt vùng bão hòa. Giá trị **μ ≈ 8,9 task/s/worker** được dùng làm mốc thiết kế tải ban đầu. Throughput và CPU được tính trong cửa sổ 90 giây khi đang phát tải; peak visible là giá trị SQS gần đúng, còn p95 được tính từ log các job hoàn thành trong cùng cửa sổ.

## Workload

| Profile | Lịch phát tải | Ý nghĩa |
|---|---|---|
| [Steady](stead.js) | 5 request/s trong 2 phút | Quan sát hệ thống ở mức tải ổn định, thấp hơn μ. |
| [Step](step.js) | 5 → 10 → 15 → 20 → 15 → 10 → 5 request/s; mỗi bậc 1 phút | Quan sát phản ứng khi tải tăng và giảm dần. |
| [Burst](burst.js) | 5 request/s trong 1 phút → 40 request/s trong 30 giây → 5 request/s trong 1 phút | Quan sát phản ứng và phục hồi sau một đợt tăng tải đột ngột. |

Các mức tải là workload tổng hợp dùng cho pilot; năng lực nhiều worker không nhất thiết tăng tuyến tính theo μ.
