# Hợp đồng tích hợp backend và hạ tầng

## 1. Luồng xử lý

Client → API → SQS → Worker → Database

- API gửi message trực tiếp vào queue của service.
- Worker đọc và xử lý message từ queue tương ứng.
- KEDA theo dõi SQS để scale worker.
- Karpenter tạo thêm node khi Pod thiếu tài nguyên.

## 2. Mapping service

Namespace ứng dụng: `retailstore`.

| Service | Queue | API ServiceAccount | Worker ServiceAccount | Worker Deployment dự kiến | Database |
|---|---|---|---|---|---|
| Cart | cart-queue | cart-api | cart-worker | cart-worker | PostgreSQL: retaildb, schema cart |
| Orders | orders-queue | orders-api | orders-worker | orders-worker | PostgreSQL: retaildb, schema orders |
| Checkout | checkout-queue | checkout-api | checkout-worker | checkout-worker | PostgreSQL: retaildb, schema checkout |
| Catalog | Không có | Theo chart | Không có | Không có | MySQL: catalogdb |
| Recommendations | Không có | Theo chart | Không có | Không có | MySQL: catalogdb hoặc in-memory |

## 3. Quyền AWS

- API chỉ được gửi message vào queue của chính service.
- Worker chỉ được nhận, xóa và thay đổi visibility message trong queue của chính service.
- KEDA có quyền đọc thông tin queue để tính số replica.
- ServiceAccount được liên kết với IAM role bằng EKS Pod Identity.

## 4. Phân chia trách nhiệm

| Thành phần | Nơi quản lý |
|---|---|
| Source code và Helm template ứng dụng | Repo backend |
| VPC, EKS, RDS, SQS, ECR, IAM | Terraform trong repo hạ tầng |
| ServiceAccount của Cart, Orders, Checkout | Repo hạ tầng |
| KEDA ScaledObject cho worker | Terraform trong repo hạ tầng |
| Values cụ thể cho môi trường EKS | Repo hạ tầng |
| Mật khẩu và credentials thực tế | Secret theo cơ chế được chọn; không commit vào Git |

## 5. Giá trị cần lấy sau Terraform apply

| Giá trị | Nguồn |
|---|---|
| URL các queue | `terraform output sqs_queue_urls` |
| URL các ECR repository | `terraform output ecr_repository_urls` |
| PostgreSQL endpoint | `terraform output postgres_endpoint` |
| MySQL endpoint | `terraform output mysql_endpoint` |
| ARN master secret PostgreSQL | `terraform output postgres_master_secret_arn` |
| ARN master secret MySQL | `terraform output mysql_master_secret_arn` |

Không dùng trực tiếp master credentials trong Pod ứng dụng.
User ứng dụng và quyền database cần được chuẩn bị riêng.

## 6. Các điểm cần hoàn thiện

- Chart tổng hiện có thể render worker Cart là `carts-worker`,
  trong khi Terraform KEDA yêu cầu `cart-worker`; cần thống nhất.
- Tắt ScaledObject trong backend chart khi Terraform quản lý.
- Sửa chart để tham chiếu Kubernetes Secret có sẵn.
- Thay values mặc định bằng cấu hình EKS: image, queue URL,
  database endpoint, node selector và credentials.
- Kiểm tra quyền và kết nối trên AWS sau khi triển khai.