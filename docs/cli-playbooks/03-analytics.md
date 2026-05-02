# Playbook 03 — Analytics Stack

Stack: `AnalyticsStack`  
Resources: Glue database, Glue crawler, Athena workgroup, EventBridge Scheduler

---

## Deploy

```bash
cdk deploy AnalyticsStack
```

---

## Verify

### SSM parameters written

```bash
aws ssm get-parameter --name /ops-lab/pipeline/glue-database-name --query Parameter.Value --output text
aws ssm get-parameter --name /ops-lab/pipeline/athena-workgroup --query Parameter.Value --output text
```

### Glue database exists

```bash
aws glue get-database --name ops-lab-pipeline \
  --query 'Database.{Name:Name,Location:LocationUri}'
```

### Crawler exists and is ready

```bash
aws glue get-crawler --name ops-lab-pipeline-crawler \
  --query 'Crawler.{State:State,LastStatus:LastCrawl.Status,Schedule:Schedule.ScheduleExpression}'
```

### Athena workgroup exists

```bash
aws athena get-work-group --work-group ops-lab-pipeline \
  --query 'WorkGroup.{State:State,BytesCutoff:Configuration.BytesScannedCutoffPerQuery}'
```

### EventBridge Scheduler exists

```bash
aws scheduler get-schedule --name ops-lab-pipeline-crawler-daily \
  --query '{Expression:ScheduleExpression,State:State}'
```

---

## Run the crawler manually

```bash
aws glue start-crawler --name ops-lab-pipeline-crawler

# Poll until idle
watch -n 5 "aws glue get-crawler --name ops-lab-pipeline-crawler \
  --query 'Crawler.{State:State,LastStatus:LastCrawl.Status,Tables:LastCrawl.TablesCreated}'"
```

### Confirm table was discovered

```bash
aws glue get-tables --database-name ops-lab-pipeline \
  --query 'TableList[*].{Name:Name,Updated:UpdateTime}'
```

---

## Run an Athena query

### Via script

```bash
python scripts/query_athena.py "SELECT source, COUNT(*) AS cnt FROM data GROUP BY source"
```

### Via AWS CLI

```bash
WORKGROUP=$(aws ssm get-parameter --name /ops-lab/pipeline/athena-workgroup --query Parameter.Value --output text)

EXECUTION_ID=$(aws athena start-query-execution \
  --query-string "SELECT source, COUNT(*) FROM data GROUP BY source" \
  --query-execution-context Database=ops-lab-pipeline \
  --work-group "$WORKGROUP" \
  --query QueryExecutionId --output text)

echo "Execution ID: $EXECUTION_ID"

# Wait for completion
aws athena get-query-execution --query-execution-id "$EXECUTION_ID" \
  --query 'QueryExecution.Status.State'

# Fetch results
aws athena get-query-results --query-execution-id "$EXECUTION_ID" \
  --query 'ResultSet.Rows[*].Data[*].VarCharValue'
```

---

## Useful Athena queries

```sql
-- Row count by source and day
SELECT source, year, month, day, COUNT(*) AS events
FROM data
GROUP BY source, year, month, day
ORDER BY year, month, day, source;

-- Latest 20 events
SELECT *
FROM data
ORDER BY timestamp DESC
LIMIT 20;

-- Events in last 24 hours (uses partition pruning)
SELECT *
FROM data
WHERE year = CAST(year(current_date) AS VARCHAR)
  AND month = LPAD(CAST(month(current_date) AS VARCHAR), 2, '0')
  AND day = LPAD(CAST(day(current_date) AS VARCHAR), 2, '0')
LIMIT 100;
```

---

## Tear down

```bash
cdk destroy AnalyticsStack
```

> Note: Athena results bucket is auto-deleted on stack destroy. Glue database and tables are
> removed. The EventBridge Scheduler is also removed.
