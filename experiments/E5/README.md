# E5 — Worker disruption và recovery

## Mục tiêu

Đánh giá khả năng phục hồi khi một worker Pod hoặc node bị gián đoạn trong lúc queue có backlog.

## Thiết kế

So sánh nhánh **baseline** với nhánh **fault** bị gián đoạn một Pod hoặc node; hai nhánh dùng cùng workload và cấu hình. KEDA có min 1/max 10 worker, queueLength 10. Công cụ đánh dấu và phân tích hiện hỗ trợ gián đoạn Pod; gián đoạn node chưa có công cụ riêng.

Các chỉ số chính gồm thời gian quan sát phục hồi, backlog, throughput và duplicate. Thời gian phục hồi phụ thuộc chu kỳ lấy mẫu; duplicate và tính toàn vẹn job cần đối soát job ID và trạng thái hoàn thành.

## Cấu hình và workload

- KEDA có polling 30 giây, cooldown 300 giây; worker yêu cầu 500m CPU và 256Mi memory, NodePool `e5-orders` dùng On-Demand.
- Các profile được hỗ trợ gồm Steady 5 request/s trong 2 phút, Step 5 → 10 → 15 → 20 → 15 → 10 → 5 request/s mỗi bậc 1 phút, và Burst 5 → 40 → 5 request/s với đỉnh 30 giây.
- Marker được ghi trước thời điểm gây lỗi; thời gian đến khi quan sát Pod cũ biến mất và Pod mới Ready có giới hạn theo chu kỳ lấy mẫu. Pod mới cũng có thể do scale-out, nên cần đối chiếu UID và sự kiện trước khi kết luận.

## Kết quả
