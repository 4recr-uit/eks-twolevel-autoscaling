# Scripts

Các file chứa lệnh AWS CLI, Helm và kubectl trực tiếp. Chạy bằng **Bash từ thư mục gốc repo**; có thể mở file và chạy từng lệnh riêng.

**Script deploy thực thi ngay khi chạy. Không còn các tham số `--apply`, `--env`, `--backend` hoặc chế độ tự sinh cấu hình.**

| File | Công việc |
| --- | --- |
| `00-init-s3-backend.py` | Tùy chọn, trước Terraform init/apply: chuẩn bị S3 backend nếu chưa có; cần Python và boto3 |
| `01-export-config.sh` | In thông tin Terraform để bạn điền vào YAML; không sửa file |
| `02-bootstrap.sh` | Kết nối EKS, chọn context `twolevel-dev`, tạo namespace và ServiceAccount |
| `03-deploy-monitoring.sh` | Cài Prometheus/Grafana và dashboard |
| `04-deploy-platform.sh` | Cài Karpenter/KEDA và cấu hình NodePool, NodeClass, xác thực |
| `05-deploy-apps.sh` | Triển khai 5 backend từ chart trong repo backend, chưa gồm UI |
| `06-deploy-autoscaling.sh` | Tạo 3 ScaledObject cho worker |
| `07-verify.sh` | Kiểm tra rollout, node, autoscaling và monitoring |
| `08-port-forward.sh` | Truy cập Grafana tại localhost:3000; Ctrl+C để dừng port-forward |
| `09-teardown.sh` | Chỉ chạy khi muốn gỡ ứng dụng và Karpenter; giữ monitoring/KEDA, CRDs, Secret/PVC và AWS |

## Chuẩn bị và thứ tự chạy

Cần AWS CLI đã đăng nhập, Terraform, Helm và kubectl. Repo backend mặc định nằm cạnh repo này: `../retailstore-backend-microservices`.

Số thứ tự thể hiện vị trí trong quy trình, không có nghĩa chạy tất cả file liên tục:

1. **00 — Chuẩn bị backend, nếu cần:** chạy trước Terraform init/apply khi chưa có S3 backend. Nếu đã apply thành công thì bỏ qua bước này. Script cần Python/boto3; xem tham số bằng `python scripts/00-init-s3-backend.py --help`.
2. **Terraform — Tạo hạ tầng AWS:** chuẩn bị tfvars, review plan rồi apply theo [terraform/README.md](../terraform/README.md).
3. **01 — Xem output:** lấy thông tin tài nguyên để điền values môi trường.
4. **02 — Bootstrap:** kết nối cluster, tạo namespace và ServiceAccount. Sau đó chuẩn bị image, database user/schema và các Secret.
5. **03 — Monitoring:** cài Prometheus/Grafana và CRD ServiceMonitor trước các chart đang bật monitoring.
6. **04 — Platform:** cài Karpenter/KEDA, NodeClass, NodePool và xác thực SQS.
7. **05 — Ứng dụng:** triển khai năm backend.
8. **06 — Autoscaling:** tạo ScaledObject cho ba worker đã tồn tại.
9. **07 — Kiểm tra:** xác minh rollout, node, scaler và monitoring; thử giao dịch thực tế riêng.
10. **08 — Truy cập:** port-forward Grafana khi cần; lệnh giữ terminal cho đến khi Ctrl+C.
11. **09 — Gỡ:** thao tác riêng khi kết thúc, không thuộc chuỗi cài đặt bình thường.

Các lệnh dưới đây bắt đầu sau khi Terraform apply đã thành công:

```bash
bash scripts/01-export-config.sh
```

Điền các giá trị `REPLACE_...` và `nodePool.amiAlias` trong `kubernetes/environments/dev/` theo output vừa xem. Kiểm tra image/tag, DB user và tên Secret trong `apps/*.yaml`. Không ghi mật khẩu vào các YAML này. Chart versions nằm trực tiếp trong lệnh Helm; cluster/region/context nằm trong `02-bootstrap.sh` và các lệnh triển khai.

```bash
bash scripts/02-bootstrap.sh
# Chuẩn bị DB users/schema, image trên ECR và các Secret ứng dụng.
# Tạo Secret grafana-admin trong namespace monitoring, gồm admin-user/admin-password.
bash scripts/03-deploy-monitoring.sh
bash scripts/04-deploy-platform.sh
bash scripts/05-deploy-apps.sh
bash scripts/06-deploy-autoscaling.sh
bash scripts/07-verify.sh
bash scripts/08-port-forward.sh
```

Luồng mẫu có monitoring và dùng context `twolevel-dev`. Nếu cluster hoặc đường dẫn backend khác, sửa các lệnh/YAML trước. Nếu trước đây Terraform đã cài add-on, đọc [MIGRATION.md](../docs/MIGRATION.md) trước triển khai. Sau verify cần thử giao dịch API → SQS → worker → DB và quan sát scaling thực tế.

## Cập nhật và gỡ

Sửa YAML rồi chạy lại đúng bước cần cập nhật. Nếu push bản mới vẫn dùng tag `latest`, cần khởi động lại workload để tải image mới (`pullPolicy: Always` đã được đặt):

```bash
kubectl --context twolevel-dev -n retailstore rollout restart deployment \
  carts-api carts-worker orders-api orders-worker checkout-api checkout-worker catalog recommendations
```

Chỉ chạy `bash scripts/09-teardown.sh` khi muốn gỡ, sau khi dừng tải/producer và xử lý hoặc bảo toàn message. Script dừng nếu còn NodeClaim trước khi gỡ controller; Terraform destroy là bước riêng.
