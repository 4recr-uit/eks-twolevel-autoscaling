# Triển khai bằng các lệnh tường minh

Hướng dẫn chạy chính nằm trong [scripts/README.md](../scripts/README.md). Chạy Bash từ repo root. Mỗi script là danh sách lệnh AWS CLI/Helm/kubectl có thể chạy riêng; không còn common.sh, config.py, các tham số --apply/--env/--backend, hoặc values sinh tự động.

## Chuẩn bị

1. Tạo hạ tầng AWS bằng Terraform; nếu đã có add-on do Terraform quản lý, hoàn tất [MIGRATION.md](MIGRATION.md) trước.
2. Chạy `bash scripts/01-export-config.sh` để xem platform_contract. Điền các REPLACE_... trong `kubernetes/environments/dev/`, bao gồm karpenter.yaml, platform.yaml, autoscaling.yaml và apps/*.yaml. Điền AMI alias đã kiểm thử trong platform.yaml.
3. Kiểm tra image/tag, DB users/schema, TLS/CA và Secret names. Values không chứa mật khẩu. Image ứng dụng phải được build/push trước; chart và image cần cùng phiên bản hỗ trợ /ready.
4. Mẫu dev dùng region us-east-1, cluster twolevel-autoscaling-dev, context twolevel-dev và repo backend ở thư mục kế bên. Sửa lệnh/path/YAML nếu khác; không còn tự đối chiếu account/state/context qua helper.

## Thứ tự

```bash
bash scripts/02-bootstrap.sh
# Tạo các Secret ứng dụng và grafana-admin, chuẩn bị DB users/schema.
bash scripts/03-deploy-monitoring.sh
bash scripts/04-deploy-platform.sh
bash scripts/05-deploy-apps.sh
bash scripts/06-deploy-autoscaling.sh
bash scripts/07-verify.sh
bash scripts/08-port-forward.sh
```

Các lệnh deploy thực thi ngay, không có chế độ preview ngầm. Muốn xem manifest trước, dùng Helm template trực tiếp, ví dụ:

```bash
helm template cart ../retailstore-backend-microservices/src/cart/chart \
  --namespace retailstore -f kubernetes/environments/dev/apps/cart.yaml
```

Mẫu mặc định có monitoring. Kubernetes namespace/ServiceAccount dùng manifest trong repo; các giá trị phải khớp Pod Identity của Terraform. Worker không khai báo replicas khi KEDA quản lý; khi tạo lần đầu Kubernetes có thể khởi tạo một replica trước khi áp dụng ScaledObject.

## Nghiệm thu và cập nhật

Verify kiểm tra rollout/Ready, không chứng minh toàn bộ giao dịch thành công. Cần thử API → SQS → worker → DB; gửi tải có giới hạn để quan sát pod/node tăng rồi giảm, đối chiếu queue/DLQ và Prometheus targets. Không tạo thêm HPA độc lập cho worker đang do KEDA điều khiển.

Sửa values rồi chạy lại đúng script. Khi push lại latest, workload cũ chưa tự restart; chạy lệnh rollout restart trong scripts/README.md. Các release có thể cập nhật từng phần nếu một lệnh giữa script lỗi: xem helm status/history, sửa lỗi hoặc rollback release liên quan rồi chạy lại.

## Gỡ

Dừng tải/producer, xử lý hoặc bảo toàn message rồi mới chạy `bash scripts/09-teardown.sh`. Script gỡ năm backend/scaler, NodePool và controller Karpenter theo thứ tự; giữ monitoring/KEDA, CRDs, namespaces, Secrets/PVCs và AWS resources. Nếu còn NodeClaim thì controller được giữ lại.

Terraform destroy là bước riêng sau khi controller đã xử lý tài nguyên ngoài cluster và bạn đã review dữ liệu/snapshot cần giữ. Không force-remove finalizers để che lỗi drain/IAM.
