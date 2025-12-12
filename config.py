"""
Central Configuration for AI Demo Builder CDK Stack
Combines static configuration with secrets from .env
"""

import os
from pathlib import Path

# Try to load .env file (for local development)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded secrets from: {env_path}")
    else:
        print(f"ℹ️  .env file not found (using environment variables)")
except ImportError:
    print("ℹ️  python-dotenv not installed (using environment variables)")

# ========================
# AWS Configuration (from .env)
# ========================
AWS_ACCOUNT_ID = os.getenv('AWS_ACCOUNT_ID', '')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# ========================
# STATIC RESOURCE NAMES
# These should NOT change - hardcoded for consistency
# ========================

PROJECT_NAME = "ai-demo-builder"

# S3 Bucket
S3_BUCKET_NAME = "ai-demo-builder"

# DynamoDB Tables
SESSIONS_TABLE = "ai-demo-builder-sessions"
CACHE_TABLE = "ai-demo-builder-cache"

# SQS Queue
SQS_PROCESSING_QUEUE = "video-processing-queue"

# SNS Topic
SNS_NOTIFICATION_TOPIC = "demo-notifications"

# IAM Role
LAMBDA_EXECUTION_ROLE = "lambda-execution-role"

# ========================
# SECRETS (from .env file)
# These values are sensitive and must be in .env
# ========================
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
HTTP_WEBHOOK_URL = os.getenv('HTTP_WEBHOOK_URL', '')

# ========================
# FEATURE FLAGS (from .env)
# ========================
ENABLE_FFMPEG_LAYER = os.getenv('ENABLE_FFMPEG_LAYER', 'true').lower() == 'true'
ENABLE_EMAIL_NOTIFICATIONS = os.getenv('ENABLE_EMAIL_NOTIFICATIONS', 'false').lower() == 'true'

# ========================
# LAMBDA FUNCTION NAMES (Static)
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
# LAMBDA CONFIGURATION (Static)
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
# VIDEO PROCESSING SETTINGS (Static)
# ========================
VIDEO_SETTINGS = {
    "max_duration": 120,        # seconds
    "min_duration": 5,          # seconds
    "max_file_size": 104857600, # 100MB
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30,
    "slide_duration": 3,        # seconds per slide
}

# ========================
# CLEANUP SETTINGS (Static)
# ========================
SESSION_EXPIRY_DAYS = 30
FAILED_SESSION_CLEANUP_DAYS = 7

# ========================
# Get Service-Specific Environment Variables
# ========================
def get_service_lambda_env(service_name: str) -> dict:
    """
    Build environment variables for a specific Lambda service
    Combines static config with secrets from .env
    
    Args:
        service_name: Name of the service (e.g., "ai_suggestion")
        
    Returns:
        dict: Environment variables for that service
    """
    
    # Base environment (secrets from .env)
    base_env = {}
    
    # Only add secrets if they exist (don't pass empty strings)
    if GITHUB_TOKEN:
        base_env["GITHUB_TOKEN"] = GITHUB_TOKEN
    
    if GEMINI_API_KEY:
        base_env["GEMINI_API_KEY"] = GEMINI_API_KEY
    
    if HTTP_WEBHOOK_URL:
        base_env["HTTP_WEBHOOK_URL"] = HTTP_WEBHOOK_URL
    
    # Service-specific environment variables
    service_specific = {
        "github_fetcher": {
            # Gets GITHUB_TOKEN from base_env
        },
        "readme_parser": {},
        "project_analyzer": {},
        "cache_service": {},
        "ai_suggestion": {
            # Gets GEMINI_API_KEY from base_env
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
        "notification_service": {
            # Gets HTTP_WEBHOOK_URL from base_env
        },
        "status_tracker": {},
        "cleanup_service": {
            "DAYS_TO_KEEP": str(SESSION_EXPIRY_DAYS),
            "FAILED_SESSION_DAYS": str(FAILED_SESSION_CLEANUP_DAYS),
        }
    }
    
    # Merge base + service-specific
    env = base_env.copy()
    if service_name in service_specific:
        env.update(service_specific[service_name])
    
    return env

# ========================
# Validation
# ========================
def validate_config():
    """Validate configuration and show warnings"""
    print("")
    print("📋 Configuration Summary:")
    print(f"   AWS Region: {AWS_REGION}")
    print(f"   S3 Bucket: {S3_BUCKET_NAME}")
    print(f"   Sessions Table: {SESSIONS_TABLE}")
    print(f"   Cache Table: {CACHE_TABLE}")
    print(f"   SQS Queue: {SQS_PROCESSING_QUEUE}")
    print(f"   SNS Topic: {SNS_NOTIFICATION_TOPIC}")
    print(f"   FFmpeg Layer: {'Enabled' if ENABLE_FFMPEG_LAYER else 'Disabled'}")
    print("")
    
    # Check for secrets
    if not GITHUB_TOKEN:
        print("⚠️  WARNING: GITHUB_TOKEN not set")
        print("   Service 1 will be rate-limited (60 requests/hour)")
        print("   Add to .env for 5,000 requests/hour")
    else:
        masked = GITHUB_TOKEN[:4] + "..." + GITHUB_TOKEN[-4:]
        print(f"✅ GitHub Token: {masked}")
    
    if not GEMINI_API_KEY:
        print("⚠️  WARNING: GEMINI_API_KEY not set")
        print("   Service 5 will use fallback suggestions (no AI)")
        print("   Add to .env for AI-powered suggestions")
    else:
        masked = GEMINI_API_KEY[:8] + "..." + GEMINI_API_KEY[-4:]
        print(f"✅ Gemini API Key: {masked}")
    
    print("")

# Run validation when imported
validate_config()