# Chuẩn bị môi trường

## Công cụ và source code

- Bash, Terraform ≥ 1.10, AWS CLI v2, kubectl, Helm và Python 3. Trên Windows có thể dùng Git Bash hoặc WSL.
- Đặt repo backend `retailstore-backend-microservices` cạnh repo hạ tầng. Các script triển khai dùng chart từ repo backend.
- Cấu hình AWS credentials và quyền truy cập S3 backend, Terraform và Kubernetes API. EKS API phải cho phép kết nối từ máy triển khai.

## Hạ tầng và ứng dụng

- Cấu hình Terraform backend, `terraform/terraform.tfvars`, account, region và chính sách giữ dữ liệu RDS. Kiểm tra kế hoạch chuyển quyền quản lý nếu add-on đã được Terraform quản lý.
- Tạo hạ tầng bằng Terraform; đối chiếu output với values trong `kubernetes/environments/dev/`. Chọn AMI alias có phiên bản cụ thể, tương thích với EKS.
- Build và push image cho năm ứng dụng. Values dev dùng tag `latest` và `imagePullPolicy: Always`; push lại cùng tag không tự khởi động lại Pod đang chạy.
- Chuẩn bị PostgreSQL `retaildb` với schema và user Cart, Orders, Checkout; MySQL `catalogdb` cho Catalog và Recommendations. Cấp quyền ứng dụng và migration phù hợp, không dùng master credentials cho Pod.
- Chuẩn bị Secret cho năm ứng dụng và Grafana, cùng RDS CA bundle. Values dev bật TLS; Cart, Orders và Checkout dùng `sslmode=verify-full`, các chart tham chiếu ConfigMap `rds-ca`.

Cấu hình dev dùng region `us-east-1`, cluster `twolevel-autoscaling-dev` và context `twolevel-dev`. Các script triển khai phải được điều chỉnh nếu dùng môi trường khác.
