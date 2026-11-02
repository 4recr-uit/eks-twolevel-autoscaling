# Chuẩn bị môi trường

- Bash, Terraform >=1.10, AWS CLI v2, kubectl tương thích EKS và Helm 3/4. Trên Windows dùng Git Bash hoặc WSL. Không chạy `.sh` trực tiếp như PowerShell; gọi `bash scripts/...`.
- Checkout repo backend cạnh repo này; nếu nằm chỗ khác, sửa đường dẫn chart trong `scripts/05-deploy-apps.sh`. Dùng các chart đã có hỗ trợ `worker.externalAutoscaling`.
- Chuẩn bị AWS credentials bằng profile/SSO hoặc role, quyền Terraform với S3 backend và quyền truy cập Kubernetes API. CIDR API EKS phải cho phép máy chạy script.
- Chuẩn bị `terraform/terraform.tfvars` theo mẫu, xác nhận account/region/budget và chính sách giữ dữ liệu RDS. `backend.tf` đang trỏ S3 bucket có sẵn; thay cấu hình nếu dùng môi trường khác.
- Chạy Terraform theo [hướng dẫn](../terraform/README.md); nếu từng cài add-ons bằng Terraform, làm [migration](MIGRATION.md) trước.
- Build/push image của cả năm backend vào ECR. Values hiện dùng `latest` và `pullPolicy: Always`; sau mỗi lần push cùng tag cần rollout restart các workload liên quan. `05-deploy-apps.sh` chỉ triển khai, không build image.
- Chọn bản AL2023 đã kiểm thử tương thích với phiên bản EKS, ghi alias `al2023@vYYYYMMDD`. Ví dụ trong test fixture chỉ dùng để render, không phải AMI đã được xác minh.
- Chuẩn bị database `retaildb` với schema/user của Cart, Orders, Checkout và `catalogdb` cho Catalog/Recommendations. Users trong values mẫu là `cart_app`, `orders_app`, `checkout_app`, `recommendations_app`; Catalog lấy user từ Secret. Cấp quyền runtime/migration phù hợp với backend, không dùng tài khoản master trong Pod.
- Tạo namespace ứng dụng và các Secret theo [INTEGRATION.md](INTEGRATION.md). Dùng công cụ secret/đầu vào được bảo vệ; không ghi mật khẩu vào values đã commit, shell history hoặc log. PostgreSQL mẫu dùng TLS `sslmode=require`; việc xác minh CA/hostname cần cấu hình driver và CA tương ứng nếu yêu cầu verify-full.
- Với MySQL, cấu hình TLS và trust bundle cho ảnh ứng dụng trước khi nghiệm thu: Catalog đọc `RETAIL_CATALOG_PERSISTENCE_TLS`, Go có thể đọc CA qua `SSL_CERT_FILE`; Recommendations đọc `RETAIL_RECOMMENDATIONS_PERSISTENCE_TLS` và `DB_SSL_CA`. Các biến có thể nằm trong Secret được `envFrom`; đường dẫn CA phải thực sự tồn tại trong image. Script không tự bổ sung CA bundle hoặc đổi policy RDS.
- Nếu bật monitoring, tạo namespace monitoring và Secret `grafana-admin` có key `admin-user`, `admin-password` trước bước deploy-monitoring. ClusterIP và port-forward là cách truy cập mặc định.

Luồng tường minh hiện dùng `kubernetes/environments/dev/` và context `twolevel-dev`. Nếu cần môi trường khác, sao chép YAML và sửa các path/cluster/context/version trong lệnh. Mỗi môi trường dùng Terraform backend/key riêng. Thông tin chi tiết: scripts/README.md.
