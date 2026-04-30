# CLAUDE.md — aws-event-driven-pipeline

## Behavioral Guidelines

These apply to every task in this repo. They bias toward caution over speed.
For trivial tasks, use judgment.

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

For infrastructure decisions specifically:
- Name the tradeoff (SQS vs Kinesis, Lambda vs Glue ETL, cost vs flexibility)
- If a CDK construct choice has implications (L1 vs L2 vs L3), surface them
- Don't silently pick a retention period, batch size, or concurrency limit — state it

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked
- No abstractions for single-use constructs
- No configurability that wasn't requested
- If you write 200 lines and it could be 50, rewrite it

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:
- Don't improve adjacent code, comments, or formatting
- Don't refactor things that aren't broken
- Match existing style, even if you'd do it differently
- If you notice unrelated issues, mention them — don't fix them silently

When your changes create orphans:
- Remove imports/variables/constructs that YOUR changes made unused
- Don't remove pre-existing dead code unless asked

Every changed line should trace directly to the request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

For infrastructure tasks, replace "tests pass" with CLI or script verification:
- "Add SQS queue" → verify: queue URL in SSM Parameter Store, message sent and received
- "Add Lambda processor" → verify: message flows end-to-end, object appears in S3
- "Add Glue crawler" → verify: crawler runs, table appears in Glue database
- "Add DLQ" → verify: poison message lands in DLQ, alarm fires

For multi-step tasks, state a brief plan first:
```
1. [Step] → verify: [CLI check]
2. [Step] → verify: [CLI check]
3. [Step] → verify: [CLI check]
```

---

## Platform Context

I am building a modular AWS ops platform as a series of independent but
interconnected GitHub projects. This repo is the data layer — the final
platform piece. It ingests events produced by other platform projects,
processes them through Lambda, lands data in S3, and makes it queryable
via Athena.

**Developer:** simoda
**Machine:** SER8 (Beelink SER8, WSL Ubuntu) for dev — Minisforum UM890
  Proxmox for on-prem VMs
**Region:** ap-southeast-2
**Account:** 820242933814
**Primary tool:** Claude Code (CLI), working directly inside this repo

---

## Existing Projects

- `aws-ops-networking` ✅ — deployed. Foundation VPC. Exports to
  `/ops-lab/networking/*` in SSM Parameter Store.
- `aws-ops-observability` ✅ — deployed. Shared SNS, CloudWatch IAM policy,
  CW agent config. Exports to `/ops-lab/shared/*`.
- `aws-3tier-platform` ✅ — deployed. ALB, ASG, RDS PostgreSQL, ElastiCache
  Redis. Primary event source for this pipeline. Exports to `/ops-lab/3tier/*`.
- `aws-image-pipeline` 🔜 — Packer golden AMIs, Proxmox builder.
- `aws-ssm-puppet-fleet` 🔜 — revamp in progress. SSM, Puppet, AWS Config
  rules, State Manager, auto-remediation.

---

## Platform Rules (apply to every project)

- **IaC:** CDK Python with Poetry — aws-cdk-lib ^2.180.0
- **No hardcoded ARNs or IDs anywhere** — all cross-project values go through
  SSM Parameter Store
- **SSM Parameter Store is the config bus** — whoever creates a resource writes
  its ID to Parameter Store; every other project reads from there at deploy time
- **NAT:** `NONE` by default — Lambda runs without VPC unless explicitly needed
- **EC2 access:** SSM only — no bastions, no key pairs
- **Tagging:** every stack must apply these tags via `cdk.Tags.of(self).add()`:
  `Project: ops-lab`, `Stack: pipeline`, `Environment: lab`
- **All projects include:**
  - CLI playbooks under `docs/cli-playbooks/`
  - Boto3 operational scripts under `scripts/`
  - This `CLAUDE.md` at repo root

---

## This Project: aws-event-driven-pipeline

**Purpose:** Event-driven ingestion and analytics pipeline. Ingests events
from the 3-tier platform, processes via Lambda, lands in S3, crawls schema
with Glue, queries via Athena. Operational tooling — DLQ redrive, pipeline
health checks, Athena query runner — is as important as the infrastructure.

**Pipeline flow:**
```
Event source (3tier app / synthetic) 
  → SQS (+ DLQ) 
  → Lambda processor 
  → S3 (partitioned by date/source) 
  → Glue crawler 
  → Athena
```

### SSM Parameters This Project Reads

```
/ops-lab/networking/vpc-id
/ops-lab/networking/subnet/isolated-0,1,2   → Lambda VPC config if needed
/ops-lab/shared/sns-topic-arn               → DLQ alarm destination
/ops-lab/shared/cloudwatch-write-policy-arn → Lambda execution role
/ops-lab/3tier/alb-dns-name                 → synthetic event generation
```

### SSM Parameters This Project Writes

```
/ops-lab/pipeline/sqs-queue-url
/ops-lab/pipeline/sqs-queue-arn
/ops-lab/pipeline/dlq-url
/ops-lab/pipeline/kinesis-stream-arn        (if Kinesis extension enabled)
/ops-lab/pipeline/s3-bucket-name
/ops-lab/pipeline/glue-database-name
/ops-lab/pipeline/athena-workgroup
```

### What This Stack Deploys

**IngestStack**
- SQS queue — primary ingest, configurable retention and visibility timeout
- Dead-letter queue — poison messages after 3 receive attempts
- CloudWatch alarm — DLQ depth > 0 → SNS alert
- Kinesis Data Stream — optional, context flag `kinesis=true`

**ProcessStack**
- Lambda processor — validates, transforms, writes to S3
- Lambda execution role — attaches shared CloudWatch write policy
- CloudWatch log group — `/ops-lab/pipeline/processor`
- S3 data lake bucket — partitioned `year=/month=/day=/source=`
- S3 lifecycle policy — transition to IA after 30 days

**AnalyticsStack**
- Glue database and crawler — auto-discovers S3 schema on schedule
- Athena workgroup — query results bucket, per-query cost controls
- EventBridge Scheduler — triggers Glue crawler daily

### Lambda Handler Conventions

All Lambda handlers follow this pattern — raise on error, never swallow
exceptions silently. This ensures DLQ routing works correctly:

```python
def handler(event, context):
    try:
        # process
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise  # re-raise so Lambda marks message as failed → DLQ
```

### Operational Scripts (Boto3)

These are first-class deliverables, not afterthoughts:

- `scripts/send_test_event.py` — publish a synthetic event to SQS for testing
- `scripts/redrive_dlq.py` — replay failed messages from DLQ back to main queue
- `scripts/pipeline_health.py` — queue depth, Lambda error rate, last Glue run status
- `scripts/query_athena.py` — run ad-hoc SQL against the Glue catalog, print results

### On-Prem Extension (future)

Kafka broker on Proxmox Minisforum VM bridges to Kinesis. Same provisioner
scripts as `aws-image-pipeline` base image. Kafka Connect forwards to Kinesis,
Lambda processes from there. Hybrid ingestion pattern — on-prem events flow
through the same pipeline as cloud events.

---

## Repo Structure

```
aws-event-driven-pipeline/
├── CLAUDE.md
├── README.md
├── app.py
├── cdk.json
├── pyproject.toml
├── pipeline_lab/
│   ├── __init__.py
│   ├── ingest_stack.py
│   ├── process_stack.py
│   └── analytics_stack.py
├── lambda/
│   ├── processor/
│   │   └── handler.py
│   └── dlq_monitor/
│       └── handler.py
├── scripts/
│   ├── send_test_event.py
│   ├── redrive_dlq.py
│   ├── pipeline_health.py
│   └── query_athena.py
└── docs/
    └── cli-playbooks/
        ├── 01-ingest.md
        ├── 02-processing.md
        ├── 03-analytics.md
        └── 04-dlq-operations.md
```

---

## Key Conventions

- Stack names: `IngestStack`, `ProcessStack`, `AnalyticsStack`
- Deploy order: `IngestStack` → `ProcessStack` → `AnalyticsStack`
- All SSM parameter keys: `/ops-lab/pipeline/{resource}`
- All resource names: `ops-lab-pipeline-{resource}`
- Tag every stack: `Project: ops-lab`, `Stack: pipeline`, `Environment: lab`
- S3 prefix pattern: `year=YYYY/month=MM/day=DD/source={source}/`
- Lambda raise on error — never swallow exceptions, DLQ routing depends on it
- Comments explain *why*, not just *what*
- Kinesis is an optional extension — default to SQS only, add Kinesis via
  context flag when demonstrating streaming specifically
