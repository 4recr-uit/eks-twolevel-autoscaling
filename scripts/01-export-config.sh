#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số." >&2; exit 2; }

# Tìm repo để các đường dẫn hoạt động từ mọi thư mục.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# Dùng cấu hình dev.
# Chỉ hiển thị thông tin không chứa mật khẩu; không sinh hoặc sửa YAML.
# Đối chiếu kết quả này để điền các giá trị REPLACE_... trong kubernetes/environments/dev/.
terraform -chdir=terraform output eks_cluster_name
terraform -chdir=terraform output platform_contract
terraform -chdir=terraform output ecr_repository_urls
terraform -chdir=terraform output sqs_queue_urls
terraform -chdir=terraform output postgres_endpoint
terraform -chdir=terraform output mysql_endpoint
