#!/usr/bin/env python3
"""Replay failed messages from the DLQ back to the main queue.

Reads up to --max messages from the DLQ in batches of 10, sends each to the
main queue, then deletes it from the DLQ. Stops when the DLQ is empty or
--max is reached.
"""
import argparse
import sys

import boto3

SSM_QUEUE_URL = "/ops-lab/pipeline/sqs-queue-url"
SSM_DLQ_URL = "/ops-lab/pipeline/dlq-url"
REGION = "ap-southeast-2"


def get_param(ssm, name: str) -> str:
    return ssm.get_parameter(Name=name)["Parameter"]["Value"]


def redrive(max_messages: int, dry_run: bool):
    ssm = boto3.client("ssm", region_name=REGION)
    sqs = boto3.client("sqs", region_name=REGION)

    queue_url = get_param(ssm, SSM_QUEUE_URL)
    dlq_url = get_param(ssm, SSM_DLQ_URL)

    moved = 0
    while moved < max_messages:
        batch_size = min(10, max_messages - moved)
        resp = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=batch_size,
            WaitTimeSeconds=2,
        )
        messages = resp.get("Messages", [])
        if not messages:
            print("DLQ is empty — nothing left to redrive.")
            break

        for msg in messages:
            if dry_run:
                print(f"[dry-run] would redrive {msg['MessageId']}")
            else:
                sqs.send_message(QueueUrl=queue_url, MessageBody=msg["Body"])
                sqs.delete_message(QueueUrl=dlq_url, ReceiptHandle=msg["ReceiptHandle"])
                print(f"Redriven {msg['MessageId']}")
            moved += 1

    print(f"Done — {'would redrive' if dry_run else 'redriven'} {moved} message(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Redrive DLQ messages back to the main queue")
    parser.add_argument("--max", type=int, default=100, help="Max messages to redrive (default: 100)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without moving anything")
    args = parser.parse_args()

    redrive(max_messages=args.max, dry_run=args.dry_run)
