AWS_REGION='us-east-1'

# ========== RDS
aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --query 'DBInstances[].{Name:DBInstanceIdentifier,Status:DBInstanceStatus,Engine:Engine,Class:DBInstanceClass,AllocatedGiB:AllocatedStorage,StorageType:StorageType}' \
  --output table

DB_INSTANCE='twolevel-autoscaling-dev-postgres'

# Dung lượng trống (GB)
aws cloudwatch get-metric-statistics \
  --region "$AWS_REGION" \
  --namespace AWS/RDS \
  --metric-name FreeStorageSpace \
  --dimensions "Name=DBInstanceIdentifier,Value=$DB_INSTANCE" \
  --start-time "$(date -u -d '1 hour ago' +'%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --period 300 \
  --statistics Minimum \
  --output json |
python -c 'import json,sys; d=json.load(sys.stdin)["Datapoints"]; d.sort(key=lambda x:x["Timestamp"]); print("Không có mẫu CloudWatch" if not d else "Thời gian: {}\nDung lượng trống: {:.2f} GiB".format(d[-1]["Timestamp"], d[-1]["Minimum"]/1024**3))'

# CPU 
aws cloudwatch get-metric-statistics \
  --region "$AWS_REGION" \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions "Name=DBInstanceIdentifier,Value=$DB_INSTANCE" \
  --start-time "$(date -u -d '1 hour ago' +'%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --period 300 \
  --statistics Average \
  --query 'sort_by(Datapoints, &Timestamp)[].[Timestamp,Average]' \
  --output table

# ========== SQS

# Liệt kê queue
aws sqs list-queues \
  --region "$AWS_REGION" \
  --output table

# Lấy url của queue theo tên
QUEUE_URL=$(aws sqs get-queue-url \
  --region "$AWS_REGION" \
  --queue-name orders-queue \
  --query QueueUrl \
  --output text)

# Xem số message trong queue
aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$QUEUE_URL" \
  --attribute-names \
    ApproximateNumberOfMessages \
    ApproximateNumberOfMessagesNotVisible \
    ApproximateNumberOfMessagesDelayed \
    VisibilityTimeout \
    RedrivePolicy \
  --output json

# ========== EKS

# List cluster
aws eks list-clusters \
  --region "$AWS_REGION" \
  --output table

# Check current context
kubectl config current-context

# List nodes and their instance types
kubectl --context twolevel-dev get nodes \
  -L node.kubernetes.io/instance-type \
  -o wide

# List HPA and KEDA ScaledObject
kubectl --context twolevel-dev -n retailstore get hpa,scaledobject

# Check logs of orders-worker deployment
kubectl --context twolevel-dev -n retailstore \
  logs deployment/orders-worker --tail=30