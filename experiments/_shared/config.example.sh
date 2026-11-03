# Sao chép thành config.local.sh và chỉnh theo môi trường trước khi sử dụng.
# Chỉ chứa tên tài nguyên không nhạy cảm; không lưu credential, token hoặc mật khẩu.
export EXPERIMENT_CONTEXT='twolevel-dev'
export EXPERIMENT_NAMESPACE='retailstore'
export EXPERIMENT_DEPLOYMENT='orders-worker'
export EXPERIMENT_QUEUE='orders-queue'
export EXPERIMENT_AWS_REGION='us-east-1'
