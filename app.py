import aws_cdk as cdk
from pipeline_lab.ingest_stack import IngestStack
from pipeline_lab.process_stack import ProcessStack
from pipeline_lab.analytics_stack import AnalyticsStack

app = cdk.App()

env = cdk.Environment(account="820242933814", region="ap-southeast-2")

ingest = IngestStack(app, "IngestStack", env=env)
process = ProcessStack(app, "ProcessStack", env=env)
analytics = AnalyticsStack(app, "AnalyticsStack", env=env)

for stack in [ingest, process, analytics]:
    cdk.Tags.of(stack).add("Project", "ops-lab")
    cdk.Tags.of(stack).add("Stack", "pipeline")
    cdk.Tags.of(stack).add("Environment", "lab")

app.synth()
