import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_sqs as sqs,
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_ssm as ssm,
)
from constructs import Construct


class IngestStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        dlq = sqs.Queue(
            self, "Dlq",
            queue_name="ops-lab-pipeline-dlq",
            retention_period=cdk.Duration.days(14),
        )

        # Visibility timeout = 60s (6× a 10s Lambda timeout; adjust in Phase 2 if needed)
        queue = sqs.Queue(
            self, "Queue",
            queue_name="ops-lab-pipeline-queue",
            visibility_timeout=cdk.Duration.seconds(60),
            retention_period=cdk.Duration.days(4),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )

        sns_topic_arn = ssm.StringParameter.value_for_string_parameter(
            self, "/ops-lab/shared/sns-topic-arn"
        )
        alert_topic = sns.Topic.from_topic_arn(self, "AlertTopic", sns_topic_arn)

        dlq_alarm = cw.Alarm(
            self, "DlqDepthAlarm",
            alarm_name="ops-lab-pipeline-dlq-depth",
            alarm_description="DLQ has messages — processor failures need investigation",
            metric=dlq.metric_approximate_number_of_messages_visible(
                statistic="Maximum",
                period=cdk.Duration.minutes(1),
            ),
            threshold=0,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        dlq_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        ssm.StringParameter(self, "QueueUrlParam",
            parameter_name="/ops-lab/pipeline/sqs-queue-url",
            string_value=queue.queue_url,
        )
        ssm.StringParameter(self, "QueueArnParam",
            parameter_name="/ops-lab/pipeline/sqs-queue-arn",
            string_value=queue.queue_arn,
        )
        ssm.StringParameter(self, "DlqUrlParam",
            parameter_name="/ops-lab/pipeline/dlq-url",
            string_value=dlq.queue_url,
        )
