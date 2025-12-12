"""
Central Configuration for AI Demo Builder
All resource names and constants in one place
"""

import os
from typing import Dict, Any

# ========================
# PROJECT METADATA
# ========================
PROJECT_NAME = "ai-demo-builder"
PROJECT_VERSION = "1.0.0"
DEPLOYMENT_ENVIRONMENT = os.getenv("DEPLOYMENT_ENV", "prod")  # prod, dev, staging

# ========================
# AWS CONFIGURATION
# ========================
AWS_REGION = "us-west-2"
AWS_ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID", "")  # Optional: set for multi-account

# ========================
# RESOURCE NAMING
# ========================

# Use suffix for environment-specific deployments
RESOURCE_SUFFIX = f"-{DEPLOYMENT_ENVIRONMENT}" if DEPLOYMENT_ENVIRONMENT != "prod" else ""

# S3 Configuration
S3_BUCKET_NAME = f"{PROJECT_NAME}{RESOURCE_SUFFIX}"
S3_FRONTEND_BUCKET = f"{PROJECT_NAME}-frontend{RESOURCE_SUFFIX}"

# DynamoDB Tables
DYNAMODB_SESSIONS_TABLE = f"{PROJECT_NAME}-sessions{RESOURCE_SUFFIX}"
DYNAMODB_CACHE_TABLE = f"{PROJECT_NAME}-cache{RESOURCE_SUFFIX}"

# SQS Queue
SQS_PROCESSING_QUEUE = f"video-processing-queue{RESOURCE_SUFFIX}"

# SNS Topic
SNS_NOTIFICATION_TOPIC = f"demo-notifications{RESOURCE_SUFFIX}"

# IAM Role
LAMBDA_EXECUTION_ROLE = f"lambda-execution-role{RESOURCE_SUFFIX}"

# CloudFormation Stack
STACK_NAME = f"AiDemoBuilderStack{RESOURCE_SUFFIX.replace('-', '')}"  # Remove dash for stack name

# ========================
# LAMBDA FUNCTION NAMES
# ========================
LAMBDA_FUNCTIONS = {
    # Analysis Pipeline
    "github_fetcher": "service-1-github-fetcher",
    "readme_parser": "service-2-readme-parser",
    "project_analyzer": "service-3-project-analyzer",
    "cache_service": "service-4-cache-service",
    
    # AI & Session
    "ai_suggestion": "service-5-ai-suggestion",
    "session_creator": "service-6-session-creator",
    
    # Upload Pipeline
    "upload_url_generator": "service-7-upload-url-generator",
    "upload_tracker": "service-8-upload-tracker",
    "video_validator": "service-9-video-validator",
    "format_converter": "service-10-format-converter",
    
    # Video Processing
    "job_queue": "service-11-job-queue",
    "slide_creator": "service-12-slide-creator",
    "video_stitcher": "service-13-video-stitcher",
    "video_optimizer": "service-14-video-optimizer",
    
    # Support Services
    "notification_service": "service-15-notification-service",
    "status_tracker": "service-16-status-tracker",
    "cleanup_service": "service-17-cleanup"
}

# ========================
# VIDEO PROCESSING SETTINGS
# ========================
VIDEO_SETTINGS = {
    "max_duration": 120,        # seconds
    "min_duration": 5,          # seconds
    "max_file_size": 104857600, # 100MB in bytes
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30,
    "slide_duration": 3,        # seconds
}

# ========================
# LAMBDA CONFIGURATION
# ========================
LAMBDA_CONFIG = {
    "runtime": "python3.11",
    "timeout_short": 10,        # seconds - for lightweight functions
    "timeout_medium": 30,       # seconds - for API calls
    "timeout_long": 300,        # seconds - for video processing
    "timeout_extra_long": 900,  # seconds - for stitching/optimization
    "memory_small": 128,        # MB
    "memory_medium": 256,       # MB
    "memory_large": 512,        # MB
    "memory_xlarge": 1024,      # MB
    "memory_xxlarge": 3008,     # MB - max
    "ephemeral_storage": 512,   # MB - for video processing
    "ephemeral_storage_large": 10240,  # MB - 10GB for stitching
}

# ========================
# CACHE & CLEANUP SETTINGS
# ========================
CACHE_TTL = 3600  # 1 hour in seconds
SESSION_EXPIRY_DAYS = 30
FAILED_SESSION_CLEANUP_DAYS = 7

# ========================
# FFMPEG PATHS (in Lambda Layer)
# ========================
FFMPEG_PATH = "/opt/python/bin/ffmpeg"
FFPROBE_PATH = "/opt/python/bin/ffprobe"

# ========================
# API GATEWAY SETTINGS
# ========================
API_CONFIG = {
    "name": "AI Demo Builder API",
    "description": "REST API for AI Demo Builder",
    "stage": "prod"
}

# ========================
# ENVIRONMENT VARIABLES FOR LAMBDA
# ========================
def get_base_lambda_env() -> Dict[str, str]:
    """
    Get base environment variables for all Lambda functions
    These are non-secret configuration values
    """
    return {
        "REGION": AWS_REGION,
        "S3_BUCKET": S3_BUCKET_NAME,
        "DYNAMODB_TABLE": DYNAMODB_SESSIONS_TABLE,
        "CACHE_TABLE": DYNAMODB_CACHE_TABLE,
        "SQS_QUEUE_URL": "",  # Will be set after SQS creation
        "SNS_TOPIC_ARN": "",  # Will be set after SNS creation
        "PROJECT_NAME": PROJECT_NAME,
        "ENVIRONMENT": DEPLOYMENT_ENVIRONMENT,
    }

def get_service_lambda_env(service_name: str) -> Dict[str, str]:
    """
    Get service-specific environment variables
    Secrets should be set via AWS Console or AWS Secrets Manager
    """
    base_env = get_base_lambda_env()
    
    # Service-specific additions
    service_env = {
        "github_fetcher": {
            # API keys set separately via console
        },
        "ai_suggestion": {
            "SERVICE4_FUNCTION_NAME": LAMBDA_FUNCTIONS["cache_service"],
            "SERVICE6_FUNCTION_NAME": LAMBDA_FUNCTIONS["session_creator"],
            # GEMINI_API_KEY set separately via console
        },
        "upload_tracker": {
            "VALIDATOR_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_validator"],
        },
        "video_validator": {
            "CONVERTER_FUNCTION_NAME": LAMBDA_FUNCTIONS["format_converter"],
            "MAX_VIDEO_DURATION": str(VIDEO_SETTINGS["max_duration"]),
            "MIN_VIDEO_DURATION": str(VIDEO_SETTINGS["min_duration"]),
            "MAX_FILE_SIZE": str(VIDEO_SETTINGS["max_file_size"]),
        },
        "format_converter": {
            # SQS_QUEUE_URL set in base
        },
        "slide_creator": {
            "STITCHER_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_stitcher"],
        },
        "video_stitcher": {
            "OPTIMIZER_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_optimizer"],
            "FFMPEG_PATH": FFMPEG_PATH,
            "FFPROBE_PATH": FFPROBE_PATH,
        },
        "video_optimizer": {
            "NOTIFICATION_FUNCTION_NAME": LAMBDA_FUNCTIONS["notification_service"],
            "CLEANUP_FUNCTION_NAME": LAMBDA_FUNCTIONS["cleanup_service"],
            "FFMPEG_PATH": FFMPEG_PATH,
            "FFPROBE_PATH": FFPROBE_PATH,
        },
        "cleanup_service": {
            "DAYS_TO_KEEP": str(SESSION_EXPIRY_DAYS),
            "FAILED_SESSION_DAYS": str(FAILED_SESSION_CLEANUP_DAYS),
        }
    }
    
    # Merge base + service-specific
    env = base_env.copy()
    if service_name in service_env:
        env.update(service_env[service_name])
    
    return env

# ========================
# VALIDATION
# ========================
def validate_config():
    """Validate that required configuration is set"""
    errors = []
    
    if not AWS_REGION:
        errors.append("AWS_REGION must be set")
    
    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")

# Validate on import
validate_config()