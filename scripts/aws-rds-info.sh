AWS_REGION='us-east-1'

# List all RDS instances with their status, engine, class, allocated storage, and storage type
aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --query 'DBInstances[].{Name:DBInstanceIdentifier,Status:DBInstanceStatus,Engine:Engine,Class:DBInstanceClass,AllocatedGiB:AllocatedStorage,StorageType:StorageType}' \
  --output table

POSTGRES_INSTANCE='twolevel-autoscaling-dev-postgres'
MYSQL_INSTANCE='twolevel-autoscaling-dev-mysql'

# Check the remaining free storage space of the RDS instance in GiB
aws cloudwatch get-metric-statistics \
  --region "$AWS_REGION" \
  --namespace AWS/RDS \
  --metric-name FreeStorageSpace \
  --dimensions "Name=DBInstanceIdentifier,Value=$POSTGRES_INSTANCE" \
  --start-time "$(date -u -d '1 hour ago' +'%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --period 300 \
  --statistics Minimum \
  --output json |
python -c 'import json,sys; d=json.load(sys.stdin)["Datapoints"]; d.sort(key=lambda x:x["Timestamp"]); print("Không có mẫu CloudWatch" if not d else "Thời gian: {}\nDung lượng trống: {:.2f} GiB".format(d[-1]["Timestamp"], d[-1]["Minimum"]/1024**3))'

aws cloudwatch get-metric-statistics \
  --region "$AWS_REGION" \
  --namespace AWS/RDS \
  --metric-name FreeStorageSpace \
  --dimensions "Name=DBInstanceIdentifier,Value=$MYSQL_INSTANCE" \
  --start-time "$(date -u -d '1 hour ago' +'%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --period 300 \
  --statistics Minimum \
  --output json |
python -c 'import json,sys; d=json.load(sys.stdin)["Datapoints"]; d.sort(key=lambda x:x["Timestamp"]); print("Không có mẫu CloudWatch" if not d else "Thời gian: {}\nDung lượng trống: {:.2f} GiB".format(d[-1]["Timestamp"], d[-1]["Minimum"]/1024**3))'

# Check the CPU utilization of the RDS instance
aws cloudwatch get-metric-statistics \
  --region "$AWS_REGION" \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions "Name=DBInstanceIdentifier,Value=$POSTGRES_INSTANCE" \
  --start-time "$(date -u -d '1 hour ago' +'%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --period 300 \
  --statistics Average \
  --query 'sort_by(Datapoints, &Timestamp)[].[Timestamp,Average]' \
  --output table

aws cloudwatch get-metric-statistics \
  --region "$AWS_REGION" \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions "Name=DBInstanceIdentifier,Value=$MYSQL_INSTANCE" \
  --start-time "$(date -u -d '1 hour ago' +'%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --period 300 \
  --statistics Average \
  --query 'sort_by(Datapoints, &Timestamp)[].[Timestamp,Average]' \
  --output table