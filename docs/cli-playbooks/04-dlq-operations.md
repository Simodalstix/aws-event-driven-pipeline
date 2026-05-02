# Playbook 04 — DLQ Operations

DLQ: `ops-lab-pipeline-dlq`  
Alarm: `ops-lab-pipeline-dlq-depth` (fires when depth > 0)

---

## Check DLQ depth

```bash
DLQ_URL=$(aws ssm get-parameter --name /ops-lab/pipeline/dlq-url --query Parameter.Value --output text)
aws sqs get-queue-attributes \
  --queue-url "$DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages'
```

Or via the health script:

```bash
python scripts/pipeline_health.py
```

---

## Inspect a DLQ message without removing it

```bash
DLQ_URL=$(aws ssm get-parameter --name /ops-lab/pipeline/dlq-url --query Parameter.Value --output text)
aws sqs receive-message \
  --queue-url "$DLQ_URL" \
  --visibility-timeout 30 \
  --query 'Messages[0].Body' --output text | python3 -m json.tool
```

> The message returns to the DLQ after the visibility timeout. Do not delete it unless you intend to discard it.

---

## Redrive DLQ messages back to the main queue

### Dry run first

```bash
python scripts/redrive_dlq.py --dry-run
```

### Redrive all messages

```bash
python scripts/redrive_dlq.py
```

### Redrive a limited batch

```bash
python scripts/redrive_dlq.py --max 10
```

---

## Discard (purge) all DLQ messages

> Use only after confirming you do not need the failed messages.

```bash
DLQ_URL=$(aws ssm get-parameter --name /ops-lab/pipeline/dlq-url --query Parameter.Value --output text)
aws sqs purge-queue --queue-url "$DLQ_URL"
```

---

## Diagnose why messages are failing

### Lambda logs around the time messages arrived in the DLQ

```bash
aws logs tail /ops-lab/pipeline/processor --since 1h --filter "ERROR"
```

### Lambda error metric

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=ops-lab-pipeline-processor \
  --start-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 3600 \
  --statistics Sum \
  --query 'Datapoints[0].Sum'
```

### Check if the DLQ alarm is active

```bash
aws cloudwatch describe-alarms \
  --alarm-names ops-lab-pipeline-dlq-depth \
  --query 'MetricAlarms[0].{State:StateValue,Updated:StateUpdatedTimestamp}'
```

---

## Silence the alarm after DLQ is drained

The alarm resets automatically once depth returns to 0. To confirm:

```bash
aws cloudwatch describe-alarms \
  --alarm-names ops-lab-pipeline-dlq-depth \
  --query 'MetricAlarms[0].StateValue'
# Expected: "OK"
```
