# Autoscaling hai tầng

## Vai trò

- **KEDA** theo dõi SQS và điều chỉnh số worker Cart, Orders và Checkout qua ScaledObject/HPA.
- **Karpenter** tạo node theo NodePool khi scheduler không thể đặt Pod do thiếu capacity; node có thể được thu hồi theo chính sách consolidation.

Helm release `worker-scaling` quản lý ScaledObject. Release `platform-config` quản lý NodePool, EC2NodeClass và authentication dùng chung.

## Cấu hình dev

| Thành phần | Cấu hình | Giá trị mặc định |
|---|---|---|
| KEDA | `kubernetes/environments/dev/autoscaling.yaml` | 0–10 worker, queueLength 10, polling 30 giây, cooldown 300 giây |
| Karpenter | `kubernetes/environments/dev/platform.yaml` | NodePool `default`, On-Demand, consolidation sau 1 phút |

Backend chart dùng `worker.externalAutoscaling=true` và `worker.scaledObject.enabled=false` khi release `worker-scaling` quản lý worker. Mỗi Deployment chỉ có một cơ chế autoscaling; khi thử CPU-HPA riêng cần xử lý ScaledObject tương ứng trước.

Thay đổi values Helm cần được render và kiểm tra trước khi triển khai. AMI hoặc NodeClass mới có thể kích hoạt thay node; đánh giá disruption và PodDisruptionBudget trước khi thay đổi.
