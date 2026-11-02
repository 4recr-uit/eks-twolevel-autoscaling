# Khắc phục lỗi triển khai

| Hiện tượng | Kiểm tra |
| --- | --- |
| Không tìm thấy Bash/Python trên Windows | Dùng Git Bash hoặc WSL. Các script deploy không cần Python; 00-init-s3-backend.py vẫn cần Python/boto3 |
| Terraform vẫn quản lý cluster resource | Hoàn tất MIGRATION.md, review removed/destroy=false; không xóa cả module Karpenter khỏi state |
| Helm báo ownership metadata sai | Object đã tồn tại trước migration; đối chiếu spec/owner, adopt đúng object theo MIGRATION.md |
| Sai account hoặc endpoint | Kiểm tra AWS_PROFILE, environment và backend/key. Không bỏ qua kiểm tra contract |
| EKS API timeout/Unauthorized | Kiểm tra CIDR, mạng, IAM/access entry của operator. Terraform role và Kubernetes quyền là hai bước riêng |
| Karpenter controller Pending | Cần seed nodes role=system, đủ CPU/memory và đủ node cho anti-affinity của hai replicas |
| NodeClass không Ready | Kiểm tra alias AMI, discovery subnet tags, SG IDs, node IAM/access entry và Pod Identity |
| Pod vẫn Pending | Kiểm tra requests, node selectors, NodePool limits và instance requirements; không phải mọi Pending đều giải quyết bằng scale-out |
| Worker không scale | Kiểm tra queue mapping/auth, KEDA logs/AccessDenied và ScaledObject Ready; đối chiếu HPA xung đột |
| ServiceMonitor API chưa tồn tại | Chạy 03-deploy-monitoring.sh trước platform/app; nếu bỏ monitoring thì tắt các ServiceMonitor trong YAML |
| Helm app timeout/DB connection fail | Kiểm tra image tag, DB users/schema/permissions, Secret keys, TLS/CA và RDS SG; render không kiểm tra kết nối |
| Bash dừng giữa nhiều releases | Các release trước có thể đã cập nhật; dùng helm status/history, sửa lỗi hoặc rollback từng release rồi chạy lại |
| Teardown kẹt NodeClaim | Giữ controller, kiểm tra finalizer/drain/PDB và quyền AWS. Không force-remove để che lỗi |

02-bootstrap.sh tạo/chọn context twolevel-dev trong kubeconfig của bạn; các lệnh deploy dùng context này tường minh. Không chia sẻ file state, Secret JSON hay log chứa credentials khi chẩn đoán.
