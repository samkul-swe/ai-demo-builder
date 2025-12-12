"""
Service 9: Video Validator
Validates uploaded video files using FFmpeg

CORRECTED VERSION - Fixed FFmpeg path and event handling
"""

import json
import os
import boto3
import subprocess
import tempfile
from botocore.exceptions import ClientError
import logging
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME')
TABLE_NAME = os.environ.get('SESSIONS_TABLE')
CONVERTER_FUNCTION = os.environ.get('CONVERTER_FUNCTION_NAME', 'service-10-format-converter')
MAX_DURATION = int(os.environ.get('MAX_VIDEO_DURATION', '120'))  # 2 minutes default
MIN_DURATION = int(os.environ.get('MIN_VIDEO_DURATION', '5'))    # 5 seconds
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', '104857600')) # 100MB


def parse_fps(fps_string):
    """
    Safely parse FPS from FFmpeg fraction format
    
    Args:
        fps_string: String like "30/1" or "24000/1001"
        
    Returns:
        Float FPS value
    """
    try:
        if '/' in str(fps_string):
            numerator, denominator = map(float, str(fps_string).split('/'))
            if denominator != 0:
                return numerator / denominator
        return float(fps_string)
    except (ValueError, ZeroDivisionError, AttributeError):
        return 0.0


def lambda_handler(event, context):
    """
    Service 9: Video Validator
    Validates uploaded video files using FFmpeg
    """
    logger.info(f"[Service9] Event: {json.dumps(event)}")
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            },
            'body': ''
        }
    
    try:
        # FIXED: Handle both string body (API Gateway) and direct object (Lambda invoke)
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        session_id = body.get('session_id')
        suggestion_id = body.get('suggestion_id')
        s3_key = body.get('s3_key')
        
        if not all([session_id, suggestion_id, s3_key]):
            logger.error("[Service9] Missing required parameters")
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'error': 'Missing required parameters',
                    'required': ['session_id', 'suggestion_id', 's3_key']
                })
            }
        
        logger.info(f"[Service9] Validating video: {s3_key}")
        logger.info(f"[Service9] Session: {session_id}, Suggestion: {suggestion_id}")
        
        # Create temp file for video
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Download video from S3
            logger.info(f"[Service9] Downloading from S3: {BUCKET_NAME}/{s3_key}")
            s3_client.download_file(BUCKET_NAME, s3_key, temp_path)
            logger.info(f"[Service9] Downloaded to {temp_path}")
            
            # Get file size
            file_size = os.path.getsize(temp_path)
            logger.info(f"[Service9] File size: {file_size:,} bytes")
            
            # Validate file size
            if file_size > MAX_FILE_SIZE:
                raise ValueError(f"File too large: {file_size:,} bytes (max: {MAX_FILE_SIZE:,} bytes / {MAX_FILE_SIZE/1024/1024:.1f}MB)")
            
            if file_size < 1000:  # Less than 1KB
                raise ValueError(f"File too small: {file_size} bytes (likely corrupt)")
            
            # FIXED: Use correct FFmpeg layer path
            ffprobe_path = '/opt/python/bin/ffprobe'
            
            # Check if ffprobe exists
            if not os.path.exists(ffprobe_path):
                # Fallback paths
                fallback_paths = ['/opt/bin/ffprobe', '/usr/bin/ffprobe', 'ffprobe']
                for path in fallback_paths:
                    if os.path.exists(path) or subprocess.run(['which', path], capture_output=True).returncode == 0:
                        ffprobe_path = path
                        break
            
            logger.info(f"[Service9] Using ffprobe at: {ffprobe_path}")
            
            # Use ffprobe to get video metadata
            probe_cmd = [
                ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                temp_path
            ]
            
            try:
                result = subprocess.run(
                    probe_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )
                
                if result.returncode != 0:
                    logger.error(f"[Service9] FFprobe stderr: {result.stderr}")
                    raise ValueError(f"FFprobe failed (exit code {result.returncode}): {result.stderr[:200]}")
                
                if not result.stdout:
                    raise ValueError("FFprobe returned empty output")
                
                metadata = json.loads(result.stdout)
                logger.info(f"[Service9] ✅ FFprobe analysis complete")
                
            except subprocess.TimeoutExpired:
                raise ValueError("Video analysis timed out after 30 seconds")
            except json.JSONDecodeError as e:
                logger.error(f"[Service9] FFprobe output: {result.stdout[:500]}")
                raise ValueError(f"Invalid FFprobe output: {str(e)}")
            
            # Extract video properties
            format_info = metadata.get('format', {})
            duration = float(format_info.get('duration', 0))
            
            # Find video and audio streams
            video_stream = None
            audio_stream = None
            for stream in metadata.get('streams', []):
                if stream.get('codec_type') == 'video' and not video_stream:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and not audio_stream:
                    audio_stream = stream
            
            if not video_stream:
                raise ValueError("No video stream found in file")
            
            # Extract video properties
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            codec = video_stream.get('codec_name', 'unknown')
            
            # FIXED: Safe FPS parsing
            fps_string = video_stream.get('r_frame_rate', '0/1')
            fps = parse_fps(fps_string)
            
            # Validate duration
            if duration < MIN_DURATION:
                raise ValueError(f"Video too short: {duration:.1f}s (minimum: {MIN_DURATION}s)")
            if duration > MAX_DURATION:
                raise ValueError(f"Video too long: {duration:.1f}s (maximum: {MAX_DURATION}s)")
            
            # Validate resolution
            if width < 320 or height < 240:
                raise ValueError(f"Resolution too low: {width}x{height} (minimum: 320x240)")
            if width > 7680 or height > 4320:  # 8K limit
                raise ValueError(f"Resolution too high: {width}x{height} (maximum: 8K)")
            
            # Validation successful
            validation_result = {
                'valid': True,
                'duration': round(duration, 2),
                'width': width,
                'height': height,
                'codec': codec,
                'fps': round(fps, 2),
                'file_size': file_size,
                'has_audio': audio_stream is not None,
                'bitrate': int(format_info.get('bit_rate', 0))
            }
            
            logger.info(f"[Service9] ✅ Validation successful: {width}x{height}, {duration:.1f}s, {codec}")
            
            # Update DynamoDB
            table = dynamodb.Table(TABLE_NAME)
            table.update_item(
                Key={'id': session_id},
                UpdateExpression='SET uploaded_videos.#suggId.validation = :val, uploaded_videos.#suggId.#status = :status, updated_at = :now',
                ExpressionAttributeNames={
                    '#suggId': str(suggestion_id),
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':val': validation_result,
                    ':status': 'validated',
                    ':now': datetime.utcnow().isoformat() + 'Z'
                }
            )
            
            logger.info(f"[Service9] ✅ Updated DynamoDB with validation results")
            
            # Trigger Service 10 (Format Converter)
            trigger_format_conversion(session_id, suggestion_id, s3_key, validation_result)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'session_id': session_id,
                    'suggestion_id': suggestion_id,
                    'validation': validation_result
                })
            }
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                logger.info(f"[Service9] Cleaned up temp file")
                
    except ValueError as e:
        logger.error(f"[Service9] ❌ Validation failed: {str(e)}")
        
        # Update DynamoDB with failure
        try:
            table = dynamodb.Table(TABLE_NAME)
            table.update_item(
                Key={'id': session_id},
                UpdateExpression='SET uploaded_videos.#suggId.validation = :val, uploaded_videos.#suggId.#status = :status, updated_at = :now',
                ExpressionAttributeNames={
                    '#suggId': str(suggestion_id),
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':val': {
                        'valid': False,
                        'error': str(e)
                    },
                    ':status': 'validation_failed',
                    ':now': datetime.utcnow().isoformat() + 'Z'
                }
            )
            logger.info(f"[Service9] Updated DynamoDB with validation failure")
        except Exception as db_error:
            logger.error(f"[Service9] Failed to update DynamoDB: {db_error}")
        
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Validation failed',
                'message': str(e),
                'session_id': session_id,
                'suggestion_id': suggestion_id
            })
        }
        
    except Exception as e:
        logger.error(f"[Service9] ❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


def trigger_format_conversion(session_id, suggestion_id, s3_key, validation_result):
    """
    Trigger Service 10 (Format Converter) asynchronously
    """
    try:
        payload = {
            'session_id': session_id,
            'suggestion_id': suggestion_id,
            's3_key': s3_key,
            'validation': validation_result
        }
        
        logger.info(f"[Service9] Triggering format conversion: {CONVERTER_FUNCTION}")
        
        lambda_client.invoke(
            FunctionName=CONVERTER_FUNCTION,
            InvocationType='Event',  # Asynchronous - fire and forget
            Payload=json.dumps(payload)
        )
        
        logger.info(f"[Service9] ✅ Triggered format conversion for {s3_key}")
        
    except Exception as e:
        logger.error(f"[Service9] ⚠️ Failed to trigger format conversion (non-critical): {e}")