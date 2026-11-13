# Tích hợp backend và hạ tầng

## Luồng xử lý

Client → API → SQS → worker → database. KEDA theo dõi queue để điều chỉnh số worker; Karpenter tạo node khi Pod không thể được xếp lịch do thiếu capacity.

## Service và tài nguyên

Ứng dụng chạy trong namespace `retailstore`.

| Service | Queue | ServiceAccount API / worker | Worker Deployment | Database |
|---|---|---|---|---|
| Cart | `cart-queue` | `cart-api` / `cart-worker` | `carts-worker` | PostgreSQL `retaildb`, schema `cart` |
| Orders | `orders-queue` | `orders-api` / `orders-worker` | `orders-worker` | PostgreSQL `retaildb`, schema `orders` |
| Checkout | `checkout-queue` | `checkout-api` / `checkout-worker` | `checkout-worker` | PostgreSQL `retaildb`, schema `checkout` |
| Catalog | — | Theo chart | — | MySQL `catalogdb` |
| Recommendations | — | Theo chart | — | MySQL `catalogdb` hoặc in-memory |

API có quyền gửi message vào queue của service; worker có quyền nhận, xóa và thay đổi visibility. KEDA có quyền đọc thông tin queue. Các ServiceAccount liên quan được gắn IAM role qua EKS Pod Identity.

Repo backend quản lý source code và chart ứng dụng. Repo hạ tầng quản lý Terraform AWS, values dev, ServiceAccount và chart `worker-scaling`. Mỗi ứng dụng được cài bằng Helm release riêng. URL queue/ECR và endpoint database lấy từ Terraform output.

## Secret database

Values dev sử dụng Secret có sẵn trong namespace `retailstore`. Helm không tự lấy RDS master secret; database users, quyền và Secret ứng dụng cần được chuẩn bị riêng.

| Service | Secret | Key |
|---|---|---|
| Cart | `cart-db` | `DB_PASSWORD` |
| Orders | `orders-db` | `DB_PASSWORD` |
| Checkout | `checkout-db` | `DB_PASSWORD` |
| Catalog | `catalog-db` | `RETAIL_CATALOG_PERSISTENCE_USER`, `RETAIL_CATALOG_PERSISTENCE_PASSWORD` |
| Recommendations | `recommendations-db` | `RETAIL_RECOMMENDATIONS_PERSISTENCE_PASSWORD` |

API và worker của Cart, Orders, Checkout cùng dùng Secret của service. Username PostgreSQL và Recommendations nằm trong values; Catalog lấy username từ Secret. Recommendations chỉ cần Secret database khi dùng MySQL; Catalog cần thêm Secret key cho search nếu bật search.

Chart hỗ trợ tạo Secret hoặc dùng Secret có sẵn qua `create`. Khi chuyển từ Secret do Helm quản lý sang Secret bên ngoài, tạo Secret với tên mới trước rồi cập nhật values; tắt `create` với tên cũ có thể khiến Helm xóa Secret. Sau khi đổi credentials được đưa vào biến môi trường, restart các workload liên quan.

Mẫu Secret nằm trong `kubernetes/environments/dev/secrets/`. Bản local chứa credentials được Git bỏ qua; không đưa mật khẩu vào values, log hoặc shell history.

## TLS tới RDS

Values dev bật `databaseTLS` và tham chiếu ConfigMap `rds-ca`, được mount thành `/etc/rds-ca/global-bundle.pem` trong workload liên quan. Cart, Orders và Checkout dùng `DB_SSLMODE=verify-full` và `DB_SSLROOTCERT`; Catalog dùng `RETAIL_CATALOG_PERSISTENCE_TLS` và `SSL_CERT_FILE`; Recommendations dùng `RETAIL_RECOMMENDATIONS_PERSISTENCE_TLS` và `DB_SSL_CA`.

CA bundle là chứng chỉ công khai, không chứa credentials. Pod kết nối trực tiếp endpoint RDS qua cổng PostgreSQL 5432 hoặc MySQL 3306. Không đặt `DATABASE_URL` riêng trong Secret nếu muốn dùng các values DB/TLS của chart, vì URL đầy đủ có thể được ứng dụng ưu tiên. Khi đổi CA, restart workload để driver nạp lại trust store và kiểm tra kết nối thực tế.
