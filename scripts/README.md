# Lệnh triển khai EKS dev

Dùng **Git Bash**, chạy từng nhóm lệnh theo thứ tự. Không cần chạy file `.sh`;
chúng lưu cùng các bước để dùng khi đã quen. Lệnh thay đổi cluster thực thi ngay.
Chỉ chuyển sang bước tiếp theo khi bước hiện tại thành công.

Các lệnh dưới đây bắt đầu sau khi Terraform apply thành công. Cần AWS CLI,
Terraform, Helm và kubectl. Hai repo nằm cạnh nhau trong `D:/WorkSpace/UITMagnolia`.

## 1. Xác thực và xem thông tin hạ tầng

```bash
# Chọn repo hạ tầng.
cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling

# Xác nhận đúng account AWS.
aws sts get-caller-identity

# Đối chiếu endpoint, queue, role và registry với values dev.
terraform -chdir=terraform output platform_contract
terraform -chdir=terraform output ecr_repository_urls
terraform -chdir=terraform output sqs_queue_urls
terraform -chdir=terraform output postgres_endpoint
terraform -chdir=terraform output mysql_endpoint
```

Cập nhật các file `kubernetes/environments/dev/` theo output thực tế, gồm
`karpenter.yaml`, `platform.yaml`, `autoscaling.yaml` và `apps/*.yaml`.
AMI alias phải được pin theo bản đã kiểm thử; các lệnh tra cứu có trong
[02-get-ami-alias.sh](02-get-ami-alias.sh).

## 2. Kết nối cluster và bootstrap

```bash
# Tạo context kết nối cluster.
aws eks update-kubeconfig --region us-east-1 --name twolevel-autoscaling-dev --alias twolevel-dev
kubectl config use-context twolevel-dev

# Chờ system node sẵn sàng.
kubectl --context twolevel-dev get nodes -l role=system
kubectl --context twolevel-dev wait --for=condition=Ready nodes -l role=system --timeout=900s

# Tạo namespace trước ServiceAccount.
kubectl --context twolevel-dev apply -k kubernetes/namespaces
kubectl --context twolevel-dev apply -k kubernetes/apps

# Kiểm tra namespace và danh tính workload.
kubectl --context twolevel-dev get namespaces
kubectl --context twolevel-dev -n retailstore get serviceaccounts
```

## 3. Chuẩn bị database và image

Đã khởi tạo RDS thì bỏ qua SQL setup. SQL verify và đặt mật khẩu user được thực
hiện riêng trong DBeaver; không lưu password vào script hoặc Git. Các lệnh tạo
schema/table nằm trong thư mục `database/` của repo backend.

Nếu cần mở lại RDS bằng DBeaver, dùng hai terminal riêng. Thay `INSTANCE_ID`
bằng EC2 node đang Online trong Systems Manager. Giữ terminal mở khi dùng DBeaver.

```bash
# Terminal riêng: tunnel PostgreSQL, local port 15432.
aws ssm start-session --region us-east-1 --target INSTANCE_ID --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters "host=twolevel-autoscaling-dev-postgres.ceb0a0oo6thh.us-east-1.rds.amazonaws.com,portNumber=5432,localPortNumber=15432"
```

```bash
# Terminal riêng khác: tunnel MySQL, local port 13306.
aws ssm start-session --region us-east-1 --target INSTANCE_ID --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters "host=twolevel-autoscaling-dev-mysql.ceb0a0oo6thh.us-east-1.rds.amazonaws.com,portNumber=3306,localPortNumber=13306"
```

Nếu image mới đã push thành công thì bỏ qua build. Nếu chưa, chạy trong repo backend:

```bash
cd /d/WorkSpace/UITMagnolia/retailstore-backend-microservices
bash -e -o pipefail build-push-images.sh
cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling
```

Script build/push dùng account dev, region `us-east-1`, tag `latest` và gồm cả UI.

## 4. Apply credentials từ file local

Điền đủ credentials trong hai file đã gitignore trước khi chạy:

- `kubernetes/environments/dev/secrets/database-secrets.local.yaml`
- `kubernetes/environments/dev/secrets/grafana-admin.local.yaml`

File example chỉ chứa mẫu. Không điền mật khẩu thật vào example. Cách điền:
[hướng dẫn Secret](../docs/INTEGRATION.md#61-tạo-năm-secret-bằng-một-file).

```bash
# Kiểm tra namespace đích.
kubectl --context twolevel-dev get namespace retailstore monitoring

# Kiểm tra manifest, chưa lưu Secret. Dừng nếu có lỗi.
kubectl --context twolevel-dev apply --dry-run=server -f kubernetes/environments/dev/secrets/database-secrets.local.yaml
kubectl --context twolevel-dev apply --dry-run=server -f kubernetes/environments/dev/secrets/grafana-admin.local.yaml

# Lưu năm DB Secret và Secret đăng nhập Grafana.
kubectl --context twolevel-dev apply -f kubernetes/environments/dev/secrets/database-secrets.local.yaml
kubectl --context twolevel-dev apply -f kubernetes/environments/dev/secrets/grafana-admin.local.yaml

# Chỉ xem metadata, không in giá trị credentials.
kubectl --context twolevel-dev -n retailstore get secret cart-db orders-db checkout-db catalog-db recommendations-db
kubectl --context twolevel-dev -n monitoring get secret grafana-admin
```

## 5. Tạo ConfigMap CA cho RDS

Thay đường dẫn CA nếu file nằm ở vị trí khác. Lệnh `create --dry-run=client` chỉ
sinh manifest; lệnh `apply` sau dấu `|` mới lưu ConfigMap vào cluster.

```bash
# Nạp public CA bundle vào ConfigMap dùng chung cho backend.
kubectl --context twolevel-dev -n retailstore create configmap rds-ca \
  --from-file=global-bundle.pem='C:/Users/hdatuan/Downloads/global-bundle.pem' \
  --dry-run=client -o yaml | kubectl --context twolevel-dev apply -f -

# Xác nhận ConfigMap tồn tại.
kubectl --context twolevel-dev -n retailstore get configmap rds-ca
```

Script Python có kiểm tra PEM vẫn có thể dùng thay thế:
[02-create-rds-ca-configmap.py](02-create-rds-ca-configmap.py). Chỉ chọn một cách.
Pod dùng endpoint RDS trực tiếp và cổng 5432/3306, không dùng tunnel DBeaver.

## 6. Cài monitoring

```bash
# Kiểm tra credentials Grafana.
kubectl --context twolevel-dev -n monitoring get secret grafana-admin

# Cài Prometheus Operator, Prometheus và Grafana.
helm upgrade --install monitoring kube-prometheus-stack \
  --repo https://prometheus-community.github.io/helm-charts \
  --version 92.7.0 --namespace monitoring --kube-context twolevel-dev \
  -f kubernetes/platform/monitoring/values.yaml --wait --timeout 900s

# Chờ ServiceMonitor CRD trước các chart sử dụng monitoring.
kubectl --context twolevel-dev wait --for=condition=Established crd/servicemonitors.monitoring.coreos.com --timeout=900s
kubectl --context twolevel-dev -n monitoring get pods

# Nạp dashboard cho Grafana sidecar.
kubectl --context twolevel-dev -n monitoring create configmap autoscaling-dashboard \
  --from-file=observability/dashboards/autoscaling-overview.json \
  --dry-run=client -o yaml | kubectl --context twolevel-dev apply -f -
kubectl --context twolevel-dev -n monitoring label configmap autoscaling-dashboard grafana_dashboard=1 --overwrite
```

Mở Grafana trong terminal riêng; giữ lệnh chạy rồi truy cập `http://localhost:3000`.
Đăng nhập bằng credentials trong Secret `grafana-admin`. Ctrl+C để đóng tunnel.

```bash
kubectl --context twolevel-dev -n monitoring port-forward --address 127.0.0.1 service/monitoring-grafana 3000:80
```

## 7. Cài Metrics Server, Karpenter và KEDA

Bước này chưa tạo NodePool, ScaledObject hay HPA. Nếu Karpenter và KEDA đã được
cài, chỉ cần chạy các lệnh Metrics Server bên dưới; không cần cài lại controller.

```bash
# Render để kiểm tra values trước khi thay đổi cluster.
helm template platform-config kubernetes/charts/platform-config -f kubernetes/environments/dev/platform.yaml > /dev/null

# Cài Metrics Server trong kube-system để cung cấp CPU/memory metrics cho HPA.
helm upgrade --install metrics-server metrics-server --repo https://kubernetes-sigs.github.io/metrics-server/ \
  --version 3.14.0 --namespace kube-system --kube-context twolevel-dev \
  -f kubernetes/platform/metrics-server/values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=120s

# Kiểm tra rollout và số liệu CPU/memory. Metrics có thể cần ít phút để xuất hiện.
kubectl --context twolevel-dev -n kube-system rollout status deployment/metrics-server --timeout=900s
kubectl --context twolevel-dev top nodes
kubectl --context twolevel-dev -n retailstore top pods

# Cài Karpenter CRDs trước controller.
helm upgrade --install karpenter-crd oci://public.ecr.aws/karpenter/karpenter-crd \
  --version 1.15.0 --namespace karpenter --kube-context twolevel-dev --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Established crd/ec2nodeclasses.karpenter.k8s.aws crd/nodepools.karpenter.sh --timeout=900s

# Cài controller với cluster endpoint, queue và IAM đã chuẩn bị.
helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --version 1.15.0 --namespace karpenter --kube-context twolevel-dev --skip-crds \
  -f kubernetes/platform/karpenter/values.yaml \
  -f kubernetes/environments/dev/karpenter.yaml --wait --timeout 900s

# Cài KEDA và chờ CRDs của scaler.
helm upgrade --install keda keda --repo https://kedacore.github.io/charts \
  --version 2.21.0 --namespace keda --kube-context twolevel-dev \
  -f kubernetes/platform/keda/values.yaml --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Established crd/scaledobjects.keda.sh crd/clustertriggerauthentications.keda.sh --timeout=900s


```

## 8. Deploy backend theo từng service

Ban đầu mỗi worker có một replica cố định và có thể chạy trên system node nếu còn đủ tài nguyên.

```bash
# Kiểm tra credentials và CA trước khi deploy.
kubectl --context twolevel-dev -n retailstore get configmap rds-ca
kubectl --context twolevel-dev -n retailstore get secret cart-db orders-db checkout-db catalog-db recommendations-db

# Catalog: xác nhận kết nối MySQL trước.
helm upgrade --install catalog ../retailstore-backend-microservices/src/catalog/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/catalog.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/catalog --timeout=900s

# Recommendations: đọc chung dữ liệu Catalog.
helm upgrade --install recommendations ../retailstore-backend-microservices/src/recommendations/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/recommendations.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/recommendations --timeout=900s

# Cart: API và worker dùng schema cart.
helm upgrade --install cart ../retailstore-backend-microservices/src/cart/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/cart.yaml --wait --timeout 900s

# Orders: API và worker dùng schema orders.
helm upgrade --install orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/orders.yaml --wait --timeout 900s

# Checkout: API và worker dùng schema checkout.
helm upgrade --install checkout ../retailstore-backend-microservices/src/checkout/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/checkout.yaml --wait --timeout 900s

# Xác nhận năm release và tám Deployment.
helm list --kube-context twolevel-dev --namespace retailstore
kubectl --context twolevel-dev -n retailstore get deployments,pods,services
```

## 9. Bật KEDA cho worker

Sau khi quan sát app, tạo xác thực SQS và chuyển ba chart sang KEDA. Việc chuyển
quyền quản lý replicas có thể làm số pod thay đổi tạm thời; theo dõi rollout.

```bash
# Tạo auth, chưa tạo NodePool; chỉ chạy nếu release chưa tồn tại.
helm install platform-config kubernetes/charts/platform-config \
  --namespace karpenter --kube-context twolevel-dev \
  -f kubernetes/environments/dev/platform.yaml --set nodePool.enabled=false --wait --timeout 900s

# Chuyển quyền quản lý replica sang KEDA.
helm upgrade cart ../retailstore-backend-microservices/src/cart/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/cart.yaml -f kubernetes/environments/dev/apps/worker-keda.yaml --wait --timeout 900s
helm upgrade orders ../retailstore-backend-microservices/src/orders/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/orders.yaml -f kubernetes/environments/dev/apps/worker-keda.yaml --wait --timeout 900s
helm upgrade checkout ../retailstore-backend-microservices/src/checkout/chart \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/apps/checkout.yaml -f kubernetes/environments/dev/apps/worker-keda.yaml --wait --timeout 900s

# Tạo ScaledObject theo SQS.
kubectl --context twolevel-dev get clustertriggerauthentication keda-sqs-pod-identity
helm upgrade --install worker-scaling kubernetes/charts/worker-scaling \
  --namespace retailstore --kube-context twolevel-dev \
  -f kubernetes/environments/dev/autoscaling.yaml --wait --timeout 900s
kubectl --context twolevel-dev -n retailstore wait --for=condition=Ready \
  scaledobject/carts-worker-sqs scaledobject/orders-worker-sqs scaledobject/checkout-worker-sqs --timeout=900s
kubectl --context twolevel-dev -n retailstore get pods,scaledobjects,hpa -o wide
```

Từ đây mỗi lần upgrade Cart, Orders hoặc Checkout phải dùng thêm file
apps/worker-keda.yaml; không chạy lại các lệnh deploy baseline ở bước 8.
KEDA có thể giảm worker xuống 0 khi hàng đợi rỗng.

Chart `worker-scaling` mặc định tạo cả ba ScaledObject. Values `workers.cart`,
`workers.orders`, `workers.checkout` có thể đặt `false` để bỏ worker tương ứng.
Nếu upgrade release đã tồn tại, việc đổi một giá trị sang `false` sẽ xóa
ScaledObject do release đó đang quản lý. E1–E3 dùng ScaledObject riêng cho Orders;
không bật scaler Orders từ release chung cùng lúc với scaler của experiment.

## 10. Bật NodePool Karpenter

Sau khi quan sát KEDA, bật NodePool. Không chạy lại helm install ở bước 9
để thay đổi release này; dùng helm upgrade như sau:

```bash
helm upgrade platform-config kubernetes/charts/platform-config \
  --namespace karpenter --kube-context twolevel-dev \
  -f kubernetes/environments/dev/platform.yaml --set nodePool.enabled=true --wait --timeout 900s
kubectl --context twolevel-dev wait --for=condition=Ready ec2nodeclass/default nodepool/default --timeout=900s
kubectl --context twolevel-dev get nodes,nodeclaims
kubectl --context twolevel-dev -n retailstore get pods -o wide
```

Karpenter bổ sung node khi có pod chưa xếp được và NodePool đáp ứng yêu cầu.
Pod có thể chạy trên mọi node phù hợp; không bảo đảm luôn ưu tiên system node.

## 11. Kiểm tra sau deploy

```bash
# Kiểm tra API rollout và autoscaling.
kubectl --context twolevel-dev -n retailstore rollout status deployment/carts-api --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-api --timeout=900s
kubectl --context twolevel-dev -n retailstore rollout status deployment/checkout-api --timeout=900s
kubectl --context twolevel-dev -n retailstore get pods,scaledobjects,hpa
kubectl --context twolevel-dev get nodes,nodeclaims

# Đọc log Catalog để kiểm tra startup/RDS.
kubectl --context twolevel-dev -n retailstore logs deployment/catalog --tail=50
```

Trạng thái Ready chưa thay thế thử giao dịch API → SQS → worker → RDS.
Nếu Pod lỗi, thay `TEN_POD` bằng tên thực tế:

```bash
kubectl --context twolevel-dev -n retailstore describe pod TEN_POD
kubectl --context twolevel-dev -n retailstore logs TEN_POD --tail=100
```

Thử Catalog trong terminal riêng, rồi mở `http://localhost:8081/catalog/products`:

```bash
kubectl --context twolevel-dev -n retailstore port-forward --address 127.0.0.1 service/catalog 8081:80
```

Nếu push lại tag `latest` hoặc thay credentials/CA khi app đã chạy, restart workload
để nạp lại cấu hình/image. Chỉ chạy khi có thay đổi cần áp dụng:

```bash
kubectl --context twolevel-dev -n retailstore rollout restart deployment \
  carts-api carts-worker orders-api orders-worker checkout-api checkout-worker catalog recommendations
```

## Các file thực thi tương ứng

| Bước | File |
|---|---|
| Xem Terraform output | `01-export-config.sh` |
| Bootstrap | `02-bootstrap.sh` |
| Apply hai file Secret local | `02-apply-secrets.sh` |
| CA có kiểm tra PEM | `02-create-rds-ca-configmap.py` |
| Monitoring | `03-deploy-monitoring.sh` |
| Metrics Server, controller Karpenter và KEDA | `04-deploy-platform.sh` |
| Năm backend | `05-deploy-apps.sh` |
| Chuyển worker sang KEDA và tạo scaler | `06-deploy-autoscaling.sh` |
| Bật NodePool | `06-enable-nodepool.sh` |
| Kiểm tra tổng thể | `07-verify.sh` |
| Grafana port-forward | `08-port-forward.sh` |

`00-init-s3-backend.py` chỉ dùng trước Terraform khi cần chuẩn bị S3 backend.
`09-teardown.sh` là thao tác gỡ riêng: chỉ chạy sau khi dừng tải và bảo toàn
message/dữ liệu cần giữ; không thuộc chuỗi triển khai. Hướng dẫn gỡ nằm trong
[DEPLOYMENT.md](../docs/DEPLOYMENT.md). Không chạy Terraform destroy để sửa lỗi deploy.
