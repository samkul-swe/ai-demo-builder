#!/usr/bin/env python3
import os

import aws_cdk as cdk

from ai_demo_builder.ai_demo_builder_stack import AiDemoBuilderStack


app = cdk.App()

# Deploy to us-west-2 (your region)
AiDemoBuilderStack(
    app, 
    "AiDemoBuilderStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region='us-west-2'  # Your S3 bucket and resources are in us-west-2
    ),
    description="AI Demo Builder - Automated video generation platform"
)

app.synth()