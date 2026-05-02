#!/usr/bin/env python3
"""Run an ad-hoc SQL query against the pipeline Glue catalog via Athena and print results.

Usage:
  python scripts/query_athena.py "SELECT * FROM \"ops-lab-pipeline\".data LIMIT 10"
  python scripts/query_athena.py --file query.sql
"""
import argparse
import sys
import time

import boto3

REGION = "ap-southeast-2"
SSM_WORKGROUP = "/ops-lab/pipeline/athena-workgroup"
SSM_DATABASE = "/ops-lab/pipeline/glue-database-name"
POLL_INTERVAL = 2  # seconds between status checks


def get_param(ssm, name: str) -> str:
    return ssm.get_parameter(Name=name)["Parameter"]["Value"]


def run_query(sql: str) -> None:
    ssm = boto3.client("ssm", region_name=REGION)
    athena = boto3.client("athena", region_name=REGION)

    workgroup = get_param(ssm, SSM_WORKGROUP)
    database = get_param(ssm, SSM_DATABASE)

    resp = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    execution_id = resp["QueryExecutionId"]
    print(f"Query ID: {execution_id}")

    # Poll until terminal state
    while True:
        status = athena.get_query_execution(QueryExecutionId=execution_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        print(f"  ... {state}", end="\r")
        time.sleep(POLL_INTERVAL)

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
        raise SystemExit(f"Query {state}: {reason}")

    stats = status["QueryExecution"].get("Statistics", {})
    scanned = stats.get("DataScannedInBytes", 0)
    print(f"Succeeded — scanned {scanned / 1024:.1f} KB")

    # Paginate results
    paginator = athena.get_paginator("get_query_results")
    first_page = True
    for page in paginator.paginate(QueryExecutionId=execution_id):
        rows = page["ResultSet"]["Rows"]
        for i, row in enumerate(rows):
            cells = [c.get("VarCharValue", "") for c in row["Data"]]
            if first_page and i == 0:
                # First row of first page is the column header
                print(" | ".join(cells))
                print("-" * (sum(len(c) for c in cells) + 3 * (len(cells) - 1)))
            else:
                print(" | ".join(cells))
            first_page = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a SQL query against the pipeline Athena workgroup")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("sql", nargs="?", help="SQL query string")
    group.add_argument("--file", help="Path to a .sql file")
    args = parser.parse_args()

    if args.file:
        with open(args.file) as f:
            sql = f.read().strip()
    else:
        sql = args.sql

    run_query(sql)
