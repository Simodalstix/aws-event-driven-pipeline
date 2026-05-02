# Playbook 02 — Process Stack

Stack: `ProcessStack`  
Resources: Lambda processor, S3 data bucket, IAM role, CloudWatch log group

---

## Deploy

```bash
cdk deploy ProcessStack
```

---

## Verify

### Bucket exists and is private

```bash
BUCKET=$(aws ssm get-parameter --name /ops-lab/pipeline/s3-bucket-name --query Parameter.Value --output text)
aws s3api get-bucket-location --bucket "$BUCKET"
aws s3api get-public-access-block --bucket "$BUCKET"
```

### Lambda exists

```bash
aws lambda get-function \
  --function-name ops-lab-pipeline-processor \
  --query 'Configuration.{State:State,Runtime:Runtime,Timeout:Timeout,Memory:MemorySize}'
```

### Trigger end-to-end: send an event, confirm object lands in S3

```bash
python scripts/send_test_event.py --source smoke --count 1

# Wait a few seconds for Lambda to process, then:
BUCKET=$(aws ssm get-parameter --name /ops-lab/pipeline/s3-bucket-name --query Parameter.Value --output text)
aws s3 ls "s3://$BUCKET/" --recursive | tail -5
```

### Check Lambda logs for the last invocation

```bash
aws logs tail /ops-lab/pipeline/processor --since 5m
```

---

## Lambda error monitoring

```bash
# Error count in last 1 hour
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

---

## Inspect an S3 object

```bash
BUCKET=$(aws ssm get-parameter --name /ops-lab/pipeline/s3-bucket-name --query Parameter.Value --output text)
KEY=$(aws s3 ls "s3://$BUCKET/" --recursive | sort | tail -1 | awk '{print $4}')
aws s3 cp "s3://$BUCKET/$KEY" - | python3 -m json.tool
```

---

## Tear down

```bash
cdk destroy ProcessStack
```

> Note: S3 bucket has `RETAIN` removal policy — delete manually if needed:
> ```bash
> aws s3 rb "s3://$BUCKET" --force
> ```
