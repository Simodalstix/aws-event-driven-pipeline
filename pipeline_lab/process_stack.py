import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_event_sources,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_ssm as ssm,
)
from constructs import Construct


class ProcessStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Account suffix keeps the bucket name globally unique without hardcoding
        bucket = s3.Bucket(
            self, "DataBucket",
            bucket_name=f"ops-lab-pipeline-data-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=cdk.Duration.days(30),
                        )
                    ]
                )
            ],
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        cw_policy_arn = ssm.StringParameter.value_for_string_parameter(
            self, "/ops-lab/shared/cloudwatch-write-policy-arn"
        )

        role = iam.Role(
            self, "ProcessorRole",
            role_name="ops-lab-pipeline-processor-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(
                    self, "CwWritePolicy", cw_policy_arn
                )
            ],
        )

        queue_arn = ssm.StringParameter.value_for_string_parameter(
            self, "/ops-lab/pipeline/sqs-queue-arn"
        )
        queue = sqs.Queue.from_queue_arn(self, "IngestQueue", queue_arn)

        log_group = logs.LogGroup(
            self, "ProcessorLogGroup",
            log_group_name="/ops-lab/pipeline/processor",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        fn = lambda_.Function(
            self, "Processor",
            function_name="ops-lab-pipeline-processor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("lambda/processor"),
            handler="handler.handler",
            timeout=cdk.Duration.seconds(10),
            memory_size=256,
            role=role,
            log_group=log_group,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
            },
        )

        bucket.grant_write(fn)

        fn.add_event_source(
            lambda_event_sources.SqsEventSource(queue, batch_size=10)
        )

        ssm.StringParameter(self, "BucketNameParam",
            parameter_name="/ops-lab/pipeline/s3-bucket-name",
            string_value=bucket.bucket_name,
        )
