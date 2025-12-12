"""
AI Demo Builder - Complete AWS CDK Stack
FIXED VERSION with correct imports and paths
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
    aws_lambda_event_sources as lambda_sources,
)
from constructs import Construct
import os

# ========================
# INLINE CONFIGURATION (Instead of importing)
# ========================
# This avoids import path issues

S3_BUCKET_NAME = "ai-demo-builder"
DYNAMODB_SESSIONS_TABLE = "ai-demo-sessions"
DYNAMODB_CACHE_TABLE = "ai-demo-cache"
SQS_PROCESSING_QUEUE = "video-processing-queue"
SNS_NOTIFICATION_TOPIC = "demo-notifications"
LAMBDA_EXECUTION_ROLE = "lambda-execution-role"

# Lambda function names
LAMBDA_FUNCTIONS = {
    "github_fetcher": "service-1-github-fetcher",
    "readme_parser": "service-2-readme-parser",
    "project_analyzer": "service-3-project-analyzer",
    "cache_service": "service-4-cache-service",
    "ai_suggestion": "service-5-ai-suggestion",
    "session_creator": "service-6-session-creator",
    "upload_url_generator": "service-7-upload-url-generator",
    "upload_tracker": "service-8-upload-tracker",
    "video_validator": "service-9-video-validator",
    "format_converter": "service-10-format-converter",
    "job_queue": "service-11-job-queue",
    "slide_creator": "service-12-slide-creator",
    "video_stitcher": "service-13-video-stitcher",
    "video_optimizer": "service-14-video-optimizer",
    "notification_service": "service-15-notification",
    "status_tracker": "service-16-status-tracker",
    "cleanup_service": "service-17-cleanup"
}

# Lambda configuration
LAMBDA_CONFIG = {
    "timeout_short": 10,
    "timeout_medium": 30,
    "timeout_long": 300,
    "timeout_extra_long": 900,
    "memory_small": 128,
    "memory_medium": 256,
    "memory_large": 512,
    "memory_xlarge": 1024,
    "memory_xxlarge": 3008,
    "ephemeral_storage": 512,
    "ephemeral_storage_large": 10240,
}


class AiDemoBuilderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================
        # STORAGE LAYER
        # ========================
        
        self.demo_bucket = s3.Bucket(
            self, "AiDemoBuilderBucket",
            bucket_name=S3_BUCKET_NAME,
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

        # DynamoDB Tables
        self.sessions_table = dynamodb.Table(
            self, "AiDemoSessions",
            table_name=DYNAMODB_SESSIONS_TABLE,
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY
        )

        self.cache_table = dynamodb.Table(
            self, "AiDemoCache",
            table_name=DYNAMODB_CACHE_TABLE,
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
        
        processing_queue = sqs.Queue(
            self, "VideoProcessingQueue",
            queue_name=SQS_PROCESSING_QUEUE,
            visibility_timeout=Duration.seconds(LAMBDA_CONFIG["timeout_extra_long"]),
            retention_period=Duration.days(4)
        )

        notification_topic = sns.Topic(
            self, "DemoNotifications",
            topic_name=SNS_NOTIFICATION_TOPIC,
            display_name="AI Demo Builder Notifications"
        )

        # ========================
        # LAMBDA LAYER (FFmpeg)
        # ========================
        
        # Check if FFmpeg layer directory exists
        layer_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "layers",
            "ffmpeg"
        )
        
        ffmpeg_layer = None
        if os.path.exists(layer_path):
            ffmpeg_layer = lambda_.LayerVersion(
                self, "FFmpegLayer",
                code=lambda_.Code.from_asset("../layers/ffmpeg"),
                compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
                description="FFmpeg and FFprobe binaries for video processing"
            )
            print("✅ FFmpeg layer will be created")
        else:
            print("⚠️  WARNING: FFmpeg layer directory not found at layers/ffmpeg")
            print("   Services 9, 10, 13, 14 will fail without FFmpeg!")
            print("   Run: ./setup-ffmpeg-layer.sh")

        # ========================
        # IAM ROLE FOR LAMBDA FUNCTIONS
        # ========================
        
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            role_name=LAMBDA_EXECUTION_ROLE,
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
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
        # HELPER: Create Lambda Function
        # ========================
        
        def create_lambda(name, path, timeout, memory, needs_ffmpeg=False, ephemeral_mb=512):
            """Helper to create Lambda function with consistent config"""
            
            layers = []
            if needs_ffmpeg and ffmpeg_layer:
                layers.append(ffmpeg_layer)
            
            env_vars = {
                "S3_BUCKET": self.demo_bucket.bucket_name,
                "DYNAMODB_TABLE": self.sessions_table.table_name,
                "CACHE_TABLE": self.cache_table.table_name,
                "SQS_QUEUE_URL": processing_queue.queue_url,
                "SNS_TOPIC_ARN": notification_topic.topic_arn,
            }
            
            # Add service-specific env vars
            service_env = self._get_service_env(name)
            env_vars.update(service_env)
            
            return lambda_.Function(
                self, name.replace("-", "").title(),
                function_name=name,
                runtime=lambda_.Runtime.PYTHON_3_11,
                handler="index.lambda_handler",
                code=lambda_.Code.from_asset(path),
                role=lambda_role,
                timeout=Duration.seconds(timeout),
                memory_size=memory,
                layers=layers if layers else None,
                ephemeral_storage_size=Size.mebibytes(ephemeral_mb) if ephemeral_mb > 512 else None,
                environment=env_vars
            )
        
        # ========================
        # CREATE ALL 17 SERVICES
        # ========================
        
        # ========================
        # DETERMINE CORRECT PATH PREFIX
        # ========================
        
        # CDK stack is in ai_demo_builder/ directory
        # Lambda code is in lambda/ directory (sibling to ai_demo_builder/)
        # So we need to go up one level: ../lambda/
        
        lambda_base_path = os.path.join(
            os.path.dirname(__file__),  # ai_demo_builder/
            "..",                        # go up to project root
            "lambda"                     # then into lambda/
        )
        
        # Verify the path exists
        if not os.path.exists(lambda_base_path):
            raise Exception(f"Lambda directory not found at: {lambda_base_path}")
        
        print(f"✅ Lambda base path: {lambda_base_path}")
        
        # ========================
        # SERVICE 1-4: ANALYSIS PIPELINE
        # ========================
        
        readme_parser = create_lambda(
            LAMBDA_FUNCTIONS["readme_parser"],
            os.path.join(lambda_base_path, "analysis/service-2-readme-parser"),
            LAMBDA_CONFIG["timeout_medium"],
            LAMBDA_CONFIG["memory_medium"]
        )
        
        project_analyzer = create_lambda(
            LAMBDA_FUNCTIONS["project_analyzer"],
            os.path.join(lambda_base_path, "analysis/service-3-project-analyzer"),
            LAMBDA_CONFIG["timeout_medium"],
            LAMBDA_CONFIG["memory_medium"]
        )
        
        cache_service = create_lambda(
            LAMBDA_FUNCTIONS["cache_service"],
            os.path.join(lambda_base_path, "analysis/service-4-cache-service"),
            LAMBDA_CONFIG["timeout_short"],
            LAMBDA_CONFIG["memory_small"]
        )
        
        github_fetcher = create_lambda(
            LAMBDA_FUNCTIONS["github_fetcher"],
            os.path.join(lambda_base_path, "analysis/service-1-github-fetcher"),
            LAMBDA_CONFIG["timeout_long"],
            LAMBDA_CONFIG["memory_large"]
        )
        
        # Service 5-6: AI & Session
        ai_suggestion_service = create_lambda(
            LAMBDA_FUNCTIONS["ai_suggestion"],
            os.path.join(lambda_base_path, "ai/service-5-ai-suggestion"),
            LAMBDA_CONFIG["timeout_long"],
            LAMBDA_CONFIG["memory_large"]
        )
        
        session_creator = create_lambda(
            LAMBDA_FUNCTIONS["session_creator"],
            os.path.join(lambda_base_path, "ai/service-6-session-creator"),
            LAMBDA_CONFIG["timeout_short"],
            LAMBDA_CONFIG["memory_small"]
        )
        
        # Service 7-10: Upload Pipeline
        upload_url_generator = create_lambda(
            LAMBDA_FUNCTIONS["upload_url_generator"],
            os.path.join(lambda_base_path, "upload/service-7-upload-url-generator"),
            LAMBDA_CONFIG["timeout_short"],
            LAMBDA_CONFIG["memory_medium"]
        )
        
        upload_tracker = create_lambda(
            LAMBDA_FUNCTIONS["upload_tracker"],
            os.path.join(lambda_base_path, "upload/service-8-upload-tracker"),
            LAMBDA_CONFIG["timeout_short"],
            LAMBDA_CONFIG["memory_medium"]
        )
        
        video_validator = create_lambda(
            LAMBDA_FUNCTIONS["video_validator"],
            os.path.join(lambda_base_path, "upload/service-9-video-validator"),
            LAMBDA_CONFIG["timeout_long"],
            LAMBDA_CONFIG["memory_xlarge"],
            needs_ffmpeg=True
        )
        
        format_converter = create_lambda(
            LAMBDA_FUNCTIONS["format_converter"],
            os.path.join(lambda_base_path, "upload/service-10-format-converter"),
            LAMBDA_CONFIG["timeout_extra_long"],
            LAMBDA_CONFIG["memory_xxlarge"],
            needs_ffmpeg=True,
            ephemeral_mb=2048
        )
        
        # Service 11-14: Processing Pipeline
        job_queue_service = create_lambda(
            LAMBDA_FUNCTIONS["job_queue"],
            os.path.join(lambda_base_path, "processing/service-11-job-queue"),
            LAMBDA_CONFIG["timeout_medium"],
            LAMBDA_CONFIG["memory_medium"]
        )
        
        slide_creator = create_lambda(
            LAMBDA_FUNCTIONS["slide_creator"],
            os.path.join(lambda_base_path, "processing/service-12-slide-creator"),
            120,
            LAMBDA_CONFIG["memory_xlarge"],
            ephemeral_mb=LAMBDA_CONFIG["ephemeral_storage"]
        )
        
        video_stitcher = create_lambda(
            LAMBDA_FUNCTIONS["video_stitcher"],
            os.path.join(lambda_base_path, "processing/service-13-video-stitcher"),
            LAMBDA_CONFIG["timeout_extra_long"],
            LAMBDA_CONFIG["memory_xxlarge"],
            needs_ffmpeg=True,
            ephemeral_mb=LAMBDA_CONFIG["ephemeral_storage_large"]
        )
        
        video_optimizer = create_lambda(
            LAMBDA_FUNCTIONS["video_optimizer"],
            os.path.join(lambda_base_path, "processing/service-14-video-optimizer"),
            LAMBDA_CONFIG["timeout_extra_long"],
            LAMBDA_CONFIG["memory_xxlarge"],
            needs_ffmpeg=True,
            ephemeral_mb=LAMBDA_CONFIG["ephemeral_storage_large"]
        )
        
        # Service 15-17: Support Services
        notification_service = create_lambda(
            LAMBDA_FUNCTIONS["notification_service"],
            os.path.join(lambda_base_path, "support/service-15-notification"),
            LAMBDA_CONFIG["timeout_medium"],
            LAMBDA_CONFIG["memory_medium"]
        )
        
        status_tracker = create_lambda(
            LAMBDA_FUNCTIONS["status_tracker"],
            os.path.join(lambda_base_path, "support/service-16-status-tracker"),
            LAMBDA_CONFIG["timeout_short"],
            LAMBDA_CONFIG["memory_medium"]
        )
        
        cleanup_service = create_lambda(
            LAMBDA_FUNCTIONS["cleanup_service"],
            os.path.join(lambda_base_path, "support/service-17-cleanup"),
            LAMBDA_CONFIG["timeout_long"],
            LAMBDA_CONFIG["memory_large"]
        )

        # ========================
        # EVENT SOURCES & TRIGGERS
        # ========================
        
        # S3 notification for upload tracker - FIXED prefix
        self.demo_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(upload_tracker),
            s3.NotificationKeyFilter(
                prefix="videos/",
                suffix=".mp4"
            )
        )
        
        # SQS trigger for slide creator
        slide_creator.add_event_source(
            lambda_sources.SqsEventSource(
                processing_queue,
                batch_size=1
            )
        )
        
        # CloudWatch Events for daily cleanup
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
        # OUTPUTS
        # ========================
        
        CfnOutput(self, "ApiEndpoint", value=api.url)
        CfnOutput(self, "S3BucketName", value=self.demo_bucket.bucket_name)
        CfnOutput(self, "SessionsTableName", value=self.sessions_table.table_name)
        CfnOutput(self, "CacheTableName", value=self.cache_table.table_name)
        CfnOutput(self, "SQSQueueUrl", value=processing_queue.queue_url)
        CfnOutput(self, "SNSTopicArn", value=notification_topic.topic_arn)
    
    def _get_service_env(self, service_name: str) -> dict:
        """Get service-specific environment variables"""
        
        service_envs = {
            "service-5-ai-suggestion": {
                "SERVICE4_FUNCTION_NAME": LAMBDA_FUNCTIONS["cache_service"],
                "SERVICE6_FUNCTION_NAME": LAMBDA_FUNCTIONS["session_creator"],
            },
            "service-8-upload-tracker": {
                "VALIDATOR_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_validator"],
            },
            "service-9-video-validator": {
                "CONVERTER_FUNCTION_NAME": LAMBDA_FUNCTIONS["format_converter"],
                "MAX_VIDEO_DURATION": "120",
                "MIN_VIDEO_DURATION": "5",
                "MAX_FILE_SIZE": "104857600",
            },
            "service-12-slide-creator": {
                "STITCHER_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_stitcher"],
            },
            "service-13-video-stitcher": {
                "OPTIMIZER_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_optimizer"],
                "FFMPEG_PATH": "/opt/python/bin/ffmpeg",
                "FFPROBE_PATH": "/opt/python/bin/ffprobe",
            },
            "service-14-video-optimizer": {
                "NOTIFICATION_FUNCTION_NAME": LAMBDA_FUNCTIONS["notification_service"],
                "FFMPEG_PATH": "/opt/python/bin/ffmpeg",
                "FFPROBE_PATH": "/opt/python/bin/ffprobe",
            },
            "service-17-cleanup": {
                "DAYS_TO_KEEP": "30",
                "FAILED_SESSION_DAYS": "7",
            }
        }
        
        return service_envs.get(service_name, {})