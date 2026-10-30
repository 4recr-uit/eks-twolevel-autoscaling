# Terraform: hạ tầng AWS

Terraform tạo VPC, EKS/seed node group, EKS managed add-ons, IAM/Pod Identity, ECR, SQS/DLQ, RDS, Budget và AWS prerequisites cho Karpenter. Các thành phần Kubernetes được triển khai sau bằng Bash/Helm.

Chạy lệnh từ root directory:

```bash
terraform -chdir=terraform init
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform validate
terraform -chdir=terraform plan
terraform -chdir=terraform apply
terraform -chdir=terraform state list
terraform -chdir=terraform output platform_contract
```

Chuẩn bị S3 backend đã cấu hình trong backend.tf, AWS credentials và tfvars riêng theo terraform.tfvars.example. Đặt đúng EKS API CIDR, ngân sách, RDS deletion protection/snapshot policy cho môi trường. Local tfvars/state không commit. Các biến cài add-on/scaling/monitoring đã chuyển sang kubernetes/environments/dev và script options.

`platform_contract` là output không chứa secret để bạn xem và điền tên cluster, role, queue, DB host và identity mappings vào YAML Kubernetes. Đây không phải file credentials. `module.karpenter[0]` được giữ để không đổi địa chỉ AWS resources có sẵn; module luôn tạo AWS prerequisites.

Deploy tiếp theo: [DEPLOYMENT.md](../docs/DEPLOYMENT.md). Gỡ workload và node Karpenter theo runbook trước khi review `terraform plan -destroy`; không hủy cluster khi controllers còn cần xử lý tài nguyên bên ngoài.

## GitHub Actions push ECR

`enable_ecr_push_role` mặc định `false`. Khi cần CI, đăng ký GitHub OIDC provider
`https://token.actions.githubusercontent.com` với audience `sts.amazonaws.com`
trong đúng AWS account trước; Terraform hiện chỉ tạo role và policy, không tạo provider.
Đặt `enable_ecr_push_role = true` và điền `github_oidc_subjects` bằng các `sub`
claim chính xác của repo/job. Ví dụ dạng truyền thống cho nhánh main:
`repo:YOUR_ORG/YOUR_REPO:ref:refs/heads/main`. Job dùng environment hoặc repo dùng
immutable subject claims có định dạng khác. Cấu hình từ chối subject rỗng/wildcard
khi bật role. Role chỉ có quyền push vào các ECR repository của dự án và không cấp
quyền deploy Kubernetes. ARN sau apply: `terraform -chdir=terraform output iam_ecr_push_role_arn`.

Nguồn: [AWS GitHub OIDC trust](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html),
[GitHub OIDC subject formats](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

## RDS và chi phí

Các biến `db_*` áp dụng cho cả PostgreSQL và MySQL:

| Biến | Hành vi và chi phí |
| --- | --- |
| `db_instance_class` | Loại máy cho mỗi DB; tính phí instance theo thời gian chạy. Hiện Single-AZ. |
| `db_allocated_storage = 20` | 20 GiB gp3 cho mỗi DB, tổng 40 GiB provisioned. Storage autoscaling đang tắt. |
| `db_backup_retention_days = 1` | Bật automated backups/PITR với thời gian giữ một ngày; 0 tắt automated backup. Giữ lâu hơn có thể tăng backup storage. |
| `db_deletion_protection = false` | Cho phép xóa DB. Bật true chặn xóa đến khi tắt lại; không có phí riêng cho cờ này, nhưng DB còn tồn tại vẫn chịu phí. |
| `db_create_final_snapshot = false` | Khi xóa DB, không yêu cầu final snapshot. Nếu true, snapshot còn lại có thể tiếp tục chịu phí storage đến khi được xóa. |

Backup RDS lưu trong Amazon S3 do RDS quản lý, không phải bucket Terraform state
và không phải bucket bạn tự cấu hình. Xem/restore qua RDS Backups/Snapshots.
Automated backup bao gồm snapshot instance và transaction logs để phục hồi theo
thời điểm; không phải SQL dump riêng từng database. Trong cùng account/region,
AWS có allowance backup storage bằng 100% tổng provisioned DB storage; phần vượt
allowance chịu phí. Không thể kết luận retention một ngày luôn miễn phí.
Final/manual snapshots tồn tại độc lập với DB; code hiện không yêu cầu giữ lại
automated backups khi xóa instance. Snapshot cuối dùng tên cố định `*-postgres-final`
và `*-mysql-final`: trước lần xóa tiếp theo phải tránh trùng snapshot đã tồn tại.

Nguồn: [AWS RDS backups và storage allowance](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html).

Các nguồn chi phí khác gồm EKS control plane, EC2/EBS của nodes, NAT Gateway
(thời gian tồn tại và lưu lượng), public IPv4, ECR storage/scanning tùy cấu hình,
SQS requests, Secrets Manager cho RDS master secrets, CloudWatch logs và S3 state.
Karpenter tạo thêm EC2/EBS sau khi triển khai cũng làm tăng chi phí ngoài số seed nodes.
Budget là cảnh báo chi phí, không tự dừng hoặc giới hạn tài nguyên ở 100 USD.
RDS `db.t4g.micro` dùng Unlimited mode: tải CPU kéo dài vượt baseline có thể
phát sinh phí CPU credits ngoài phí instance.

Nguồn giá: [EKS](https://aws.amazon.com/eks/pricing/),
[NAT và IPv4](https://aws.amazon.com/vpc/pricing/),
[RDS T4g CPU credits](https://aws.amazon.com/rds/instance-types/).

## Seed managed node group

`node_instance_types` chọn loại EC2; `node_group_min_size` và `node_group_max_size`
là biên số node; `node_group_desired_size` là số node mong muốn lúc tạo group.
Với min=1/max=3/desired=2, group ban đầu duy trì hai node, không tự scale theo
Pod Pending chỉ vì max=3. Repo không cài Cluster Autoscaler cho group này.
Karpenter quản lý nhóm node khác theo NodePool, không tự tăng seed group.
`ignore_changes` đang bỏ qua thay đổi desired size sau khi tạo: sửa desired trong
tfvars không bảo đảm resize group qua apply; dùng quy trình resize EKS riêng.

Nodes này có label `role=system`. Values Kubernetes hiện đặt controllers,
monitoring và các API/backend trên nhóm đó. Hai `t3.small` cần được kiểm tra
CPU/RAM và giới hạn Pod trước khi xem là đủ cho toàn bộ workload.

Nguồn: [EKS scaling configuration](https://docs.aws.amazon.com/eks/latest/APIReference/API_NodegroupScalingConfig.html).

Biến mật khẩu Grafana đã được gỡ khỏi Terraform; monitoring dùng Kubernetes
Secret ở bước triển khai cluster. `removed.tf` vẫn giữ địa chỉ module observability
cũ với `destroy=false` để chuyển state an toàn; đây không phải cấu hình cài monitoring.
