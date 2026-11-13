# Khắc phục sự cố

| Hiện tượng | Kiểm tra và xử lý |
|---|---|
| EKS API timeout hoặc Unauthorized | Kiểm tra mạng, CIDR API, IAM và EKS access entry; quyền AWS không tự bảo đảm quyền Kubernetes. |
| Helm báo ownership metadata sai | Đối chiếu object hiện có và chủ sở hữu trước khi chuyển quyền quản lý; không cài đè khi chưa rõ trạng thái. |
| Karpenter controller Pending | Kiểm tra system node, CPU/memory và điều kiện scheduling/anti-affinity của controller. |
| EC2NodeClass hoặc NodePool không Ready | Kiểm tra AMI alias, subnet/security group, IAM role, access entry và trạng thái controller. |
| Worker Pod Pending | Kiểm tra scheduler events, requests, node selector, NodePool limits và instance requirements. |
| Worker không scale | Kiểm tra queue URL, IAM/auth, ScaledObject Ready, KEDA logs và HPA xung đột. |
| Không tìm thấy ServiceMonitor API | Kiểm tra monitoring đã được cài và CRD đã Established trước platform/app. |
| Helm app timeout hoặc lỗi DB | Kiểm tra image, user/schema/quyền DB, Secret, TLS/CA và security group RDS; Helm render không kiểm tra kết nối. |
| Script dừng giữa nhiều release | Kiểm tra Helm status/history: release trước đó có thể đã cập nhật; xử lý hoặc rollback từng release rồi chạy lại bước phù hợp. |
| Teardown còn NodeClaim | Giữ Karpenter controller; kiểm tra drain, PodDisruptionBudget, finalizer và quyền AWS trước khi tiếp tục. |

Các script triển khai dùng context `twolevel-dev`. Không chia sẻ Terraform state, Secret hoặc log có chứa credentials khi chẩn đoán.
