"""
AI Demo Builder - Complete AWS CDK Stack
Uses centralized configuration from config.py
All 17 services properly configured
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
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct
import sys
import os

# Import centralized configuration
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    S3_BUCKET_NAME,
    DYNAMODB_SESSIONS_TABLE,
    DYNAMODB_CACHE_TABLE,
    SQS_PROCESSING_QUEUE,
    SNS_NOTIFICATION_TOPIC,
    LAMBDA_EXECUTION_ROLE,
    LAMBDA_FUNCTIONS,
    LAMBDA_CONFIG,
    VIDEO_SETTINGS,
    get_service_lambda_env,
)


class AiDemoBuilderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================
        # STORAGE LAYER
        # ========================
        
        # S3 Bucket for video storage
        self.demo_bucket = s3.Bucket(
            self, "AiDemoBuilderBucket",
            bucket_name=S3_BUCKET_NAME,  # From config.py
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
            table_name=DYNAMODB_SESSIONS_TABLE,  # From config.py
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY
        )

        # DynamoDB Table for caching
        self.cache_table = dynamodb.Table(
            self, "AiDemoCache",
            table_name=DYNAMODB_CACHE_TABLE,  # From config.py
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
            queue_name=SQS_PROCESSING_QUEUE,  # From config.py
            visibility_timeout=Duration.seconds(LAMBDA_CONFIG["timeout_extra_long"]),  # From config.py
            retention_period=Duration.days(4)
        )

        # SNS Topic for notifications
        notification_topic = sns.Topic(
            self, "DemoNotifications",
            topic_name=SNS_NOTIFICATION_TOPIC,  # From config.py
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
            role_name=LAMBDA_EXECUTION_ROLE,  # From config.py
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant permissions to Lambda role
        self.demo_bucket.grant_read_write(lambda_role)
        self.demo_bucket.grant_delete(lambda_role)
        self.sessions_table.grant_read_write_data(lambda_role)
        self.cache_table.grant_read_write_data(lambda_role)
        processing_queue.grant_send_messages(lambda_role)
        processing_queue.grant_consume_messages(lambda_role)
        notification_topic.grant_publish(lambda_role)

        # Grant Lambda invocation permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:service-*"]
            )
        )

        # ========================
        # PERSON 1: ANALYSIS PIPELINE (Services 1-4)
        # ========================
        
        # Service 2: README Parser
        readme_parser = lambda_.Function(
            self, "ReadmeParser",
            function_name=LAMBDA_FUNCTIONS["readme_parser"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis/service-2-readme-parser"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_medium"]),  # From config.py
            memory_size=LAMBDA_CONFIG["memory_medium"],  # From config.py
            environment=get_service_lambda_env("readme_parser")  # From config.py
        )

        # Service 3: Project Analyzer
        project_analyzer = lambda_.Function(
            self, "ProjectAnalyzer",
            function_name=LAMBDA_FUNCTIONS["project_analyzer"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis/service-3-project-analyzer"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_medium"]),
            memory_size=LAMBDA_CONFIG["memory_medium"],
            environment=get_service_lambda_env("project_analyzer")
        )

        # Service 4: Cache Service
        cache_service = lambda_.Function(
            self, "CacheService",
            function_name=LAMBDA_FUNCTIONS["cache_service"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis/service-4-cache-service"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_short"]),
            memory_size=LAMBDA_CONFIG["memory_small"],
            environment=get_service_lambda_env("cache_service")
        )

        # Service 1: GitHub Fetcher
        github_fetcher = lambda_.Function(
            self, "GitHubFetcher",
            function_name=LAMBDA_FUNCTIONS["github_fetcher"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis/service-1-github-fetcher"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_medium"]),
            memory_size=LAMBDA_CONFIG["memory_large"],
            environment=get_service_lambda_env("github_fetcher")
        )

        # ========================
        # PERSON 2: AI & SESSION MANAGEMENT (Services 5-6)
        # ========================
        
        # Service 6: Session Creator
        session_creator = lambda_.Function(
            self, "SessionCreator",
            function_name=LAMBDA_FUNCTIONS["session_creator"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/ai/service-6-session-creator"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_medium"]),
            memory_size=LAMBDA_CONFIG["memory_medium"],
            environment=get_service_lambda_env("session_creator")
        )
        
        # Service 5: AI Suggestion Service
        ai_suggestion_service = lambda_.Function(
            self, "AiSuggestionService",
            function_name=LAMBDA_FUNCTIONS["ai_suggestion"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/ai/service-5-ai-suggestion"),
            role=lambda_role,
            timeout=Duration.seconds(90),
            memory_size=LAMBDA_CONFIG["memory_large"],
            environment=get_service_lambda_env("ai_suggestion")
        )

        # ========================
        # PERSON 3: UPLOAD PIPELINE (Services 7-10)
        # ========================
        
        # Service 7: Upload URL Generator
        upload_url_generator = lambda_.Function(
            self, "UploadUrlGenerator",
            function_name=LAMBDA_FUNCTIONS["upload_url_generator"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-7-upload-url-generator"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_short"]),
            memory_size=LAMBDA_CONFIG["memory_medium"],
            environment=get_service_lambda_env("upload_url_generator")
        )
        
        # Service 8: Upload Tracker
        upload_tracker = lambda_.Function(
            self, "UploadTracker",
            function_name=LAMBDA_FUNCTIONS["upload_tracker"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-8-upload-tracker"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_medium"]),
            memory_size=LAMBDA_CONFIG["memory_medium"],
            environment=get_service_lambda_env("upload_tracker")
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

        # Service 9: Video Validator
        video_validator = lambda_.Function(
            self, "VideoValidator",
            function_name=LAMBDA_FUNCTIONS["video_validator"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-9-video-validator"),
            role=lambda_role,
            layers=[ffmpeg_layer],
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_long"]),
            memory_size=LAMBDA_CONFIG["memory_xlarge"],
            ephemeral_storage_size=Size.mebibytes(LAMBDA_CONFIG["ephemeral_storage"]),
            environment=get_service_lambda_env("video_validator")
        )

        # Service 10: Format Converter
        format_converter = lambda_.Function(
            self, "FormatConverter",
            function_name=LAMBDA_FUNCTIONS["format_converter"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload/service-10-format-converter"),
            role=lambda_role,
            layers=[ffmpeg_layer],
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_long"]),
            memory_size=LAMBDA_CONFIG["memory_xlarge"],
            ephemeral_storage_size=Size.mebibytes(LAMBDA_CONFIG["ephemeral_storage"]),
            environment={
                **get_service_lambda_env("format_converter"),
                "SQS_QUEUE_URL": processing_queue.queue_url  # Add after queue creation
            }
        )

        # ========================
        # PERSON 4: VIDEO PROCESSING (Services 11-14)
        # ========================
        
        # Service 11: Job Queue Service
        job_queue_service = lambda_.Function(
            self, "JobQueueService",
            function_name=LAMBDA_FUNCTIONS["job_queue"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/processing/service-11-job-queue"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_medium"]),
            memory_size=LAMBDA_CONFIG["memory_medium"],
            environment={
                **get_service_lambda_env("job_queue"),
                "SQS_QUEUE_URL": processing_queue.queue_url
            }
        )

        # Service 12: Slide Creator
        slide_creator = lambda_.Function(
            self, "SlideCreator",
            function_name=LAMBDA_FUNCTIONS["slide_creator"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/processing/service-12-slide-creator"),
            role=lambda_role,
            timeout=Duration.seconds(120),
            memory_size=LAMBDA_CONFIG["memory_large"],
            ephemeral_storage_size=Size.mebibytes(LAMBDA_CONFIG["ephemeral_storage"]),
            environment=get_service_lambda_env("slide_creator")
        )

        # Service 13: Video Stitcher
        video_stitcher = lambda_.Function(
            self, "VideoStitcher",
            function_name=LAMBDA_FUNCTIONS["video_stitcher"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/processing/service-13-video-stitcher"),
            role=lambda_role,
            layers=[ffmpeg_layer],
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_extra_long"]),
            memory_size=LAMBDA_CONFIG["memory_xxlarge"],
            ephemeral_storage_size=Size.mebibytes(LAMBDA_CONFIG["ephemeral_storage_large"]),
            environment=get_service_lambda_env("video_stitcher")
        )

        # Service 14: Video Optimizer
        video_optimizer = lambda_.Function(
            self, "VideoOptimizer",
            function_name=LAMBDA_FUNCTIONS["video_optimizer"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/processing/service-14-video-optimizer"),
            role=lambda_role,
            layers=[ffmpeg_layer],
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_extra_long"]),
            memory_size=LAMBDA_CONFIG["memory_xxlarge"],
            ephemeral_storage_size=Size.mebibytes(LAMBDA_CONFIG["ephemeral_storage_large"]),
            environment=get_service_lambda_env("video_optimizer")
        )

        # ========================
        # PERSON 5: SUPPORT SERVICES (Services 15-17)
        # ========================
        
        # Service 15: Notification Service
        notification_service = lambda_.Function(
            self, "NotificationService",
            function_name=LAMBDA_FUNCTIONS["notification_service"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/support/service-15-notification"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_medium"]),
            memory_size=LAMBDA_CONFIG["memory_medium"],
            environment={
                **get_service_lambda_env("notification_service"),
                "SNS_TOPIC_ARN": notification_topic.topic_arn
            }
        )

        # Service 16: Status Tracker
        status_tracker = lambda_.Function(
            self, "StatusTracker",
            function_name=LAMBDA_FUNCTIONS["status_tracker"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/support/service-16-status-tracker"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_short"]),
            memory_size=LAMBDA_CONFIG["memory_medium"],
            environment=get_service_lambda_env("status_tracker")
        )

        # Service 17: Cleanup Service
        cleanup_service = lambda_.Function(
            self, "CleanupService",
            function_name=LAMBDA_FUNCTIONS["cleanup_service"],  # From config.py
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/support/service-17-cleanup"),
            role=lambda_role,
            timeout=Duration.seconds(LAMBDA_CONFIG["timeout_long"]),
            memory_size=LAMBDA_CONFIG["memory_large"],
            environment=get_service_lambda_env("cleanup_service")
        )

        # Schedule cleanup to run daily at 2 AM UTC
        cleanup_rule = events.Rule(
            self, "DailyCleanupRule",
            schedule=events.Schedule.cron(
                minute='0',
                hour='2',
                month='*',
                week_day='*',
                year='*'
            )
        )
        cleanup_rule.add_target(targets.LambdaFunction(cleanup_service))

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

        # GET /status/{session_id} - Get session status
        status_resource = api.root.add_resource("status")
        status_by_id = status_resource.add_resource("{session_id}")
        status_by_id.add_method(
            "GET",
            apigateway.LambdaIntegration(status_tracker)
        )

        # POST /generate/{session_id} - Trigger video generation
        generate = api.root.add_resource("generate")
        generate_by_id = generate.add_resource("{session_id}")
        generate_by_id.add_method(
            "POST",
            apigateway.LambdaIntegration(job_queue_service)
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