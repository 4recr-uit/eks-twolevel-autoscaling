# Replace the instance ID with your own EC2 instance ID that has access to the RDS instances. 
# The localPortNumber can be any available port on your local machine.

# SSM Tunnel to RDS PostgreSQL

aws ssm start-session --region us-east-1 --target i-00c54b8d20bb13369 --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters "host=twolevel-autoscaling-dev-postgres.ceb0a0oo6thh.us-east-1.rds.amazonaws.com,portNumber=5432,localPortNumber=15432"

# SSM Tunnel to RDS MySQL

aws ssm start-session --region us-east-1 --target i-00c54b8d20bb13369 --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters "host=twolevel-autoscaling-dev-mysql.ceb0a0oo6thh.us-east-1.rds.amazonaws.com,portNumber=3306,localPortNumber=13306"
