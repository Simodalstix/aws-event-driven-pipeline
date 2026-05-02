import json

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_athena as athena,
    aws_glue as glue,
    aws_iam as iam,
    aws_s3 as s3,
    aws_scheduler as scheduler,
    aws_ssm as ssm,
)
from constructs import Construct


class AnalyticsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        bucket_name = ssm.StringParameter.value_for_string_parameter(
            self, "/ops-lab/pipeline/s3-bucket-name"
        )

        # --- Glue ---

        database = glue.CfnDatabase(
            self, "GlueDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="ops-lab-pipeline",
                description="Pipeline event data lake",
            ),
        )

        # Glue needs to read S3 and write to the Glue catalog
        crawler_role = iam.Role(
            self, "CrawlerRole",
            role_name="ops-lab-pipeline-crawler-role",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole"),
            ],
        )
        # Grant read access to the data bucket (bucket name is a deploy-time token)
        crawler_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket"],
            resources=[
                f"arn:aws:s3:::{bucket_name}",
                f"arn:aws:s3:::{bucket_name}/*",
            ],
        ))

        crawler = glue.CfnCrawler(
            self, "Crawler",
            name="ops-lab-pipeline-crawler",
            role=crawler_role.role_arn,
            database_name="ops-lab-pipeline",
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[
                    glue.CfnCrawler.S3TargetProperty(path=f"s3://{bucket_name}/")
                ]
            ),
            # Schema change policy: update table, don't delete on schema drift
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE",
                delete_behavior="LOG",
            ),
            configuration=json.dumps({
                "Version": 1.0,
                "Grouping": {"TableGroupingPolicy": "CombineCompatibleSchemas"},
            }),
        )
        crawler.node.add_dependency(database)

        # --- Athena ---

        results_bucket = s3.Bucket(
            self, "AthenaResultsBucket",
            bucket_name=f"ops-lab-pipeline-athena-results-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(expiration=cdk.Duration.days(30))
            ],
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        athena.CfnWorkGroup(
            self, "AthenaWorkgroup",
            name="ops-lab-pipeline",
            description="Pipeline analytics workgroup",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{results_bucket.bucket_name}/results/",
                ),
                # Fail queries that would scan more than 1 GB — guards against runaway scans
                bytes_scanned_cutoff_per_query=1_073_741_824,
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics_enabled=True,
            ),
        )

        # --- EventBridge Scheduler (daily crawler trigger) ---

        scheduler_role = iam.Role(
            self, "SchedulerRole",
            role_name="ops-lab-pipeline-scheduler-role",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )
        scheduler_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:StartCrawler"],
            resources=[
                f"arn:aws:glue:{self.region}:{self.account}:crawler/ops-lab-pipeline-crawler"
            ],
        ))

        scheduler.CfnSchedule(
            self, "CrawlerSchedule",
            name="ops-lab-pipeline-crawler-daily",
            # Run at 01:00 UTC daily — after typical overnight data arrival
            schedule_expression="cron(0 1 * * ? *)",
            schedule_expression_timezone="UTC",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="OFF",
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn="arn:aws:scheduler:::aws-sdk:glue/startCrawler",
                role_arn=scheduler_role.role_arn,
                input=json.dumps({"Name": "ops-lab-pipeline-crawler"}),
            ),
        )

        # --- SSM outputs ---

        ssm.StringParameter(self, "GlueDatabaseParam",
            parameter_name="/ops-lab/pipeline/glue-database-name",
            string_value="ops-lab-pipeline",
        )
        ssm.StringParameter(self, "AthenaWorkgroupParam",
            parameter_name="/ops-lab/pipeline/athena-workgroup",
            string_value="ops-lab-pipeline",
        )
