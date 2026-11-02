# Cấu trúc repo

| Đường dẫn | Vai trò |
| --- | --- |
| terraform/ | AWS resources, EKS managed add-ons, Pod Identity và output platform_contract |
| kubernetes/platform/ | Values chart chính thức Karpenter/KEDA/Prometheus/Grafana |
| kubernetes/charts/platform-config/ | NodePool, EC2NodeClass, auth KEDA và Catalog ServiceMonitor |
| kubernetes/charts/worker-scaling/ | Ba ScaledObject |
| kubernetes/environments/dev/ | YAML tường minh: AWS endpoints, image/tag và chính sách dev |
| kubernetes/apps/, namespaces/ | Manifest ServiceAccount/Namespace và Kustomization gom file |
| scripts/ | Các lệnh triển khai trực tiếp; xem scripts/README.md |
| observability/ | Dashboard và các placeholder alert chưa bật |
| tests/ | Test offline dùng mock command và Helm render |
| .generated/ | Artifact kiểm tra cục bộ còn lưu; không được dùng làm đầu vào deploy |

Chart ứng dụng vẫn ở repo backend. Các placeholder NetworkPolicy, alert và k6 chưa được bật. Versions của chart platform được ghi ngay trong các lệnh Helm; nâng version cần đọc hướng dẫn CRDs tương ứng.
