"""
AI Demo Builder - Complete AWS CDK Stack
Includes all services with proper caching configuration
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    Size,
    CfnOutput,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_iam as iam,
    aws_s3_notifications as s3n,
)
from constructs import Construct


class AiDemoBuilderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================
        # STORAGE LAYER
        # ========================
        
        # S3 Bucket for video storage
        self.demo_bucket = s3.Bucket(
            self, "AiDemoBuilderBucket",
            bucket_name="ai-demo-builder",
            cors=[s3.CorsRule(
                allowed_methods=[
                    s3.HttpMethods.GET,
                    s3.HttpMethods.PUT,
                    s3.HttpMethods.POST
                ],
                allowed_origins=["*"],
                allowed_headers=["*"]
            )],
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # DynamoDB Table for demo sessions
        self.sessions_table = dynamodb.Table(
            self, "AiDemoSessions",
            table_name="ai-demo-sessions",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY
        )

        # DynamoDB Table for caching (GitHub analysis & AI suggestions)
        self.cache_table = dynamodb.Table(
            self, "AiDemoCache",
            table_name="ai-demo-cache",
            partition_key=dynamodb.Attribute(
                name="cacheKey",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY
        )

        # ========================
        # MESSAGING & QUEUING
        # ========================
        
        # SQS Queue for video processing jobs
        processing_queue = sqs.Queue(
            self, "VideoProcessingQueue",
            queue_name="video-processing-queue",
            visibility_timeout=Duration.seconds(900),
            retention_period=Duration.days(4)
        )

        # SNS Topic for notifications
        notification_topic = sns.Topic(
            self, "DemoNotifications",
            topic_name="demo-notifications",
            display_name="AI Demo Builder Notifications"
        )

        # ========================
        # LAMBDA LAYER (FFmpeg)
        # ========================
        
        ffmpeg_layer = lambda_.LayerVersion(
            self, "FFmpegLayer",
            code=lambda_.Code.from_asset("layers/ffmpeg"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="FFmpeg and FFprobe binaries for video processing"
        )

        # ========================
        # IAM ROLE FOR LAMBDA FUNCTIONS
        # ========================
        
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            role_name="lambda-execution-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant permissions to Lambda role
        self.demo_bucket.grant_read_write(lambda_role)
        self.sessions_table.grant_read_write_data(lambda_role)
        self.cache_table.grant_read_write_data(lambda_role)
        processing_queue.grant_send_messages(lambda_role)
        processing_queue.grant_consume_messages(lambda_role)
        notification_topic.grant_publish(lambda_role)

        # Grant Lambda invocation permissions (for service-to-service calls)
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:service-*"]
            )
        )

        # ========================
        # PERSON 1: ANALYSIS PIPELINE
        # ========================
        
        # Service 2: README Parser
        readme_parser = lambda_.Function(
            self, "ReadmeParser",
            function_name="service-2-readme-parser",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis/service-2-readme-parser"),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=256
        )

        # Service 3: Project Analyzer
        project_analyzer = lambda_.Function(
            self, "ProjectAnalyzer",
            function_name="service-3-project-analyzer",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis/service-3-project-analyzer"),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=256
        )

        # Service 4: Cache Service
        cache_service = lambda_.Function(
            self, "CacheService",
            function_name="service-4-cache-service",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/support/service-4-cache-service"),
            role=lambda_role,
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "DYNAMODB_TABLE": self.cache_table.table_name
            }
        )

        # Service 1: GitHub Fetcher (orchestrates 2, 3, 4)
        github_fetcher = lambda_.Function(
            self, "GitHubFetcher",
            function_name="service-1-github-fetcher",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis/service-1-github-fetcher"),
            role=lambda_role,
            timeout=Duration.seconds(60),
            memory_size=512,
            environment={
                "GITHUB_TOKEN": "",  # Add via console after deployment
            }
        )

        # ========================
        # PERSON 2: AI & SESSION MANAGEMENT
        # ========================
        
        # Service 5: AI Suggestion Service
        ai_suggestion_service = lambda_.Function(
            self, "AiSuggestionService",
            function_name="service-5-ai-suggestion",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/ai/service-5-ai-suggestion"),
            role=lambda_role,
            timeout=Duration.seconds(90),
            memory_size=512,
            environment={
                "GEMINI_API_KEY": "",  # Add via console after deployment
                "SERVICE4_FUNCTION_NAME": "service-4-cache-service",
                "SERVICE6_FUNCTION_NAME": "service-6-session-creator"
            }
        )

        # Service 6: Session Creator (placeholder - implement later)
        # Service 7: Suggestion Organizer (placeholder - implement later)

        # ========================
        # PERSON 3: UPLOAD PIPELINE (Your working services)
        # ========================
        
        # Service 8: Upload URL Generator
        upload_url_generator = lambda_.Function(
            self, "UploadUrlGenerator",
            function_name="service-8-upload-url-generator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-8-upload-url-generator"),
            role=lambda_role,
            timeout=Duration.seconds(10),
            memory_size=256,
            environment={
                "S3_BUCKET": self.demo_bucket.bucket_name,
                "DYNAMODB_TABLE": self.sessions_table.table_name
            }
        )

        # Service 9: Upload Tracker
        upload_tracker = lambda_.Function(
            self, "UploadTracker",
            function_name="service-9-upload-tracker",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-9-upload-tracker"),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "DYNAMODB_TABLE": self.sessions_table.table_name
            }
        )

        # Service 10: Video Validator
        video_validator = lambda_.Function(
            self, "VideoValidator",
            function_name="service-10-video-validator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-10-video-validator"),
            role=lambda_role,
            layers=[ffmpeg_layer],
            timeout=Duration.seconds(300),
            memory_size=1024,
            environment={
                "S3_BUCKET": self.demo_bucket.bucket_name,
                "DYNAMODB_TABLE": self.sessions_table.table_name
            }
        )

        # Service 11: Format Converter
        format_converter = lambda_.Function(
            self, "FormatConverter",
            function_name="service-11-format-converter",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-11-format-converter"),
            role=lambda_role,
            layers=[ffmpeg_layer],
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(2048),
            environment={
                "S3_BUCKET": self.demo_bucket.bucket_name,
                "DYNAMODB_TABLE": self.sessions_table.table_name
            }
        )

        # S3 Event Notification to trigger upload tracker
        self.demo_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(upload_tracker),
            s3.NotificationKeyFilter(
                prefix="videos/",
                suffix=".mp4"
            )
        )

        # ========================
        # API GATEWAY
        # ========================
        
        api = apigateway.RestApi(
            self, "AiDemoBuilderApi",
            rest_api_name="AI Demo Builder API",
            description="REST API for AI Demo Builder",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS
            )
        )

        # POST /analyze - Analyze GitHub repository
        analyze = api.root.add_resource("analyze")
        analyze.add_method(
            "POST",
            apigateway.LambdaIntegration(github_fetcher)
        )

        # POST /suggestions - Generate AI suggestions
        suggestions = api.root.add_resource("suggestions")
        suggestions.add_method(
            "POST",
            apigateway.LambdaIntegration(ai_suggestion_service)
        )

        # POST /upload-url - Get presigned upload URL
        upload_url = api.root.add_resource("upload-url")
        upload_url.add_method(
            "POST",
            apigateway.LambdaIntegration(upload_url_generator)
        )

        # ========================
        # OUTPUTS
        # ========================
        
        CfnOutput(
            self, "ApiEndpoint",
            value=api.url,
            description="API Gateway endpoint URL"
        )

        CfnOutput(
            self, "S3BucketName",
            value=self.demo_bucket.bucket_name,
            description="S3 bucket for video storage"
        )

        CfnOutput(
            self, "SessionsTableName",
            value=self.sessions_table.table_name,
            description="DynamoDB table for sessions"
        )

        CfnOutput(
            self, "CacheTableName",
            value=self.cache_table.table_name,
            description="DynamoDB table for caching"
        )

        CfnOutput(
            self, "SQSQueueUrl",
            value=processing_queue.queue_url,
            description="SQS queue for video processing"
        )

        CfnOutput(
            self, "SNSTopicArn",
            value=notification_topic.topic_arn,
            description="SNS topic for notifications"
        )