import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
BUCKET_NAME = os.environ["BUCKET_NAME"]


def handler(event, context):
    try:
        for record in event["Records"]:
            _process_record(record)
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise  # re-raise so Lambda marks the batch as failed → DLQ after maxReceiveCount


def _process_record(record):
    body = json.loads(record["body"])
    source = body.get("source", "unknown")
    now = datetime.now(timezone.utc)

    key = (
        f"year={now.year}/month={now.month:02d}/day={now.day:02d}"
        f"/source={source}/{uuid.uuid4()}.json"
    )

    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(body),
        ContentType="application/json",
    )

    logger.info(f"Written s3://{BUCKET_NAME}/{key}")
