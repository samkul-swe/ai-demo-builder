"""
Shared configuration for Lambda functions
Loads environment variables and provides constants
"""

import os
from typing import Dict, Any, Optional

# ========================
# AWS RESOURCES (from environment)
# ========================
AWS_REGION = os.environ.get('REGION', 'us-east-1')
S3_BUCKET = os.environ.get('S3_BUCKET', 'ai-demo-builder')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'ai-demo-sessions')
CACHE_TABLE = os.environ.get('CACHE_TABLE', 'ai-demo-cache')
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL', '')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

# ========================
# API KEYS (loaded from environment)
# ========================
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
HTTP_WEBHOOK_URL = os.environ.get('HTTP_WEBHOOK_URL', '')

# ========================
# SERVICE FUNCTION NAMES
# ========================
SERVICE4_FUNCTION_NAME = os.environ.get('SERVICE4_FUNCTION_NAME', 'service-4-cache-service')
SERVICE6_FUNCTION_NAME = os.environ.get('SERVICE6_FUNCTION_NAME', 'service-6-session-creator')
VALIDATOR_FUNCTION_NAME = os.environ.get('VALIDATOR_FUNCTION_NAME', 'service-9-video-validator')
CONVERTER_FUNCTION_NAME = os.environ.get('CONVERTER_FUNCTION_NAME', 'service-10-format-converter')
STITCHER_FUNCTION_NAME = os.environ.get('STITCHER_FUNCTION_NAME', 'service-13-video-stitcher')
OPTIMIZER_FUNCTION_NAME = os.environ.get('OPTIMIZER_FUNCTION_NAME', 'service-14-video-optimizer')
NOTIFICATION_FUNCTION_NAME = os.environ.get('NOTIFICATION_FUNCTION_NAME', 'service-15-notification')
CLEANUP_FUNCTION_NAME = os.environ.get('CLEANUP_FUNCTION_NAME', 'service-17-cleanup')

# ========================
# VIDEO PROCESSING SETTINGS
# ========================
MAX_VIDEO_DURATION = int(os.environ.get('MAX_VIDEO_DURATION', '120'))
MIN_VIDEO_DURATION = int(os.environ.get('MIN_VIDEO_DURATION', '5'))
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', '104857600'))

# ========================
# FFMPEG PATHS
# ========================
FFMPEG_PATH = os.environ.get('FFMPEG_PATH', '/opt/python/bin/ffmpeg')
FFPROBE_PATH = os.environ.get('FFPROBE_PATH', '/opt/python/bin/ffprobe')

# ========================
# CLEANUP SETTINGS
# ========================
DAYS_TO_KEEP = int(os.environ.get('DAYS_TO_KEEP', '30'))
FAILED_SESSION_DAYS = int(os.environ.get('FAILED_SESSION_DAYS', '7'))

# ========================
# HELPER FUNCTIONS
# ========================

def get_config(key: str, default: Optional[str] = None) -> str:
    """
    Get configuration value with fallback
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        Configuration value
    """
    return os.environ.get(key, default or '')

def require_config(key: str) -> str:
    """
    Get required configuration value, raise error if not set
    
    Args:
        key: Environment variable name
        
    Returns:
        Configuration value
        
    Raises:
        ValueError: If key is not set
    """
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"Required configuration {key} is not set")
    return value

def get_all_config() -> Dict[str, Any]:
    """Get all configuration as dictionary (for debugging)"""
    return {
        'aws_region': AWS_REGION,
        's3_bucket': S3_BUCKET,
        'dynamodb_table': DYNAMODB_TABLE,
        'cache_table': CACHE_TABLE,
        'has_github_token': bool(GITHUB_TOKEN),
        'has_gemini_key': bool(GEMINI_API_KEY),
        'max_video_duration': MAX_VIDEO_DURATION,
        'min_video_duration': MIN_VIDEO_DURATION,
    }