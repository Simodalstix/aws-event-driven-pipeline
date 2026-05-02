#!/usr/bin/env python3
"""Print a quick health summary of the pipeline.

Checks:
  - SQS queue depth (visible + in-flight)
  - DLQ depth
  - Lambda error count (last 1 hour)
  - Last Glue crawler run status and duration
"""
from datetime import datetime, timedelta, timezone

import boto3

REGION = "ap-southeast-2"
LAMBDA_FUNCTION_NAME = "ops-lab-pipeline-processor"
GLUE_CRAWLER_NAME = "ops-lab-pipeline-crawler"

SSM_QUEUE_URL = "/ops-lab/pipeline/sqs-queue-url"
SSM_DLQ_URL = "/ops-lab/pipeline/dlq-url"


def get_param(ssm, name: str) -> str:
    return ssm.get_parameter(Name=name)["Parameter"]["Value"]


def queue_depth(sqs, url: str) -> tuple[int, int]:
    attrs = sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    return (
        int(attrs["ApproximateNumberOfMessages"]),
        int(attrs["ApproximateNumberOfMessagesNotVisible"]),
    )


def lambda_errors(cw) -> int:
    now = datetime.now(timezone.utc)
    resp = cw.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName="Errors",
        Dimensions=[{"Name": "FunctionName", "Value": LAMBDA_FUNCTION_NAME}],
        StartTime=now - timedelta(hours=1),
        EndTime=now,
        Period=3600,
        Statistics=["Sum"],
    )
    points = resp.get("Datapoints", [])
    return int(points[0]["Sum"]) if points else 0


def last_crawler_run(glue_client) -> dict | None:
    resp = glue_client.get_crawler_metrics(CrawlerNameList=[GLUE_CRAWLER_NAME])
    metrics = resp.get("CrawlerMetricsList", [])
    if not metrics:
        return None

    history = glue_client.list_crawls(
        CrawlerName=GLUE_CRAWLER_NAME,
        MaxResults=1,
    )
    runs = history.get("Crawls", [])
    if not runs:
        return None
    return runs[0]


def main():
    ssm = boto3.client("ssm", region_name=REGION)
    sqs = boto3.client("sqs", region_name=REGION)
    cw = boto3.client("cloudwatch", region_name=REGION)
    glue = boto3.client("glue", region_name=REGION)

    queue_url = get_param(ssm, SSM_QUEUE_URL)
    dlq_url = get_param(ssm, SSM_DLQ_URL)

    q_visible, q_inflight = queue_depth(sqs, queue_url)
    dlq_visible, _ = queue_depth(sqs, dlq_url)
    errors = lambda_errors(cw)
    run = last_crawler_run(glue)

    print("=== Pipeline Health ===")
    print(f"Queue  : {q_visible} visible, {q_inflight} in-flight")
    status = "OK" if dlq_visible == 0 else "ALERT"
    print(f"DLQ    : {dlq_visible} message(s)  [{status}]")
    err_status = "OK" if errors == 0 else "ALERT"
    print(f"Lambda : {errors} error(s) in last 1h  [{err_status}]")

    if run:
        state = run.get("State", "UNKNOWN")
        start = run.get("StartTime", "")
        end = run.get("EndTime", "")
        duration = ""
        if start and end:
            secs = int((end - start).total_seconds())
            duration = f" ({secs}s)"
        print(f"Crawler: {state}{duration}  last started {start}")
    else:
        print("Crawler: no runs recorded yet")


if __name__ == "__main__":
    main()
