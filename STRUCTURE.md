# Cấu trúc Repo Hạ tầng – Two‑Level Autoscaling on EKS

> **Bản phác thảo lịch sử, không dùng để triển khai.** Cây thư mục và nội dung bên dưới phản ánh thiết kế cũ (IRSA/OIDC của EKS, Redis, DynamoDB lock, v.v.) và không khớp Terraform hiện tại. Nguồn hiện hành là [`terraform/`](./terraform/) và [PROJECT_DECISIONS.md](../project-documentation/01-official-reports/PROJECT_DECISIONS.md). Quyết định IAM hiện tại: **EKS Pod Identity** cho ứng dụng, KEDA và Karpenter; không tạo EKS OIDC provider cho IRSA. GitHub Actions OIDC là cơ chế CI/CD riêng.

Tài liệu này giải thích **từng thư mục và tệp** trong repo, mục đích, và nội dung cần có bên trong.

---

## Sơ đồ tổng thể

```text
eks-twolevel-autoscaling/
├── .github/
│   └── workflows/                     # CI/CD pipelines (GitHub Actions)
├── terraform/
│   ├── backend.tf                     # Cấu hình remote state (S3 + DynamoDB)
│   ├── main.tf                        # Entry point gọi các module
│   ├── variables.tf                   # Khai báo biến toàn cục
│   ├── outputs.tf                     # Output sau khi apply (cluster endpoint, v.v.)
│   ├── providers.tf                   # Khai báo providers (AWS, Kubernetes, Helm)
│   ├── locals.tf                      # Biến nội bộ (tên chuẩn hóa, tag chung)
│   ├── terraform.tfvars               # Giá trị biến thực tế (KHÔNG commit secret)
│   ├── terraform.tfvars.example       # Mẫu để developer copy
│   ├── modules/                       # Các module tái sử dụng
│   │   ├── networking/                # VPC, Subnet, Route, NAT, IGW
│   │   ├── eks/                       # EKS cluster, node groups, IRSA
│   │   ├── karpenter/                 # Cài Karpenter qua Helm + IAM
│   │   ├── keda/                      # Cài KEDA qua Helm
│   │   ├── observability/             # Prometheus, Grafana, Alertmanager
│   │   ├── databases/                 # RDS PostgreSQL + Redis ElastiCache
│   │   ├── ecr/                       # ECR repositories cho mỗi service
│   │   ├── sqs/                       # SQS queues cho các worker
│   │   └── iam/                       # IAM roles, policies dùng chung
├── kubernetes/                        # Manifest K8s (không được tạo qua Terraform)
│   ├── namespaces/                    # Namespace definitions
│   ├── karpenter/                     # NodePool, EC2NodeClass
│   ├── keda/                          # ScaledObject, TriggerAuthentication
│   ├── monitoring/                    # Prometheus, Grafana, ServiceMonitor
│   ├── apps/                          # Kustomize overlay cho backend services
│   └── network-policies/              # NetworkPolicy giới hạn traffic
├── observability/
│   ├── dashboards/                    # Grafana dashboard JSON
│   └── alerts/                        # Prometheus alerting rules YAML
├── load-testing/
│   ├── scenarios/                     # k6 scripts (baseline, spike, soak, stress)
│   └── results/                       # Kết quả test (gitignore phần lớn)
├── scripts/                           # Shell scripts tiện ích
├── assets/                            # Hình ảnh, sơ đồ cho README
├── docs/                              # Tài liệu kỹ thuật chi tiết
├── .gitignore
├── README.md
└── STRUCTURE.md                       # File này
```

---

## Chi tiết từng thành phần

### `.github/workflows/`
Chứa các pipeline CI/CD tự động hoá quy trình Terraform và load test.

| File | Nội dung cần có |
|------|----------------|
| `terraform-plan.yml` | Trigger trên PR: chạy `terraform fmt`, `terraform validate`, `terraform plan`. Comment kết quả vào PR. |
| `terraform-apply.yml` | Trigger khi merge vào `main`: chạy `terraform apply -auto-approve`. Chỉ áp dụng cho môi trường tương ứng (dev/staging/prod). |
| `load-test.yml` | Trigger thủ công hoặc theo lịch: chạy k6 script đã chọn, lưu kết quả vào artifact. |
| `destroy.yml` | Trigger thủ công (workflow_dispatch): chạy `terraform destroy` cho môi trường chỉ định. Có bước xác nhận. |

---

### `terraform/`

#### `terraform/backend.tf`
Khai báo **remote state backend** để nhiều người và CI dùng chung state.
```
- type: s3
- bucket: tên bucket S3 (ví dụ: "uitm-tfstate-eks")
- key: "eks-twolevel/terraform.tfstate"
- region: us-east-1 (hoặc ap-southeast-1)
- dynamodb_table: tên bảng lock (ví dụ: "uitm-tfstate-lock")
- encrypt: true
```

#### `terraform/providers.tf`
Khai báo các Terraform providers cần thiết với version constraint:
```
- hashicorp/aws   ~> 5.x
- hashicorp/kubernetes ~> 2.x
- hashicorp/helm  ~> 2.x
- gavinbunney/kubectl (optional – apply manifest phức tạp)
```

#### `terraform/main.tf`
Entry point. Gọi lần lượt các module:
```
module "networking" { source = "./modules/networking" ... }
module "eks"        { source = "./modules/eks"        ... }
module "karpenter"  { source = "./modules/karpenter"  ... }
module "keda"       { source = "./modules/keda"        ... }
module "observability" { source = "./modules/observability" ... }
module "databases"  { source = "./modules/databases"   ... }
module "ecr"        { source = "./modules/ecr"         ... }
module "sqs"        { source = "./modules/sqs"         ... }
module "iam"        { source = "./modules/iam"         ... }
```

#### `terraform/variables.tf`
Khai báo tất cả biến đầu vào, kèm `description` và `default` (nếu có):
- `aws_region` – vùng AWS (ap-southeast-1)
- `cluster_name` – tên EKS cluster
- `cluster_version` – phiên bản Kubernetes (1.29)
- `environment` – dev / staging / prod
- `vpc_cidr` – CIDR của VPC
- `availability_zones` – danh sách AZ
- `db_instance_class` – loại RDS instance
- `karpenter_version`, `keda_version` – version Helm chart
- `ecr_repo_names` – danh sách tên ECR repo (cart, catalog, v.v.)
- `sqs_queue_names` – tên các queue

#### `terraform/outputs.tf`
Export các giá trị quan trọng sau khi apply:
- `cluster_endpoint`, `cluster_name`, `cluster_oidc_issuer_url`
- `vpc_id`, `private_subnet_ids`
- `rds_endpoint`, `redis_endpoint`
- `ecr_repo_urls` – map service → URL
- `sqs_queue_urls` – map queue name → URL

#### `terraform/locals.tf`
Biến nội bộ dùng trong nhiều module:
- `common_tags` – `{ Project, Environment, ManagedBy="Terraform" }`
- `name_prefix` – `"${var.cluster_name}-${var.environment}"`

#### `terraform/terraform.tfvars.example`
Mẫu giá trị biến, developer copy thành `terraform.tfvars` rồi điền:
```hcl
aws_region   = "ap-southeast-1"
cluster_name = "uitm-eks"
environment  = "dev"
vpc_cidr     = "10.0.0.0/16"
...
```

---

### `terraform/modules/networking/`
Tạo toàn bộ hạ tầng mạng.

| File | Nội dung |
|------|---------|
| `main.tf` | `aws_vpc`, `aws_subnet` (public + private × số AZ), `aws_internet_gateway`, `aws_nat_gateway`, `aws_eip`, `aws_route_table`, `aws_route_table_association` |
| `variables.tf` | `vpc_cidr`, `availability_zones`, `cluster_name`, `environment`, `common_tags` |
| `outputs.tf` | `vpc_id`, `public_subnet_ids`, `private_subnet_ids` |
| `versions.tf` | `required_providers { aws ~> 5.x }` |

> **Lưu ý tag bắt buộc trên subnet:**
> - Public subnet: `kubernetes.io/role/elb = 1`
> - Private subnet: `kubernetes.io/role/internal-elb = 1`, `karpenter.sh/discovery = cluster_name`

---

### `terraform/modules/eks/`
Tạo EKS cluster, managed node group seed (để Karpenter chạy được), và cấu hình IRSA.

| File | Nội dung |
|------|---------|
| `main.tf` | `aws_eks_cluster`, `aws_eks_node_group` (minimal – 1-2 node cho system workloads), OIDC provider, `aws_eks_addon` (vpc-cni, coredns, kube-proxy) |
| `variables.tf` | `cluster_name`, `cluster_version`, `vpc_id`, `subnet_ids`, `common_tags` |
| `outputs.tf` | `cluster_endpoint`, `cluster_ca_certificate`, `cluster_oidc_issuer_url`, `cluster_name` |
| `versions.tf` | `required_providers { aws, kubernetes, tls }` |

---

### `terraform/modules/karpenter/`
Cài Karpenter bằng Helm và tạo các IAM resources cần thiết.

| File | Nội dung |
|------|---------|
| `main.tf` | Helm release `karpenter`, `aws_iam_role` (cho Karpenter controller dùng IRSA), `aws_iam_instance_profile` (cho EC2 nodes), `aws_sqs_queue` (interruption queue), `aws_cloudwatch_event_rule` (Spot interruption events) |
| `variables.tf` | `cluster_name`, `cluster_endpoint`, `oidc_provider_arn`, `karpenter_version`, `karpenter_namespace`, `node_iam_role_name` |
| `outputs.tf` | `karpenter_role_arn`, `node_instance_profile_name` |
| `versions.tf` | `required_providers { aws, helm }` |

---

### `terraform/modules/keda/`
Cài KEDA bằng Helm.

| File | Nội dung |
|------|---------|
| `main.tf` | Helm release `keda` vào namespace `keda`, `aws_iam_role` (cho KEDA operator IRSA – cần đọc SQS metrics từ CloudWatch) |
| `variables.tf` | `keda_version`, `keda_namespace`, `oidc_provider_arn`, `cluster_name` |
| `outputs.tf` | `keda_operator_role_arn` |
| `versions.tf` | `required_providers { aws, helm }` |

---

### `terraform/modules/observability/`
Cài stack quan trắc.

| File | Nội dung |
|------|---------|
| `main.tf` | Helm release `kube-prometheus-stack` (Prometheus Operator + Grafana + Alertmanager), `helm_release "loki"` (log aggregation, optional), tạo `aws_cloudwatch_log_group` cho container logs |
| `variables.tf` | `monitoring_namespace`, `grafana_admin_password`, `prometheus_retention_days`, `cluster_name` |
| `outputs.tf` | `grafana_service_name`, `prometheus_endpoint` |
| `versions.tf` | `required_providers { aws, helm, kubernetes }` |

---

### `terraform/modules/databases/`
Tạo RDS và Redis.

| File | Nội dung |
|------|---------|
| `main.tf` | `aws_db_instance` (PostgreSQL cho orders/catalog), `aws_elasticache_cluster` (Redis cho cart session), `aws_db_subnet_group`, `aws_elasticache_subnet_group`, security groups, `aws_secretsmanager_secret` (lưu credentials) |
| `variables.tf` | `vpc_id`, `private_subnet_ids`, `db_instance_class`, `db_name`, `db_username`, `db_password`, `redis_node_type`, `environment`, `common_tags` |
| `outputs.tf` | `rds_endpoint`, `rds_port`, `redis_endpoint`, `redis_port`, `db_secret_arn` |
| `versions.tf` | `required_providers { aws }` |

---

### `terraform/modules/ecr/`
Tạo ECR repositories cho mỗi microservice.

| File | Nội dung |
|------|---------|
| `main.tf` | `aws_ecr_repository` (cho từng service: ui, catalog, cart, orders, checkout, recommendations), `aws_ecr_lifecycle_policy` (giữ 10 image gần nhất), `aws_ecr_repository_policy` (cho phép EKS node pull) |
| `variables.tf` | `repo_names` (list of string), `environment`, `common_tags` |
| `outputs.tf` | `repository_urls` (map: tên → URL) |
| `versions.tf` | `required_providers { aws }` |

---

### `terraform/modules/sqs/`
Tạo SQS queues dùng cho KEDA trigger.

| File | Nội dung |
|------|---------|
| `main.tf` | `aws_sqs_queue` (standard queue cho mỗi worker: cart-queue, orders-queue, checkout-queue), `aws_sqs_queue_policy` (cho phép producer gửi message, worker đọc), Dead Letter Queue (DLQ) cho mỗi queue chính |
| `variables.tf` | `queue_names`, `visibility_timeout`, `message_retention_seconds`, `environment`, `common_tags` |
| `outputs.tf` | `queue_urls` (map), `queue_arns` (map) |
| `versions.tf` | `required_providers { aws }` |

---

### `terraform/modules/iam/`
Tạo IAM roles cho các ServiceAccount của backend (IRSA).

| File | Nội dung |
|------|---------|
| `main.tf` | `aws_iam_role` + `aws_iam_role_policy` cho từng service: `cart-sa` (read/write SQS cart-queue, Redis), `orders-sa` (read SQS orders-queue, write RDS), `catalog-sa` (read RDS), `checkout-sa` (publish SQS, write orders-queue). Chính sách trust OIDC của EKS cluster. |
| `variables.tf` | `oidc_provider_arn`, `cluster_name`, `namespace`, `service_accounts` (map: name → permissions), `sqs_queue_arns`, `db_secret_arn` |
| `outputs.tf` | `service_account_role_arns` (map: service → IAM role ARN) |
| `versions.tf` | `required_providers { aws }` |

---

### `terraform/environments/`
Mỗi môi trường là một Terraform root module **độc lập**, gọi lại các module trong `modules/`.

| File | Nội dung |
|------|---------|
| `backend.tf` | Khởi tạo backend S3 với `key` riêng của môi trường (e.g. `"eks-twolevel/dev/terraform.tfstate"`) |
| `main.tf` | Gọi các module trong `../../modules/` với biến phù hợp môi trường |
| `variables.tf` | Khai báo lại các biến cần nhận từ tfvars |
| `terraform.tfvars` | Giá trị thực tế cho môi trường (region, instance size, v.v.) – **KHÔNG commit secret** |
| `outputs.tf` | Tổng hợp output từ các module |

> `dev` – cluster nhỏ, spot instance, single-AZ để tiết kiệm  
> `staging` – gần giống prod, dùng để kiểm thử end-to-end  
> `prod` – multi-AZ, reserved/spot mix, strict security groups

---

### `kubernetes/`
Chứa các manifest Kubernetes **không** được quản lý bởi Terraform (được apply bằng `kubectl` hoặc `kustomize`).

#### `kubernetes/namespaces/`
| File | Nội dung |
|------|---------|
| `retailstore.yaml` | `Namespace` tên `retailstore` với labels `istio-injection: enabled` (nếu dùng Istio) |
| `monitoring.yaml` | `Namespace` tên `monitoring` |
| `keda.yaml` | `Namespace` tên `keda` |
| `karpenter.yaml` | `Namespace` tên `karpenter` |

#### `kubernetes/karpenter/`
| File | Nội dung |
|------|---------|
| `node-pool.yaml` | `NodePool` CRD – định nghĩa loại instance (Spot, arm64/amd64), giới hạn tổng CPU/memory, TTL node rỗng. |
| `ec2-node-class.yaml` | `EC2NodeClass` CRD – AMI family (AL2023), subnetSelector (tag Karpenter discovery), securityGroupSelector, instanceProfile. |

#### `kubernetes/keda/`
| File | Nội dung |
|------|---------|
| `keda-operator.yaml` | Patch cấu hình cho KEDA operator nếu cần override (thường Helm đủ). |
| `trigger-auth.yaml` | `TriggerAuthentication` dùng IRSA (annotate ServiceAccount để KEDA dùng role AWS truy cập SQS metrics). |
| `scaled-object-cart.yaml` | `ScaledObject` cho service cart: target `cart-deployment`, trigger `aws-sqs-queue`, `queueURL`, `queueLength=5` (5 message/pod), `minReplicaCount=0`, `maxReplicaCount=20`. |
| `scaled-object-checkout.yaml` | Tương tự cho checkout service. |
| `scaled-object-orders.yaml` | Tương tự cho orders service. |

#### `kubernetes/monitoring/`
| File | Nội dung |
|------|---------|
| `prometheus-operator.yaml` | `PrometheusRule` cho các custom alert (nếu không đặt trong `observability/alerts/`). |
| `grafana.yaml` | `GrafanaDashboard` CRD (nếu dùng Grafana Operator) hoặc ConfigMap chứa dashboard JSON. |
| `alertmanager.yaml` | `AlertmanagerConfig` – route alert tới Slack/email/PagerDuty. |
| `service-monitors.yaml` | `ServiceMonitor` cho mỗi backend service (cart, orders, checkout…) – Prometheus scrape `/actuator/prometheus` hoặc `/metrics`. |

#### `kubernetes/apps/`
| File | Nội dung |
|------|---------|
| `kustomization.yaml` | Kustomize `base` hoặc `overlay` trỏ tới Helm chart của backend (từ `retailstore-backend-microservices`). Dùng để patch image tag, resource limits, và ServiceAccount theo môi trường. |

#### `kubernetes/network-policies/`
| File | Nội dung |
|------|---------|
| `default-deny.yaml` | `NetworkPolicy` deny-all ingress/egress trong namespace `retailstore` – baseline security. |
| `allow-intra-namespace.yaml` | `NetworkPolicy` cho phép traffic trong cùng namespace (giữa các service với nhau). Có thể thêm rule cho phép từ `monitoring` namespace scrape metrics. |

---

### `observability/`

#### `observability/dashboards/`
| File | Nội dung |
|------|---------|
| `autoscaling-overview.json` | Grafana dashboard tổng hợp: số pod mỗi service theo thời gian, số node, queue depth SQS, lag KEDA. |
| `keda-metrics.json` | Dashboard riêng KEDA: `keda_scaler_metrics_value`, `keda_scaler_active`, replicaCount mỗi ScaledObject. |
| `karpenter-nodes.json` | Dashboard Karpenter: node provisioned/deprovisioned, interruption count, Spot vs On-Demand ratio. |
| `application-latency.json` | Dashboard backend: p50/p95/p99 latency, error rate, throughput (request/s). |

#### `observability/alerts/`
| File | Nội dung |
|------|---------|
| `scaling-alerts.yaml` | `PrometheusRule` – cảnh báo khi pod không scale kịp (queue depth > ngưỡng, không có node sẵn). |
| `pod-alerts.yaml` | Cảnh báo pod crash-loop, OOMKilled, restart nhiều. |
| `node-alerts.yaml` | Cảnh báo node NotReady, Spot interruption rate cao, CPU/Memory node > 85%. |

---

### `load-testing/`

#### `load-testing/scenarios/`
| File | Nội dung |
|------|---------|
| `baseline.js` | k6 script – mô phỏng traffic bình thường (~50 VU, 5 phút). Đo latency baseline khi autoscaling chưa bị trigger. |
| `spike.js` | k6 script – tăng đột ngột từ 0 → 500 VU trong 30 giây. Quan sát KEDA scale up nhanh thế nào. |
| `soak.js` | k6 script – giữ 200 VU trong 30-60 phút. Kiểm tra memory leak, node stability. |
| `stress.js` | k6 script – tăng dần đến khi hệ thống đạt giới hạn. Tìm điểm nghẽn. |

#### `load-testing/results/`
Thư mục chứa kết quả chạy k6 (HTML report, JSON raw). Thêm vào `.gitignore` ngoại trừ file tóm tắt.

---

### `scripts/`
| File | Nội dung |
|------|---------|
| `bootstrap.sh` | Chạy một lần đầu: tạo S3 bucket và DynamoDB table cho remote state, sau đó `terraform init`. |
| `build-push-images.sh` | Login ECR, build Docker image mỗi service (tham số: `$SERVICE`, `$TAG`), push lên ECR. |
| `deploy.sh` | Chạy `terraform apply` cho môi trường chỉ định + `kubectl apply -k kubernetes/` + `helmfile sync`. |
| `destroy.sh` | Chạy `terraform destroy` (yêu cầu xác nhận) sau khi xóa workload (để tránh resource leak). |
| `port-forward.sh` | Port-forward Grafana, Prometheus, và các service backend ra localhost để debug nhanh. |

---

### `docs/`
| File | Nội dung |
|------|---------|
| `SETUP.md` | Hướng dẫn cài công cụ (terraform, kubectl, helm, k6), cấu hình AWS credentials, clone repo. |
| `DEPLOYMENT.md` | Quy trình deploy từ đầu: bootstrap → VPC → EKS → Karpenter/KEDA → DB → Backend → Validate. |
| `AUTOSCALING.md` | Giải thích thiết kế 2-cấp: KEDA ScaledObject, Karpenter NodePool, cách chúng phối hợp. |
| `OBSERVABILITY.md` | Cách truy cập Grafana, load dashboard, đọc alert, cấu hình Alertmanager webhook. |
| `TROUBLESHOOTING.md` | Các lỗi thường gặp và cách xử lý: pod Pending, KEDA không trigger, Karpenter không provision node, v.v. |

---

## Nguyên tắc chung

1. **Không commit secret** – Dùng AWS Secrets Manager / SSM Parameter Store / `terraform.tfvars` (gitignore).
2. **Mọi resource đều có `common_tags`** – Giúp quản lý chi phí và tìm kiếm trên AWS Console.
3. **Module = tái sử dụng** – Mỗi module có `variables.tf` + `outputs.tf` rõ ràng, không hardcode.
4. **Environment isolation** – `dev`, `staging`, `prod` là 3 Terraform root riêng, state riêng.
5. **Kubernetes manifest tách khỏi Terraform** – Terraform chỉ tạo cluster và cài Helm, còn business config (ScaledObject, NetworkPolicy) trong `kubernetes/` và apply bằng kubectl/kustomize.
