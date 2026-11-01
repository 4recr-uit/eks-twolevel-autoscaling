#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Usage: bash scripts/02-apply-secrets.sh" >&2; exit 2; }

# 1. Kiểm tra hai file local đã được điền credentials.
test -f kubernetes/environments/dev/secrets/database-secrets.local.yaml
test -f kubernetes/environments/dev/secrets/grafana-admin.local.yaml
if grep -Eq '^[[:space:]]+REPLACE_WITH_' \
  kubernetes/environments/dev/secrets/database-secrets.local.yaml \
  kubernetes/environments/dev/secrets/grafana-admin.local.yaml; then
  echo "Điền đầy đủ credentials trong hai file local trước khi apply." >&2
  exit 1
fi

# 2. Kiểm tra namespace đích.
kubectl --context twolevel-dev get namespace retailstore monitoring

# 3. Kiểm tra cả hai manifest trước khi lưu Secret.
kubectl --context twolevel-dev apply --dry-run=server \
  -f kubernetes/environments/dev/secrets/database-secrets.local.yaml
kubectl --context twolevel-dev apply --dry-run=server \
  -f kubernetes/environments/dev/secrets/grafana-admin.local.yaml

# 4. Lưu năm DB Secret và Secret Grafana.
kubectl --context twolevel-dev apply \
  -f kubernetes/environments/dev/secrets/database-secrets.local.yaml
kubectl --context twolevel-dev apply \
  -f kubernetes/environments/dev/secrets/grafana-admin.local.yaml

# 5. Xác nhận Secret tồn tại; không in giá trị credentials.
kubectl --context twolevel-dev -n retailstore get secret \
  cart-db orders-db checkout-db catalog-db recommendations-db
kubectl --context twolevel-dev -n monitoring get secret grafana-admin
