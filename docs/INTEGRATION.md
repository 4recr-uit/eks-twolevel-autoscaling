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
| Cart | cart-queue | cart-api | cart-worker | carts-worker | PostgreSQL: retaildb, schema cart |
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
| KEDA ScaledObject cho worker | Helm chart worker-scaling trong repo hạ tầng |
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

## 6. Secret kết nối database

Helm chart hỗ trợ hai cách: `create: true` để Helm tạo Secret; `create: false`
để dùng Secret có sẵn. Cờ này chỉ điều khiển việc tạo Secret, không ngăn
Deployment đọc Secret khi cần kết nối database.

| Service | Trường values | Tên Secret mặc định | Key cần có |
|---|---|---|---|
| Cart | `database.secret` | `cart-db` | `DB_PASSWORD` |
| Orders | `database.secret` | `orders-db` | `DB_PASSWORD` |
| Checkout | `database.secret` | `checkout-db` | `DB_PASSWORD` |
| Catalog | `app.persistence.secret` | `catalog-db` | `RETAIL_CATALOG_PERSISTENCE_USER`, `RETAIL_CATALOG_PERSISTENCE_PASSWORD` |
| Recommendations | `app.persistence.secret` | `recommendations-db` | `RETAIL_RECOMMENDATIONS_PERSISTENCE_PASSWORD` |

- Cart, Orders, Checkout: cả API và worker tham chiếu cùng Secret của service.
  Username lấy từ `database.user` trong ConfigMap. Secret vẫn được tham chiếu
  khi `create: false`; nếu bỏ trống tên thì dùng `<fullname>-db`.
- Catalog: username và password lấy từ Secret khi dùng MySQL. Nếu bật search,
  Secret đó cần thêm `RETAIL_CATALOG_SEARCH_OS_USERNAME` và
  `RETAIL_CATALOG_SEARCH_OS_PASSWORD`.
- Recommendations: username lấy từ `app.persistence.user`; chỉ tạo/tham chiếu
  Secret khi provider là `mysql`. Chế độ `in-memory` không cần database Secret.
- Với EKS, người vận hành hoặc cơ chế quản lý secret phải tạo các Secret ứng dụng
  trong namespace `retailstore` trước khi deploy. Helm không tự đọc RDS master
  secret từ AWS Secrets Manager. Không commit credentials thực tế vào Git.
- Khi chuyển một release đã có Secret do Helm tạo sang Secret quản lý bên ngoài,
  tạo Secret với tên mới trước, rồi cập nhật values sang tên mới và `create: false`.
  Chỉ tắt `create` với tên cũ có thể khiến Helm xóa Secret cũ lúc upgrade.
- Sau khi đổi credentials trong Secret, restart các workload dùng biến môi trường
  đó để container nhận giá trị mới. Render chart chỉ kiểm tra cấu hình, không
  xác minh Secret tồn tại, mật khẩu đúng hoặc quyền truy cập RDS.

### 6.1. Tạo năm Secret bằng một file

Mẫu: [database-secrets.example.yaml](../kubernetes/environments/dev/secrets/database-secrets.example.yaml).
File dùng `stringData`, bạn điền mật khẩu trực tiếp, không cần tự encode base64.
Kubernetes chuyển các giá trị này thành `data` khi lưu Secret.
[Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

1. Dùng bản `database-secrets.local.yaml` cùng thư mục để điền credentials thật.
   File này được Git ignore. Chỉ sửa file local; giữ file example không có mật khẩu thật.
2. Thay đúng năm dòng `REPLACE_WITH_...` bằng mật khẩu đã đặt trên RDS. Giữ nguyên
   bốn dấu cách đầu dòng. Password là phần sau thụt dòng `|-`, không thêm dấu nháy
   bao quanh và không thêm comment cuối dòng. `|-` tránh thêm newline vào mật khẩu.
3. Catalog username đã đặt là `catalog_app`. Nếu user thực tế khác thì sửa dòng này.
   User PostgreSQL và Recommendations lấy từ `apps/*.yaml`:
   `cart_app`, `orders_app`, `checkout_app`, `recommendations_app`.
4. Namespace là `retailstore`; context của các lệnh dưới là `twolevel-dev`.

Nếu chưa có file local, tạo một bản sao bằng PowerShell (lệnh dừng nếu file đã có):

```powershell
$secretDir = 'D:\WorkSpace\UITMagnolia\eks-twolevel-autoscaling\kubernetes\environments\dev\secrets'
if (Test-Path -LiteralPath "$secretDir\database-secrets.local.yaml") { throw 'File local đã tồn tại; mở file đó để sửa, không ghi đè.' }
Copy-Item -LiteralPath "$secretDir\database-secrets.example.yaml" -Destination "$secretDir\database-secrets.local.yaml"
```

Mở file local trong editor và điền mật khẩu trước khi tiếp tục. Không gửi mật khẩu
vào chat, không commit file local, không chạy `kubectl get secret -o yaml` để chia sẻ kết quả.

Xác nhận context trỏ đúng EKS cluster (nếu chưa có alias, chạy lệnh đầu):

```powershell
aws eks update-kubeconfig --region us-east-1 --name twolevel-autoscaling-dev --alias twolevel-dev
kubectl config view --context twolevel-dev --minify
kubectl --context twolevel-dev get namespace retailstore
```

Nếu namespace chưa có, tạo bằng `kubectl --context twolevel-dev create namespace retailstore`.

Sau khi điền mật khẩu, kiểm tra rồi apply bằng PowerShell:

```powershell
$secretFile = 'D:\WorkSpace\UITMagnolia\eks-twolevel-autoscaling\kubernetes\environments\dev\secrets\database-secrets.local.yaml'
if (Select-String -LiteralPath $secretFile -Pattern '^\s+REPLACE_WITH_' -Quiet) { throw 'Chưa điền đủ năm mật khẩu.' }
kubectl --context twolevel-dev apply --dry-run=server -f $secretFile
if ($LASTEXITCODE -ne 0) { throw 'Kiểm tra Secret thất bại; chưa apply.' }
kubectl --context twolevel-dev apply -f $secretFile
```

Lệnh dry-run gửi cấu hình đến API server để kiểm tra nhưng không lưu object.
Không thêm `-o yaml`/`-o json` vào hai lệnh apply để tránh in credentials.
Không dùng `--server-side` với mẫu `stringData` này.

Xem tên và số key, không hiển thị giá trị mật khẩu:

```powershell
kubectl --context twolevel-dev -n retailstore get secret cart-db orders-db checkout-db catalog-db recommendations-db
```

Kết quả mong đợi: năm Secret `Opaque`; cột DATA là `1, 1, 1, 2, 1` tương ứng.
Đây chỉ xác nhận Secret tồn tại và số key; chưa chứng minh password đúng hoặc Pod
kết nối được RDS. Secret giữ nguyên các tên chart đang tham chiếu với `create: false`.

File này chỉ chuẩn bị credentials. Trước khi deploy cần hoàn thiện TLS/CA trong Pod
(MySQL users yêu cầu SSL), endpoint và image/tag. Pod dùng cổng RDS thật 5432/3306,
không dùng cổng SSM tunnel 15432/13306. Nếu ứng dụng đã chạy và vừa đổi Secret,
cần restart đúng workload để nạp lại biến môi trường.

### 6.2. CA và TLS cho Pod

File CA không cần nằm trong repo hay image. Script
[02-create-rds-ca-configmap.py](../scripts/02-create-rds-ca-configmap.py) đọc file
PEM đã tải trên máy, kiểm tra đọc được chứng chỉ, rồi tạo/cập nhật **một ConfigMap**
`rds-ca` trong namespace `retailstore`. Không deploy app, không thay đổi RDS hay Secret.
Script dùng Python standard library và `kubectl` có trong PATH.

Trong PowerShell, thay đường dẫn CA nếu file của bạn lưu ở chỗ khác:

```powershell
python 'D:\WorkSpace\UITMagnolia\eks-twolevel-autoscaling\scripts\02-create-rds-ca-configmap.py' --ca-file 'C:\Users\hdatuan\Downloads\global-bundle.pem' --dry-run
```

Nếu kiểm tra thành công, chạy lại bỏ `--dry-run` để lưu ConfigMap vào cluster:

```powershell
python 'D:\WorkSpace\UITMagnolia\eks-twolevel-autoscaling\scripts\02-create-rds-ca-configmap.py' --ca-file 'C:\Users\hdatuan\Downloads\global-bundle.pem'
kubectl --context twolevel-dev -n retailstore get configmap rds-ca
```

Mặc định script dùng context `twolevel-dev`, namespace `retailstore`, tên `rds-ca`.
Namespace và context cần có trước. Có thể đổi bằng `--context`, `--namespace`,
`--name`; nếu đổi tên ConfigMap thì phải đổi `databaseTLS.caConfigMapName` trong
các values tương ứng. `--dry-run` kiểm tra qua API server nhưng chưa lưu object.

Các chart trong repo backend đã hỗ trợ `databaseTLS.enabled`, mặc định `false`.
Năm file values dev trong `kubernetes/environments/dev/apps/` đã bật `true` và
tham chiếu ConfigMap `rds-ca`. Chart mount key `global-bundle.pem` thành file
`/etc/rds-ca/global-bundle.pem`, read-only, trên **cả API và worker**.
[ConfigMap volume](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/).

| Workload | Biến môi trường chart thêm khi bật TLS |
|---|---|
| Cart, Orders, Checkout — API và worker | `DB_SSLMODE=verify-full`, `DB_SSLROOTCERT=/etc/rds-ca/global-bundle.pem` |
| Catalog | `RETAIL_CATALOG_PERSISTENCE_TLS=true`, `SSL_CERT_FILE=/etc/rds-ca/global-bundle.pem` |
| Recommendations | `RETAIL_RECOMMENDATIONS_PERSISTENCE_TLS=true`, `DB_SSL_CA=/etc/rds-ca/global-bundle.pem` |

Các biến được đặt trực tiếp trong Deployment để TLS vẫn hoạt động khi dùng
ConfigMap ứng dụng bên ngoài (`configMap.create=false`). PostgreSQL dev values
cũng đổi `sslmode` sang `verify-full`. Chỉ cấu hình Helm thay đổi, các image mới
đã hỗ trợ các biến này nên không cần build lại chỉ để mount CA/bật TLS.
Không đặt `DATABASE_URL` riêng trong Secret nếu muốn dùng cấu hình DB/TLS từ values,
vì URL đầy đủ được backend ưu tiên và có thể ghi đè các tham số TLS.

Sau khi có CA và năm Secret, deploy bằng **Git Bash**, từ repo hạ tầng:

```bash
cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling
bash scripts/05-deploy-apps.sh
```

Script 05 kiểm tra ConfigMap và Secret tồn tại trước khi chạy Helm. Cần hoàn thành
prerequisites trong [DEPLOYMENT.md](DEPLOYMENT.md), gồm ServiceAccount, monitoring
CRDs nếu bật ServiceMonitor, platform và quyền truy cập ECR. Lần deploy này thay
Pod spec (env/volume), nên Helm sẽ rollout Pod và tải image theo `pullPolicy: Always`.

Kiểm tra sau deploy:

```powershell
kubectl --context twolevel-dev -n retailstore get pods
kubectl --context twolevel-dev -n retailstore rollout status deployment/catalog
kubectl --context twolevel-dev -n retailstore logs deployment/catalog --tail=50
```

CA trong ConfigMap là public certificate, không phải username/password. Không cần
SSM tunnel hay file hosts của DBeaver cho Pod: chúng dùng endpoint RDS và cổng thật
5432/3306 trong VPC. Nếu cập nhật nội dung CA sau này, restart workload để driver
nạp lại trust store/SSL context, rồi kiểm tra rollout. Bước này chưa kiểm chứng
TLS thực tế; phải nghiệm thu bằng Pod startup/readiness và thao tác API/worker.

## 7. Các điểm cần hoàn thiện

- Chart tổng và Terraform dùng tên Cart Deployment `carts-worker`;
  khi cài chart Cart riêng, đặt `fullnameOverride=carts` để giữ đúng tên.
- ScaledObject trong backend chart đã tắt mặc định; giữ trạng thái này khi
  Helm release worker-scaling quản lý autoscaling.
- Chuẩn bị user database, quyền migration và Secret thực tế theo bảng trên.
- Thay values mặc định bằng cấu hình EKS: image, queue URL,
  database endpoint, node selector và credentials.
- Kiểm tra quyền và kết nối trên AWS sau khi triển khai.

## Luồng triển khai Bash

Xem [DEPLOYMENT.md](DEPLOYMENT.md). Image/service charts lấy từ repo backend; mỗi service có Helm release riêng. Values EKS ghi đè node selector và trỏ trực tiếp RDS, không phụ thuộc PgBouncer. Cart dùng fullname `carts`. Ban đầu worker chạy một replica cố định. Khi bật KEDA, dùng thêm values `apps/worker-keda.yaml` để Helm không ghi `spec.replicas`; giữ `worker.scaledObject.enabled=false` vì release worker-scaling quản lý ScaledObject.

Users mặc định trong values EKS là `cart_app`, `orders_app`, `checkout_app`, `recommendations_app`; sửa theo users thực tế đã provision. Catalog lấy username từ Secret. Script không tạo DB user/schema hoặc tự đọc RDS master secret.
