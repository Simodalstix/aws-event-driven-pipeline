# Playbook 01 — Ingest Stack

Stack: `IngestStack`  
Resources: SQS queue, DLQ, CloudWatch alarm

---

## Deploy

```bash
cdk deploy IngestStack
```

---

## Verify

### Queue and DLQ exist

```bash
aws ssm get-parameter --name /ops-lab/pipeline/sqs-queue-url --query Parameter.Value --output text
aws ssm get-parameter --name /ops-lab/pipeline/dlq-url --query Parameter.Value --output text
```

### Queue attributes

```bash
QUEUE_URL=$(aws ssm get-parameter --name /ops-lab/pipeline/sqs-queue-url --query Parameter.Value --output text)
aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names All \
  --query 'Attributes.{Visible:ApproximateNumberOfMessages,InFlight:ApproximateNumberOfMessagesNotVisible,Retention:MessageRetentionPeriod,Visibility:VisibilityTimeout}'
```

### DLQ alarm exists and is in OK state

```bash
aws cloudwatch describe-alarms \
  --alarm-names ops-lab-pipeline-dlq-depth \
  --query 'MetricAlarms[0].{State:StateValue,Threshold:Threshold}'
```

---

## Send a test message

```bash
QUEUE_URL=$(aws ssm get-parameter --name /ops-lab/pipeline/sqs-queue-url --query Parameter.Value --output text)
aws sqs send-message \
  --queue-url "$QUEUE_URL" \
  --message-body '{"source":"test","event_type":"smoke_test"}'
```

Or via the script:

```bash
python scripts/send_test_event.py --source test --count 3
```

---

## Tear down

```bash
cdk destroy IngestStack
```

> Note: SSM parameters are removed with the stack. DLQ messages are not — drain first if needed.
