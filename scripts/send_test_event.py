#!/usr/bin/env python3
"""Publish a synthetic event to the pipeline SQS queue."""
import argparse
import json
import uuid
from datetime import datetime, timezone

import boto3

SSM_QUEUE_URL = "/ops-lab/pipeline/sqs-queue-url"
REGION = "ap-southeast-2"


def get_queue_url():
    ssm = boto3.client("ssm", region_name=REGION)
    return ssm.get_parameter(Name=SSM_QUEUE_URL)["Parameter"]["Value"]


def send_event(source: str, payload: dict, count: int = 1):
    queue_url = get_queue_url()
    sqs = boto3.client("sqs", region_name=REGION)

    for i in range(count):
        body = {
            "event_id": str(uuid.uuid4()),
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        resp = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(body))
        print(f"[{i+1}/{count}] sent {resp['MessageId']} — source={source}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a synthetic event to the pipeline queue")
    parser.add_argument("--source", default="test", help="Event source label (default: test)")
    parser.add_argument("--count", type=int, default=1, help="Number of events to send (default: 1)")
    parser.add_argument(
        "--payload",
        default='{}',
        help='Extra JSON payload merged into the event body (default: {})',
    )
    args = parser.parse_args()

    try:
        extra = json.loads(args.payload)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid --payload JSON: {e}")

    send_event(source=args.source, payload=extra, count=args.count)
