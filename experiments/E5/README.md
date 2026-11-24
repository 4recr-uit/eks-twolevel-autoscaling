# E5 — Worker disruption và recovery

## Mục tiêu

Đánh giá khả năng phục hồi khi một worker Pod hoặc node bị gián đoạn trong lúc queue có backlog.

## Thiết kế

So sánh nhánh **baseline** với nhánh **fault** bị gián đoạn một Pod hoặc node; hai nhánh dùng cùng workload và cấu hình. KEDA có min 0/max 20 worker, queueLength 10. Công cụ đánh dấu và phân tích hiện hỗ trợ gián đoạn Pod; gián đoạn node chưa có công cụ riêng.

Các chỉ số chính gồm thời gian quan sát phục hồi, backlog, throughput và duplicate. Thời gian phục hồi phụ thuộc chu kỳ lấy mẫu; duplicate và tính toàn vẹn job cần đối soát job ID và trạng thái hoàn thành.

Mỗi lượt bắt đầu với 0 worker và queue rỗng; xác minh Prometheus thu được metric worker sau khi workload kích hoạt Pod.

Có thể dùng cấu hình Orders mặc định với ScaledObject `orders-worker-sqs` của release `worker-scaling` cho cả baseline và fault. Bộ thu nhận diện autoscaler đang điều khiển Deployment; ở cấu hình mặc định, Node-phút tính tất cả node của pool `default`, có thể bao gồm capacity dùng chung. Ghi số node Ready, loại instance và cách giữ node ban đầu để tái lập cùng điều kiện ở lượt sau.

## Cấu hình và workload

- KEDA có polling 10 giây, cooldown 120 giây; worker yêu cầu 500m CPU và 256Mi memory, NodePool `e5-orders` dùng On-Demand.
- Các profile được hỗ trợ gồm Steady 5 request/s trong 2 phút, Step 5 → 10 → 15 → 20 → 15 → 10 → 5 request/s mỗi bậc 1 phút, và Burst 5 → 40 → 5 request/s với đỉnh 30 giây.
- Để lưu ID job API chấp nhận, chạy k6 với `-e LOG_JOB_IDS=1` và `--log-output file=ĐƯỜNG_DẪN_LOG`. Đối chiếu các ID này với bản ghi hoàn thành của worker trước khi Pod bị thu hồi.
- Marker được ghi trước thời điểm gây lỗi; thời gian đến khi quan sát Pod cũ biến mất và Pod mới Ready có giới hạn theo chu kỳ lấy mẫu. Pod mới cũng có thể do scale-out, nên cần đối chiếu UID và sự kiện trước khi kết luận.

Để giữ warm capacity khi cần, sau khi các Pod giữ chỗ Ready hãy gắn `karpenter.sh/do-not-disrupt=true` cho từng node cần giữ trước khi xóa Deployment giữ chỗ; gỡ annotation sau lượt. Ghi số node và capacity thực tế vì loại instance có thể khác nhau.

## Kết quả

Baseline `r01` và fault `r01` dùng cùng cấu hình Orders mặc định và cùng tải Burst 5 → 40 → 5 request/s. Hai lượt bắt đầu với queue rỗng, 0 worker, cùng một node Karpenter `t3.small` Ready và hai node hệ thống. Audit log của EKS xác nhận hai worker Pod bị xóa lần lượt ở T+71,56 và T+87,55 giây, trong pha tải đỉnh T+60 đến T+90.

| Chỉ số | Baseline | Fault |
|---|---:|---:|
| Job có đúng một bản ghi thành công / job được chấp nhận | 1.799/1.799 | 1.800/1.800 |
| Worker đầu tiên chuyển Ready, tính từ đầu tải | 33,4 s | 24,8 s |
| p95 E2E toàn lượt theo job ID | 15,618 s | 12,298 s |
| p95 thời gian chờ queue | 15,511 s | 12,191 s |
| p95 thời gian worker xử lý | 118 ms | 117 ms |
| Peak backlog quan sát qua SQS (visible + in-flight) | 132 | 88 |
| Thời gian xác nhận queue drain sau khi dừng tải | 47,3 s | 38,1 s |

Từ lần xóa đầu đến hết burst, throughput đạt 39,97 job/s ở baseline và 39,92 job/s ở fault, tính theo thời điểm hoàn thành. Với các job vào queue trong cùng cửa sổ, p95 E2E tương ứng là 132 và 138 ms. Sau lần xóa thứ hai, số worker mong muốn giữ ở 9. Pod mới chuyển Ready sau khoảng 6 giây và bộ thu ghi nhận đủ 9/9 worker Ready sau 13,5 giây.

Chênh lệch p95 toàn lượt chủ yếu đến từ thời gian chờ queue ở đầu tải. Trong 90 job chậm nhất của mỗi lượt, 90 job ở baseline và 88 job ở fault đã vào queue trước pha burst. Với một lượt mỗi nhánh, cửa sổ từ T+71,56 đến T+90 cho thấy hệ thống vẫn duy trì gần 40 job/s khi hai worker lần lượt bị xóa. Dữ liệu chi tiết nằm trong `experiments/results/E5/E5-baseline-burst-r01/` và `experiments/results/E5/E5-fault-burst-r01/`.
