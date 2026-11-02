# Metrics và Grafana

Luồng mẫu mặc định có monitoring: chạy 03-deploy-monitoring.sh trước 04-deploy-platform.sh và 05-deploy-apps.sh. Chuẩn bị Secret grafana-admin có admin-user/admin-password trong namespace monitoring. Prometheus/Grafana chạy bằng kube-prometheus-stack; retention 24h, Alertmanager tắt, không yêu cầu PVC/public ingress.

Chart Karpenter/KEDA tự tạo controller ServiceMonitors khi bật monitoring. Backend charts quản lý monitors của Cart/Orders/Checkout/Recommendations; platform-config thêm monitor cho Catalog. Prometheus được cấu hình tìm monitors ngoài namespace monitoring.

Dashboard `observability/dashboards/autoscaling-overview.json` được cài thành ConfigMap với nhãn grafana_dashboard=1. Dashboard hiển thị desired/ready/Pending worker, HPA, node, CPU/memory, throughput, trạng thái xử lý, latency, KEDA, Karpenter và SQS. Chọn datasource Prometheus, CloudWatch, region và queue ở đầu dashboard; mặc định SQS là `orders-queue` tại `us-east-1`. Histogram percentile là ước lượng theo bucket; các khoảng 5 phút có thể làm mượt tải ngắn. KEDA/HPA có thể không có series khi chưa bật scaler. Panel Karpenter hiển thị node controller quan sát được, không phải số node do Karpenter tạo; đối chiếu NodeClaim/events để đo provisioning. SQS là metric gần đúng và có độ trễ; `No data` không đồng nghĩa với 0.

Để cập nhật riêng dashboard khi monitoring đã cài, chạy `bash scripts/update-monitoring-dashboard.sh`. Để cập nhật cả cấu hình datasource, chạy `bash scripts/03-deploy-monitoring.sh` sau khi đã kiểm tra Helm values đang áp dụng. `terraform/grafana-cloudwatch.tf` quản lý IAM role chỉ đọc CloudWatch metrics và EKS Pod Identity association cho service account `monitoring-grafana`; role trust giới hạn cluster, namespace và service account. Terraform phải được plan/review và apply theo quy trình dự án; sau khi tạo association, restart Grafana để pod nhận identity. Không lưu access key trong repo hoặc dashboard. Kiểm tra region, chọn CloudWatch ở dashboard và test query SQS metric; CloudWatch API có thể phát sinh chi phí khi refresh dashboard.

Các mốc first job, Pending, NodeClaim, node Ready và pod Ready cần đối chiếu logs/events cùng timestamp; dashboard không thay thế thu timeline. Xuất dữ liệu mỗi lượt trước khi hết retention; pod ngắn hạn có thể mất mẫu counter. Không dùng queue depth gần đúng để đối soát job duy nhất hoặc chứng minh không mất message.

Sau 02-bootstrap.sh đã chọn context twolevel-dev, chạy `bash scripts/08-port-forward.sh`, mở localhost:3000. Kiểm tra Prometheus targets thay vì chỉ nhìn Pod Running. Metrics/labels có thể thay đổi khi nâng version controller; đối chiếu dashboard với version đang pin.

Dữ liệu metrics/Grafana mặc định không bền vững khi Pod/cluster bị xóa. Logs/traces, alert delivery, dashboard latency chi tiết và storage bền vững cần cấu hình riêng; các file placeholder còn lại chưa được triển khai.

Nếu bỏ qua monitoring, tắt serviceMonitor trong values Karpenter/KEDA và các app có monitor, đặt monitoring=false trong environments/dev/platform.yaml, đồng thời bỏ nhóm lệnh kiểm tra monitoring trong 07-verify.sh. Không apply ServiceMonitor khi chưa cài CRD tương ứng.
