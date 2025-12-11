import aws_cdk as core
import aws_cdk.assertions as assertions

from ai_demo_builder.ai_demo_builder_stack import AiDemoBuilderStack

# example tests. To run these tests, uncomment this file along with the example
# resource in ai_demo_builder/ai_demo_builder_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = AiDemoBuilderStack(app, "ai-demo-builder")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
