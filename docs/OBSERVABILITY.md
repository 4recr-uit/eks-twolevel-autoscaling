# Metrics và Grafana

## Thành phần

Monitoring dùng `kube-prometheus-stack` với Prometheus và Grafana. Cấu hình dev giữ metrics 24 giờ, tắt Alertmanager và không yêu cầu PVC hoặc public ingress. KEDA, Karpenter và các ứng dụng cung cấp ServiceMonitor; Prometheus được cấu hình tìm monitor ngoài namespace `monitoring`.

Grafana dùng Secret `grafana-admin` và được truy cập qua port-forward. Dashboard `observability/dashboards/autoscaling-overview.json` được nạp bằng ConfigMap có nhãn `grafana_dashboard=1`.

## Dashboard và datasource

Dashboard hiển thị worker, HPA/KEDA, node/Karpenter, CPU/memory, throughput, trạng thái xử lý, latency và SQS. Chọn datasource Prometheus, CloudWatch, region và queue; mặc định là `orders-queue` ở `us-east-1`.

Grafana dùng EKS Pod Identity để đọc CloudWatch metrics; role và association được quản lý bằng Terraform. Sau khi tạo association, restart Grafana để Pod nhận identity, sau đó kiểm tra datasource và query SQS. CloudWatch API có thể phát sinh chi phí khi refresh dashboard.

Để cập nhật riêng dashboard, từ thư mục `scripts`:

```bash
kubectl --context twolevel-dev -n monitoring create configmap autoscaling-dashboard \
  --from-file=../observability/dashboards/autoscaling-overview.json --dry-run=client -o yaml | \
  kubectl --context twolevel-dev apply -f -
kubectl --context twolevel-dev -n monitoring label configmap autoscaling-dashboard grafana_dashboard=1 --overwrite
```

`03-deploy-monitoring.sh` cập nhật cả Helm release và dashboard; kiểm tra values hiện hành trước khi chạy lại.

## Giới hạn dữ liệu

- SQS metrics là số gần đúng và có độ trễ; `No data` không đồng nghĩa với 0.
- Percentile từ histogram là ước lượng theo bucket; cửa sổ 5 phút có thể làm mượt burst ngắn. Pod sống ngắn có thể thiếu mẫu counter.
- Panel Karpenter thể hiện node controller quan sát được, không phải số node do Karpenter tạo. Đối chiếu NodeClaim, event và log để phân tích provisioning.
- Dashboard không thay thế đối soát job ID hoặc thu timeline. Metrics và dữ liệu Grafana mặc định không bền vững khi Pod hoặc cluster bị xóa.
