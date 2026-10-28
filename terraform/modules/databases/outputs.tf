output "postgres_endpoint" {
  description = "PostgreSQL hostname; use port 5432"
  value       = aws_db_instance.postgres.address
}

output "mysql_endpoint" {
  description = "MySQL hostname; use port 3306"
  value       = aws_db_instance.mysql.address
}

output "postgres_master_secret_arn" {
  description = "ARN of the RDS-managed PostgreSQL bootstrap credential secret"
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "mysql_master_secret_arn" {
  description = "ARN of the RDS-managed MySQL bootstrap credential secret"
  value       = aws_db_instance.mysql.master_user_secret[0].secret_arn
}

output "postgres_security_group_id" {
  description = "Security group allowing PostgreSQL traffic from EKS nodes"
  value       = aws_security_group.postgres.id
}

output "mysql_security_group_id" {
  description = "Security group allowing MySQL traffic from EKS nodes"
  value       = aws_security_group.mysql.id
}
