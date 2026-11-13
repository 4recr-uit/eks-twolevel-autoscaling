AWS_REGION='us-east-1'

# List all SQS queues in the specified region
aws sqs list-queues \
  --region "$AWS_REGION" \
  --output table

# Get the URL from the specific SQS queue name
ORDERS_QUEUE_URL=$(aws sqs get-queue-url \
  --region "$AWS_REGION" \
  --queue-name orders-queue \
  --query QueueUrl \
  --output text)

CHECKOUT_QUEUE_URL=$(aws sqs get-queue-url \
  --region "$AWS_REGION" \
  --queue-name checkout-queue \
  --query QueueUrl \
  --output text)

CART_QUEUE_URL=$(aws sqs get-queue-url \
  --region "$AWS_REGION" \
  --queue-name cart-queue \
  --query QueueUrl \
  --output text)

# Get the current attributes of the SQS queue
aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$ORDERS_QUEUE_URL" \
  --attribute-names \
    ApproximateNumberOfMessages \
    ApproximateNumberOfMessagesNotVisible \
    ApproximateNumberOfMessagesDelayed \
    VisibilityTimeout \
    RedrivePolicy \
  --output json

aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$CHECKOUT_QUEUE_URL" \
  --attribute-names \
    ApproximateNumberOfMessages \
    ApproximateNumberOfMessagesNotVisible \
    ApproximateNumberOfMessagesDelayed \
    VisibilityTimeout \
    RedrivePolicy \
  --output json

aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$CART_QUEUE_URL" \
  --attribute-names \
    ApproximateNumberOfMessages \
    ApproximateNumberOfMessagesNotVisible \
    ApproximateNumberOfMessagesDelayed \
    VisibilityTimeout \
    RedrivePolicy \
  --output json