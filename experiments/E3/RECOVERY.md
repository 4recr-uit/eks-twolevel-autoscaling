# Sửa lần nâng cấp Orders sang E3 ngày 2026-11-07

## Nguyên nhân đã kiểm tra

Revision 22 đã bị pending-upgrade vì API và worker mới CrashLoopBackOff. Sự cố
đã được sửa ở revision 23; các lệnh bên dưới lưu lại quy trình xử lý, không cần
chạy lại sau khi E3 hoàn tất. Khi xảy ra lỗi, cả hai log đều ghi:

```text
Failed to initialize database repository: PostgreSQL requires DB_HOST, DB_NAME, DB_USER and DB_PASSWORD or DATABASE_URL
```

Backup trước E3 dùng ServiceAccount `orders-api`/`orders-worker`, tham chiếu Secret
`orders-db`, mount CA từ ConfigMap `rds-ca` và khai báo `DB_SSLROOTCERT`. Chart backend
local vừa dùng để nâng cấp không hỗ trợ đầy đủ các cấu hình đó; khi
`database.secret.create=false`, template local còn bỏ tham chiếu Secret có sẵn.
Nâng cấp với cùng values không thể giữ lại các phần template đã thiếu.

Chart từ Helm revision 21 đã được đọc từ release storage và trích xuất vào:

```text
.generated/e3/orders-chart-revision21/
```

Đây là artifact local, không nằm trong Git. Không đổi image hoặc build ứng dụng
trong lúc sửa cấu hình. Chart được trích xuất đã qua `helm lint`; bản render với
backup và overlay E3 giữ đúng ServiceAccount, Secret DB, CA và TLS env. Sau khi
chuẩn hóa các giá trị mặc định Kubernetes, Pod spec worker khớp backup trước E3,
với thay đổi NodePool thành `e3-orders`. `externalAutoscaling=true` bỏ trường
replicas khỏi manifest; cần đặt replica bằng kubectl trước khi đo.

## Thao tác trên terminal người chạy

Từ `experiments/E3`. Nếu lần nâng cấp cũ vẫn đang chạy, nhấn Ctrl+C một lần ở
terminal đó và đợi lệnh kết thúc. Không chạy đồng thời hai thao tác Helm.

```bash
helm status orders -n retailstore
```

Chỉ chạy sửa khi release không còn ở trạng thái pending-upgrade/pending-rollback/
pending-install. Nếu trạng thái pending vẫn giữ sau khi lệnh cũ đã kết thúc,
kiểm tra lịch sử và tiến trình trước; không xóa Secret lưu revision để vượt khóa.

```bash
(
  set -e

  test -s ../../.generated/e3/orders-chart-revision21/Chart.yaml
  test -s ../../.generated/e3/pre-e3-20261107T083008Z/orders-values.yaml

  helm upgrade orders ../../.generated/e3/orders-chart-revision21 \
    -n retailstore --kube-context twolevel-dev \
    -f ../../.generated/e3/pre-e3-20261107T083008Z/orders-values.yaml \
    -f ./autoscaled-values.yaml \
    --server-side=false --wait --timeout 300s

  kubectl --context twolevel-dev -n retailstore scale deployment/orders-worker --replicas=1
  kubectl --context twolevel-dev -n retailstore rollout status deployment/orders-worker --timeout=300s
)
```

Kiểm tra cả API lẫn worker trước khi bật HPA hoặc phát tải:

```bash
kubectl --context twolevel-dev -n retailstore get deployments,pods -o wide
kubectl --context twolevel-dev -n retailstore logs deployment/orders-worker -c orders-worker --tail=30
kubectl --context twolevel-dev get nodes -l karpenter.sh/nodepool=e3-orders -o wide
```

Mục tiêu là API đủ replica Ready và một worker Ready trên node E3. Kiểm tra lại
đúng một node E3 Ready; node ban đầu đã bị thay trong thời gian lỗi. Nếu có nhiều
node, chuẩn bị lại điều kiện đầu trước lượt đo. Giữ node E1 cho đến khi có kế hoạch
khôi phục cuối thí nghiệm; baseline trước E3 còn trỏ tới `e1-orders`.

Trong các lần upgrade/restore còn lại của đợt E3 này, dùng chart đã trích xuất trên.
Chưa dùng lại chart backend local cho đến khi đồng bộ đủ tính năng và kiểm tra bản
render. Helm rollback revision 21 sẽ khôi phục cấu hình E1, không phải cấu hình E3.
