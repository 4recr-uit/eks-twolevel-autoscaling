# Triển khai môi trường dev

Các lệnh dưới đây chạy bằng Bash từ thư mục `scripts` của repo hạ tầng. Script triển khai thực thi trực tiếp trên context `twolevel-dev`.

## Chuẩn bị cấu hình

1. Tạo hạ tầng bằng Terraform và hoàn tất chuyển quyền quản lý add-on nếu cần.
2. Chạy `bash 01-export-config.sh`; đối chiếu output với values trong `kubernetes/environments/dev/`, bao gồm image, queue URL, database endpoint, NodePool và AMI alias.
3. Chuẩn bị database users/schema, image và quyền truy cập. Tạo bản local của hai mẫu Secret trong `kubernetes/environments/dev/secrets/`, điền credentials và không commit các file local.
4. Chuẩn bị file RDS CA bundle trên máy. Các Secret và ConfigMap CA sẽ được tạo sau bước bootstrap.

## Thứ tự triển khai

```bash
bash 02-bootstrap.sh
bash 02-apply-secrets.sh
python 02-create-rds-ca-configmap.py --ca-file /path/to/global-bundle.pem --dry-run
python 02-create-rds-ca-configmap.py --ca-file /path/to/global-bundle.pem
bash 03-deploy-monitoring.sh
bash 04-deploy-platform.sh
bash 05-deploy-apps.sh
bash 06-deploy-autoscaling.sh
bash 06-enable-nodepool.sh
bash 07-verify.sh
bash 08-port-forward.sh
```

Thay đường dẫn CA bằng file thực tế. `02-apply-secrets.sh` yêu cầu cả `database-secrets.local.yaml` và `grafana-admin.local.yaml`. Bước autoscaling tạo release cấu hình ban đầu với NodePool tắt; bước tiếp theo bật NodePool trước khi verify.

## Nghiệm thu và cập nhật

`07-verify.sh` kiểm tra rollout và trạng thái Ready. Kiểm tra thêm luồng API → SQS → worker → database, queue/DLQ và Prometheus targets; quan sát scale-out/scale-in với tải phù hợp.

Khi `worker-scaling` đã tồn tại, `05-deploy-apps.sh` sẽ dừng để tránh ghi đè replica do KEDA quản lý. Khi nâng cấp chart Cart, Orders hoặc Checkout, dùng values của service **và** `worker-keda.yaml`, như ở `06-deploy-autoscaling.sh`; giữ `worker.scaledObject.enabled=false`. Kiểm tra release và values trước khi nâng cấp từng ứng dụng. Nếu push lại image cùng tag, restart workload liên quan để Pod tải lại image.

## Gỡ triển khai

Dừng producer, xử lý hoặc bảo toàn message trước khi chạy `bash 09-teardown.sh`. Script gỡ ứng dụng, scaler, NodePool và Karpenter controller theo thứ tự; giữ monitoring/KEDA, CRD, namespace, Secret/PVC và tài nguyên AWS. Nếu còn NodeClaim, script giữ controller lại.

Terraform destroy là bước riêng sau khi kiểm tra tài nguyên ngoài cluster và dữ liệu cần giữ. Không xóa finalizer để bỏ qua lỗi drain hoặc IAM.
