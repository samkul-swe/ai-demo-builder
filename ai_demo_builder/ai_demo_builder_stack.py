"""
AI Demo Builder - PRODUCTION-READY CDK Stack
Matches actual project structure with lambda/ai/, lambda/analysis/, etc.
All resources ordered correctly with proper dependencies
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    Size,
    CfnOutput,
    BundlingOptions,
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
from pathlib import Path

# Import centralized configuration
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    S3_BUCKET_NAME,
    SESSIONS_TABLE,
    CACHE_TABLE,
    SQS_PROCESSING_QUEUE,
    SNS_NOTIFICATION_TOPIC,
    LAMBDA_EXECUTION_ROLE,
    LAMBDA_FUNCTIONS,
    LAMBDA_CONFIG,
    VIDEO_SETTINGS,
    get_service_lambda_env,
)

# Feature flag - set to False if layers/ffmpeg doesn't exist
USE_FFMPEG_LAYER = os.path.exists("layers/ffmpeg/python") or os.path.exists("layers/ffmpeg")


class AiDemoBuilderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        print(f"🔧 FFmpeg Layer: {'✅ ENABLED' if USE_FFMPEG_LAYER else '⚠️  DISABLED (video processing limited)'}")

        # ========================
        # PHASE 1: FOUNDATIONAL RESOURCES (No dependencies)
        # ========================
        
        # S3 Bucket - Create first, no dependencies
        self.demo_bucket = s3.Bucket(
            self, "AiDemoBuilderBucket",
            cors=[s3.CorsRule(
                allowed_methods=[
                    s3.HttpMethods.GET,
                    s3.HttpMethods.PUT,
                    s3.HttpMethods.POST,
                    s3.HttpMethods.DELETE
                ],
                allowed_origins=["*"],
                allowed_headers=["*"],
                max_age=3000
            )],
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED
        )

        # DynamoDB Tables - No dependencies
        self.sessions_table = dynamodb.Table(
            self, "AiDemoSessions",
            table_name="ai-demo-builder-sessions",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=False
        )

        self.cache_table = dynamodb.Table(
            self, "AiDemoCache",
            table_name="ai-demo-builder-cache",
            partition_key=dynamodb.Attribute(
                name="cacheKey",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=False
        )

        # SQS Queue - No dependencies
        processing_queue = sqs.Queue(
            self, "VideoProcessingQueue",
            visibility_timeout=Duration.seconds(LAMBDA_CONFIG["timeout_extra_long"]),
            retention_period=Duration.days(4),
            receive_message_wait_time=Duration.seconds(20)
        )

        # SNS Topic - No dependencies
        notification_topic = sns.Topic(
            self, "DemoNotifications",
            display_name="AI Demo Builder Notifications"
        )

        # ========================
        # PHASE 2: LAMBDA LAYER (Optional, depends on file system)
        # ========================
        
        if USE_FFMPEG_LAYER:
            ffmpeg_layer = lambda_.LayerVersion(
                self, "FFmpegLayer",
                code=lambda_.Code.from_asset("layers/ffmpeg"),
                compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
                description="FFmpeg and FFprobe binaries for video processing"
            )
        else:
            ffmpeg_layer = None

        # ========================
        # PHASE 3: IAM ROLE (Depends on foundational resources)
        # ========================
        
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            description="Execution role for AI Demo Builder Lambda functions"
        )

        # Grant permissions
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
        # PHASE 4: LAMBDA FUNCTIONS (Depend on IAM role and layer)
        # ========================
        
        # Helper function to create Lambda with local dependencies
        def create_lambda_with_deps(
            id: str,
            function_name: str,
            code_path: str,
            handler: str,
            timeout: int,
            memory: int,
            env_config: dict,
            layers: list = None,
            ephemeral_storage: int = None
        ):
            """Create Lambda function using locally installed dependencies"""
            
            # Use code from asset (includes package/ directory if it exists)
            code = lambda_.Code.from_asset(code_path)
            
            # Build Lambda config
            lambda_config = {
                "scope": self,
                "id": id,
                "function_name": function_name,
                "runtime": lambda_.Runtime.PYTHON_3_11,
                "handler": handler,
                "code": code,
                "role": lambda_role,
                "timeout": Duration.seconds(timeout),
                "memory_size": memory,
                "environment": {**common_env, **env_config}
            }
            
            if layers:
                lambda_config["layers"] = layers
            
            if ephemeral_storage:
                lambda_config["ephemeral_storage_size"] = Size.mebibytes(ephemeral_storage)
            
            return lambda_.Function(**lambda_config)
        
        # Common environment variables for all Lambda functions
        common_env = {
            "BUCKET_NAME": self.demo_bucket.bucket_name,
            "SESSIONS_TABLE": self.sessions_table.table_name,
            "CACHE_TABLE": self.cache_table.table_name,
            "SQS_QUEUE_URL": processing_queue.queue_url,
            "SNS_TOPIC_ARN": notification_topic.topic_arn,
        }

        # ====================
        # ANALYSIS PIPELINE (lambda/analysis/)
        # ====================
        
        github_fetcher = create_lambda_with_deps(
            id="GitHubFetcher",
            function_name=LAMBDA_FUNCTIONS["github_fetcher"],
            code_path="lambda/analysis/service-1-github-fetcher",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_long"],
            memory=LAMBDA_CONFIG["memory_large"],
            env_config=get_service_lambda_env("github_fetcher")
        )

        readme_parser = create_lambda_with_deps(
            id="ReadmeParser",
            function_name=LAMBDA_FUNCTIONS["readme_parser"],
            code_path="lambda/analysis/service-2-readme-parser",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_medium"],
            memory=LAMBDA_CONFIG["memory_medium"],
            env_config=get_service_lambda_env("readme_parser")
        )

        project_analyzer = create_lambda_with_deps(
            id="ProjectAnalyzer",
            function_name=LAMBDA_FUNCTIONS["project_analyzer"],
            code_path="lambda/analysis/service-3-project-analyzer",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_medium"],
            memory=LAMBDA_CONFIG["memory_medium"],
            env_config=get_service_lambda_env("project_analyzer")
        )

        cache_service = create_lambda_with_deps(
            id="CacheService",
            function_name=LAMBDA_FUNCTIONS["cache_service"],
            code_path="lambda/analysis/service-4-cache-service",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_short"],
            memory=LAMBDA_CONFIG["memory_small"],
            env_config=get_service_lambda_env("cache_service")
        )

        # ====================
        # AI & SESSION MANAGEMENT (lambda/ai/)
        # ====================
        
        ai_suggestion_service = create_lambda_with_deps(
            id="AiSuggestionService",
            function_name=LAMBDA_FUNCTIONS["ai_suggestion"],
            code_path="lambda/ai/service-5-ai-suggestion",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_long"],
            memory=LAMBDA_CONFIG["memory_large"],
            env_config=get_service_lambda_env("ai_suggestion")
        )

        session_creator = create_lambda_with_deps(
            id="SessionCreator",
            function_name=LAMBDA_FUNCTIONS["session_creator"],
            code_path="lambda/ai/service-6-session-creator",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_short"],
            memory=LAMBDA_CONFIG["memory_small"],
            env_config=get_service_lambda_env("session_creator")
        )

        # ====================
        # UPLOAD PIPELINE (lambda/upload/)
        # ====================
        
        upload_url_generator = create_lambda_with_deps(
            id="UploadUrlGenerator",
            function_name=LAMBDA_FUNCTIONS["upload_url_generator"],
            code_path="lambda/upload/service-7-upload-url-generator",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_short"],
            memory=LAMBDA_CONFIG["memory_small"],
            env_config=get_service_lambda_env("upload_url_generator")
        )
        
        upload_tracker = create_lambda_with_deps(
            id="UploadTracker",
            function_name=LAMBDA_FUNCTIONS["upload_tracker"],
            code_path="lambda/upload/service-8-upload-tracker",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_short"],
            memory=LAMBDA_CONFIG["memory_small"],
            env_config=get_service_lambda_env("upload_tracker")
        )

        # Video Validator - with optional FFmpeg layer
        video_validator = create_lambda_with_deps(
            id="VideoValidator",
            function_name=LAMBDA_FUNCTIONS["video_validator"],
            code_path="lambda/upload/service-9-video-validator",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_medium"],
            memory=LAMBDA_CONFIG["memory_medium"],
            env_config=get_service_lambda_env("video_validator"),
            layers=[ffmpeg_layer] if ffmpeg_layer else None
        )

        # Format Converter - with optional FFmpeg layer
        format_converter = create_lambda_with_deps(
            id="FormatConverter",
            function_name=LAMBDA_FUNCTIONS["format_converter"],
            code_path="lambda/upload/service-10-format-converter",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_long"],
            memory=LAMBDA_CONFIG["memory_large"],
            env_config=get_service_lambda_env("format_converter"),
            layers=[ffmpeg_layer] if ffmpeg_layer else None
        )

        # ====================
        # VIDEO PROCESSING (lambda/processing/)
        # ====================
        
        job_queue_service = create_lambda_with_deps(
            id="JobQueueService",
            function_name=LAMBDA_FUNCTIONS["job_queue"],
            code_path="lambda/processing/service-11-job-queue",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_medium"],
            memory=LAMBDA_CONFIG["memory_medium"],
            env_config=get_service_lambda_env("job_queue")
        )

        slide_creator = create_lambda_with_deps(
            id="SlideCreator",
            function_name=LAMBDA_FUNCTIONS["slide_creator"],
            code_path="lambda/processing/service-12-slide-creator",
            handler="index.lambda_handler",
            timeout=120,
            memory=LAMBDA_CONFIG["memory_large"],
            env_config=get_service_lambda_env("slide_creator"),
            ephemeral_storage=LAMBDA_CONFIG["ephemeral_storage"]
        )

        # Video Stitcher - with optional FFmpeg layer
        video_stitcher = create_lambda_with_deps(
            id="VideoStitcher",
            function_name=LAMBDA_FUNCTIONS["video_stitcher"],
            code_path="lambda/processing/service-13-video-stitcher",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_extra_long"],
            memory=LAMBDA_CONFIG["memory_xxlarge"],
            env_config=get_service_lambda_env("video_stitcher"),
            layers=[ffmpeg_layer] if ffmpeg_layer else None,
            ephemeral_storage=LAMBDA_CONFIG["ephemeral_storage_large"]
        )

        # Video Optimizer - with optional FFmpeg layer
        video_optimizer = create_lambda_with_deps(
            id="VideoOptimizer",
            function_name=LAMBDA_FUNCTIONS["video_optimizer"],
            code_path="lambda/processing/service-14-video-optimizer",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_extra_long"],
            memory=LAMBDA_CONFIG["memory_xxlarge"],
            env_config=get_service_lambda_env("video_optimizer"),
            layers=[ffmpeg_layer] if ffmpeg_layer else None,
            ephemeral_storage=LAMBDA_CONFIG["ephemeral_storage_large"]
        )

        # ====================
        # SUPPORT SERVICES (lambda/support/)
        # ====================
        
        notification_service = create_lambda_with_deps(
            id="NotificationService",
            function_name=LAMBDA_FUNCTIONS["notification_service"],
            code_path="lambda/support/service-15-notification",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_medium"],
            memory=LAMBDA_CONFIG["memory_medium"],
            env_config=get_service_lambda_env("notification_service")
        )

        status_tracker = create_lambda_with_deps(
            id="StatusTracker",
            function_name=LAMBDA_FUNCTIONS["status_tracker"],
            code_path="lambda/support/service-16-status-tracker",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_short"],
            memory=LAMBDA_CONFIG["memory_medium"],
            env_config=get_service_lambda_env("status_tracker")
        )

        cleanup_service = create_lambda_with_deps(
            id="CleanupService",
            function_name=LAMBDA_FUNCTIONS["cleanup_service"],
            code_path="lambda/support/service-17-cleanup",
            handler="index.lambda_handler",
            timeout=LAMBDA_CONFIG["timeout_long"],
            memory=LAMBDA_CONFIG["memory_large"],
            env_config=get_service_lambda_env("cleanup_service")
        )

        # ========================
        # PHASE 5: EVENT INTEGRATIONS (Depend on Lambda functions)
        # ========================
        
        # S3 Event Notification - Must be created AFTER Lambda function
        self.demo_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(upload_tracker),
            s3.NotificationKeyFilter(prefix="uploads/")
        )

        # EventBridge rule for cleanup
        cleanup_rule = events.Rule(
            self, "DailyCleanupRule",
            schedule=events.Schedule.cron(
                minute='0',
                hour='2',
                month='*',
                week_day='*',
                year='*'
            ),
            description="Daily cleanup of expired sessions and old files"
        )
        cleanup_rule.add_target(targets.LambdaFunction(cleanup_service))

        # ========================
        # PHASE 6: API GATEWAY (Depends on Lambda functions)
        # ========================
        
        api = apigateway.RestApi(
            self, "AiDemoBuilderApi",
            rest_api_name="AI Demo Builder API",
            description="REST API for AI Demo Builder",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["*"]
            ),
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=200
            )
        )

        # API Routes
        analyze = api.root.add_resource("analyze")
        analyze.add_method("POST", apigateway.LambdaIntegration(github_fetcher))

        suggestions = api.root.add_resource("suggestions")
        suggestions.add_method("POST", apigateway.LambdaIntegration(ai_suggestion_service))

        upload_url = api.root.add_resource("upload-url")
        upload_url.add_method("POST", apigateway.LambdaIntegration(upload_url_generator))

        status_resource = api.root.add_resource("status")
        status_by_id = status_resource.add_resource("{session_id}")
        status_by_id.add_method("GET", apigateway.LambdaIntegration(status_tracker))

        generate = api.root.add_resource("generate")
        generate_by_id = generate.add_resource("{session_id}")
        generate_by_id.add_method("POST", apigateway.LambdaIntegration(job_queue_service))

        # ========================
        # PHASE 7: OUTPUTS
        # ========================
        
        CfnOutput(self, "ApiEndpoint", 
                  value=api.url, 
                  description="API Gateway endpoint URL",
                  export_name=f"{self.stack_name}-ApiEndpoint")
        
        CfnOutput(self, "S3BucketName", 
                  value=self.demo_bucket.bucket_name, 
                  description="S3 bucket for video storage",
                  export_name=f"{self.stack_name}-BucketName")
        
        CfnOutput(self, "SessionsTableName", 
                  value=self.sessions_table.table_name, 
                  description="DynamoDB table for sessions",
                  export_name=f"{self.stack_name}-SessionsTable")
        
        CfnOutput(self, "CacheTableName", 
                  value=self.cache_table.table_name, 
                  description="DynamoDB table for caching",
                  export_name=f"{self.stack_name}-CacheTable")
        
        CfnOutput(self, "SQSQueueUrl", 
                  value=processing_queue.queue_url, 
                  description="SQS queue for video processing",
                  export_name=f"{self.stack_name}-QueueUrl")
        
        CfnOutput(self, "SNSTopicArn", 
                  value=notification_topic.topic_arn, 
                  description="SNS topic for notifications",
                  export_name=f"{self.stack_name}-TopicArn")
        
        CfnOutput(self, "FFmpegLayerStatus",
                  value="ENABLED" if USE_FFMPEG_LAYER else "DISABLED",
                  description="FFmpeg layer availability status")
        
        print(f"✅ Stack configuration complete - {17} Lambda functions configured")