locals {
  # Filter out empty or whitespace-only queue names
  valid_queue_names = toset([
    for name in var.sqs_queue_names : trimspace(name) if trimspace(name) != ""
  ])

  # Build the final queue name based on use_name_prefix flag
  queue_name_map = {
    for name in local.valid_queue_names :
    name => var.use_name_prefix && var.name_prefix != "" ? "${var.name_prefix}-${name}" : name
  }

  # Build DLQ name map
  dlq_name_map = {
    for name in local.valid_queue_names :
    name => var.use_name_prefix && var.name_prefix != "" ? "${var.name_prefix}-${name}-dlq" : "${name}-dlq"
  }
}

# ── Dead Letter Queues ────────────────────────────────────────────────────────
# Created first so their ARNs are available for the redrive_policy on main queues.
resource "aws_sqs_queue" "dlq" {
  for_each = var.enable_dlq ? local.valid_queue_names : toset([])

  name                      = local.dlq_name_map[each.value]
  message_retention_seconds = var.dlq_message_retention
  sqs_managed_sse_enabled   = true

  tags = merge(
    { Environment = var.environment },
    var.tags,
    { Name = "${local.dlq_name_map[each.value]}" }
  )
}

# ── Main SQS Queues ───────────────────────────────────────────────────────────
resource "aws_sqs_queue" "this" {
  for_each = local.valid_queue_names

  name                       = local.queue_name_map[each.value]
  visibility_timeout_seconds = var.sqs_visibility_timeout
  message_retention_seconds  = var.sqs_message_retention
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  max_message_size           = var.max_message_size
  sqs_managed_sse_enabled    = true

  # Redrive to DLQ after max_receive_count failures
  redrive_policy = var.enable_dlq ? jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.value].arn
    maxReceiveCount     = var.max_receive_count
  }) : null

  tags = merge(
    { Environment = var.environment },
    var.tags,
    { Name = local.queue_name_map[each.value] }
  )
}

# ── DLQ Redrive Allow Policy ──────────────────────────────────────────────────
# Allows the main queue to use the DLQ as a redrive target.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  for_each = var.enable_dlq ? local.valid_queue_names : toset([])

  queue_url = aws_sqs_queue.dlq[each.value].id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.this[each.value].arn]
  })
}
