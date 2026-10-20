resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.database_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-subnets" })
}

resource "aws_security_group" "postgres" {
  name        = "${var.name_prefix}-postgres-sg"
  description = "PostgreSQL access from EKS nodes only"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-postgres-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_nodes" {
  security_group_id            = aws_security_group.postgres.id
  referenced_security_group_id = var.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL from seed and Karpenter nodes"
}

resource "aws_security_group" "mysql" {
  name        = "${var.name_prefix}-mysql-sg"
  description = "MySQL access from EKS nodes only"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-mysql-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "mysql_from_nodes" {
  security_group_id            = aws_security_group.mysql.id
  referenced_security_group_id = var.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL from seed and Karpenter nodes"
}

resource "aws_db_instance" "postgres" {
  identifier                   = "${var.name_prefix}-postgres"
  engine                       = "postgres"
  engine_version               = var.postgres_engine_version
  instance_class               = var.db_instance_class
  db_name                      = "retaildb"
  username                     = var.master_username
  manage_master_user_password  = true
  allocated_storage            = var.allocated_storage
  max_allocated_storage        = var.max_allocated_storage
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.postgres.id]
  publicly_accessible          = false
  multi_az                     = false
  backup_retention_period      = var.backup_retention_days
  auto_minor_version_upgrade   = false
  deletion_protection          = var.deletion_protection
  skip_final_snapshot          = !var.create_final_snapshot
  final_snapshot_identifier    = var.create_final_snapshot ? "${var.name_prefix}-postgres-final" : null
  copy_tags_to_snapshot        = true
  performance_insights_enabled = false

  tags = merge(var.tags, { Name = "${var.name_prefix}-postgres" })
}

resource "aws_db_instance" "mysql" {
  identifier                   = "${var.name_prefix}-mysql"
  engine                       = "mysql"
  engine_version               = var.mysql_engine_version
  instance_class               = var.db_instance_class
  db_name                      = "catalogdb"
  username                     = var.master_username
  manage_master_user_password  = true
  allocated_storage            = var.allocated_storage
  max_allocated_storage        = var.max_allocated_storage
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.mysql.id]
  publicly_accessible          = false
  multi_az                     = false
  backup_retention_period      = var.backup_retention_days
  auto_minor_version_upgrade   = false
  deletion_protection          = var.deletion_protection
  skip_final_snapshot          = !var.create_final_snapshot
  final_snapshot_identifier    = var.create_final_snapshot ? "${var.name_prefix}-mysql-final" : null
  copy_tags_to_snapshot        = true
  performance_insights_enabled = false

  tags = merge(var.tags, { Name = "${var.name_prefix}-mysql" })
}
