"""
Central Configuration for AI Demo Builder
"""

import os

# ========================
# RESOURCE NAMING
# ========================

PROJECT_NAME = "ai-demo-builder"

# S3
S3_BUCKET_NAME = "ai-demo-builder"

# DynamoDB Tables
SESSIONS_TABLE = "ai-demo-builder-sessions"
CACHE_TABLE = "ai-demo-builder-cache"

# SQS
SQS_PROCESSING_QUEUE = "video-processing-queue"

# SNS
SNS_NOTIFICATION_TOPIC = "demo-notifications"

# IAM
LAMBDA_EXECUTION_ROLE = "lambda-execution-role"

# ========================
# LAMBDA FUNCTION NAMES
# ========================
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

# ========================
# LAMBDA CONFIGURATION
# ========================
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

# ========================
# VIDEO SETTINGS
# ========================
VIDEO_SETTINGS = {
    "max_duration": 120,
    "min_duration": 5,
    "max_file_size": 104857600,
}

# ========================
# SERVICE-SPECIFIC ENV VARS
# ========================
def get_service_lambda_env(service_name: str) -> dict:
    """Get service-specific environment variables"""
    
    service_envs = {
        "github_fetcher": {},
        "readme_parser": {},
        "project_analyzer": {},
        "cache_service": {},
        "ai_suggestion": {
            "SERVICE4_FUNCTION_NAME": LAMBDA_FUNCTIONS["cache_service"],
            "SERVICE6_FUNCTION_NAME": LAMBDA_FUNCTIONS["session_creator"],
        },
        "session_creator": {},
        "upload_url_generator": {},
        "upload_tracker": {
            "VALIDATOR_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_validator"],
        },
        "video_validator": {
            "CONVERTER_FUNCTION_NAME": LAMBDA_FUNCTIONS["format_converter"],
            "MAX_VIDEO_DURATION": str(VIDEO_SETTINGS["max_duration"]),
            "MIN_VIDEO_DURATION": str(VIDEO_SETTINGS["min_duration"]),
            "MAX_FILE_SIZE": str(VIDEO_SETTINGS["max_file_size"]),
        },
        "format_converter": {},
        "job_queue": {},
        "slide_creator": {
            "STITCHER_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_stitcher"],
        },
        "video_stitcher": {
            "OPTIMIZER_FUNCTION_NAME": LAMBDA_FUNCTIONS["video_optimizer"],
            "FFMPEG_PATH": "/opt/python/bin/ffmpeg",
            "FFPROBE_PATH": "/opt/python/bin/ffprobe",
        },
        "video_optimizer": {
            "NOTIFICATION_FUNCTION_NAME": LAMBDA_FUNCTIONS["notification_service"],
            "FFMPEG_PATH": "/opt/python/bin/ffmpeg",
            "FFPROBE_PATH": "/opt/python/bin/ffprobe",
        },
        "notification_service": {},
        "status_tracker": {},
        "cleanup_service": {
            "DAYS_TO_KEEP": "30",
            "FAILED_SESSION_DAYS": "7",
        }
    }
    
    return service_envs.get(service_name, {})