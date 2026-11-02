# Autoscaling hai tầng

KEDA theo dõi ba SQS queue và quản lý worker `carts-worker`, `orders-worker`, `checkout-worker`. Khi scheduler không thể đặt Pod do thiếu capacity, Karpenter tạo node theo NodePool default.

Chính sách Karpenter nằm trong `kubernetes/environments/dev/platform.yaml`; ngưỡng KEDA nằm trong `autoscaling.yaml`. Baseline: 0–10 replicas, backlog 10/replica, polling 30s, cooldown 300s. Helm release platform-config quản lý NodePool/EC2NodeClass/auth; worker-scaling quản lý ScaledObjects.

Sau khi sửa YAML, render/review bằng Helm rồi chạy lại script tương ứng; không cần Terraform apply. AMI phải có version cụ thể và tương thích cluster. Đổi AMI hoặc NodeClass có thể kích hoạt thay node: review disruption/PodDisruptionBudget và rollout như thay đổi vận hành riêng.

Backend chart phải đặt `worker.externalAutoscaling=true`, `worker.scaledObject.enabled=false`. Mỗi worker chỉ có một cơ chế autoscaling. Để thí nghiệm HPA CPU, gỡ ScaledObject tương ứng theo kế hoạch trước khi tạo HPA riêng; không để hai HPA điều khiển cùng Deployment.

Các lệnh quan sát: `kubectl get scaledobjects,hpa -n retailstore`, `kubectl get nodepool,ec2nodeclass,nodeclaims`, `kubectl get pods -n retailstore -o wide`. Dùng đúng kubeconfig/context như DEPLOYMENT.md.
