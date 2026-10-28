# Hướng dẫn triển khai Terraform

Thư mục này tạo VPC, EKS, ECR, ba hàng đợi SQS kèm DLQ, hai RDS Single-AZ (PostgreSQL và MySQL), IAM/Pod Identity và AWS Budget. Karpenter, KEDA và monitoring được bật ở các lượt triển khai sau. Các lệnh dưới đây chạy trong thư mục `terraform`; ví dụ dùng Region `us-east-1` và cluster `twolevel-autoscaling-dev`.

## 1. Chuẩn bị

- Cài Terraform **>= 1.10**, AWS CLI và `kubectl`; cấu hình AWS credentials có quyền tạo các tài nguyên trên. Kiểm tra tài khoản bằng `aws sts get-caller-identity`.
- S3 bucket `tfstate-bucket-2006` trong `us-east-1` phải tồn tại và tài khoản cần quyền đọc/ghi state. Nếu dùng bucket khác, sửa `backend.tf` trước khi chạy `terraform init`.
- Nếu chưa có, sao chép `terraform.tfvars.example` thành `terraform.tfvars`. Thay `eks_public_access_cidrs` bằng **IPv4 công khai hiện tại** của máy quản trị ở dạng `/32`; `203.0.113.10/32` chỉ là giá trị mẫu. Đặt `budget_alert_email` nếu muốn nhận cảnh báo chi phí ở ngưỡng 80%.
- Kiểm tra `monthly_budget_usd`, cấu hình RDS và hai biến `db_deletion_protection`, `db_create_final_snapshot`. Giá trị mẫu phù hợp môi trường đồ án có thể hủy; dữ liệu cần giữ phải được sao lưu trước khi xóa.

## 2. Triển khai

**Lượt 1 — hạ tầng nền:** giữ `enable_cluster_addons = false`, `enable_keda_scaled_objects = false` và `enable_observability = false` trong `terraform.tfvars`.

```bash
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan
terraform apply
aws eks update-kubeconfig --region us-east-1 --name twolevel-autoscaling-dev
kubectl get nodes
```

Chỉ tiếp tục khi cluster và seed node group đã sẵn sàng; với cấu hình mẫu, `kubectl get nodes` hiển thị hai node `Ready`. Nếu thay `project_name`, `environment` hoặc `aws_region`, dùng tên cluster/Region tương ứng trong lệnh `update-kubeconfig`.

**Lượt 2 — autoscaling:** đặt `enable_cluster_addons = true`, rồi chạy `terraform plan` và `terraform apply` lần nữa. Kiểm tra:

```bash
kubectl get pods -n karpenter
kubectl get ec2nodeclass,nodepool
kubectl get pods -n keda
kubectl get clustertriggerauthentication
```

Các Pod phải `Running`; `EC2NodeClass` và `NodePool` phải `Ready`. Karpenter chỉ tạo thêm EC2 node khi có Pod cần tài nguyên. Sau khi đã triển khai ba worker Deployment (`cart-worker`, `orders-worker`, `checkout-worker`) trong namespace `retailstore`, mới đặt `enable_keda_scaled_objects = true` và apply tiếp; kiểm tra bằng `kubectl get scaledobjects -n retailstore`.

Monitoring là tùy chọn: tạo trước Secret `grafana-admin` trong namespace `monitoring` với hai khóa `admin-user`, `admin-password`, sau đó đặt `enable_observability = true` và apply. Dashboard chỉ truy cập nội bộ qua `kubectl port-forward`.

## 3. Kiểm tra trên AWS Console

Đăng nhập [AWS Management Console](https://console.aws.amazon.com/), chọn **us-east-1** (hoặc Region đã cấu hình), rồi kiểm tra:

| Dịch vụ / đường dẫn | Kết quả mong đợi |
| --- | --- |
| **VPC → Your VPCs / Subnets / Route tables** | VPC `twolevel-autoscaling-dev-vpc`; 2 public, 2 private cho EKS và 2 database subnet. Route table database chỉ có route nội bộ VPC. |
| **EKS → Clusters → twolevel-autoscaling-dev** | Cluster `Active`; trong **Compute**, managed node group `Active`. Trong **Access → Pod Identity**, có các association cho publisher, worker và KEDA; sau lượt 2 có thêm Karpenter. |
| **RDS → Databases → twolevel-autoscaling-dev-postgres / twolevel-autoscaling-dev-mysql** | Hai DB `Available`, `Multi-AZ: No`, `Publicly accessible: No`. Trong **Connectivity & security**, DB dùng subnet group riêng; security group chỉ cho phép node SG truy cập cổng 5432 hoặc 3306 tương ứng. |
| **SQS → Queues** | Có `cart-queue`, `orders-queue`, `checkout-queue` và ba DLQ; mỗi queue chính có dead-letter queue và `maxReceiveCount = 3`. Sau lượt 2 có thêm queue xử lý gián đoạn của Karpenter. |
| **ECR → Private registry → Repositories** | Có 5 repository: `catalog`, `cart`, `orders`, `checkout`, `recommendations`. |
| **Billing and Cost Management → Budgets** | Budget `twolevel-autoscaling-dev-monthly-cost` theo mức trong `monthly_budget_usd`; email cảnh báo chỉ có nếu đã cấu hình `budget_alert_email`. |

Karpenter và KEDA được cài bằng Helm nên kiểm tra trạng thái chạy bằng `kubectl` như ở lượt 2, không tìm chúng trong danh sách **EKS Add-ons**. Để xem ID, endpoint và URL thực tế, chạy `terraform output`.

Khi kết thúc, sao lưu dữ liệu và kết quả đo cần giữ rồi chạy `terraform plan -destroy` trước `terraform destroy`. Kiểm tra lại trên Console các snapshot, EBS volume, load balancer và tài nguyên còn tính phí sau khi hủy.
