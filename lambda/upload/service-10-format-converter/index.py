"""
Service 10: Format Converter
Converts videos to standardized format (1920x1080, 30fps, H.264)

CORRECTED VERSION - Fixed FFmpeg path and event handling
"""

import json
import os
import boto3
import subprocess
import tempfile
import shutil
from datetime import datetime
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3', region_name='us-west-2')
dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
sqs = boto3.client('sqs', region_name='us-west-2')

# Environment variables
BUCKET = os.environ.get('S3_BUCKET', 'ai-demo-builder')
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'ai-demo-sessions')
QUEUE_URL = os.environ.get('SQS_QUEUE_URL', '')

# Standard output format for all videos
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
OUTPUT_FPS = 30
OUTPUT_BITRATE = '2M'
OUTPUT_CODEC = 'libx264'


def lambda_handler(event, context):
    """
    Service 10: Format Converter
    Convert video to standardized format for consistent stitching
    """
    logger.info(f"[Service10] Event: {json.dumps(event)}")
    
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
        input_s3_key = body.get('s3_key')
        validation_result = body.get('validation', {})  # From Service 9
        
        if not all([session_id, suggestion_id, input_s3_key]):
            logger.error("[Service10] Missing required parameters")
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
        
        logger.info(f"[Service10] Converting video: {input_s3_key}")
        logger.info(f"[Service10] Session: {session_id}, Suggestion: {suggestion_id}")
        
        # Log input video properties if available
        if validation_result:
            logger.info(f"[Service10] Input: {validation_result.get('width')}x{validation_result.get('height')}, "
                       f"{validation_result.get('duration')}s, {validation_result.get('codec')}")
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        input_file = os.path.join(temp_dir, 'input.mp4')
        output_file = os.path.join(temp_dir, 'standardized.mp4')
        
        try:
            # Download input video
            logger.info(f"[Service10] Downloading from S3: {BUCKET}/{input_s3_key}")
            s3_client.download_file(BUCKET, input_s3_key, input_file)
            input_size = os.path.getsize(input_file)
            logger.info(f"[Service10] Downloaded {input_size:,} bytes")
            
            # FIXED: Use correct FFmpeg layer path
            ffmpeg_path = '/opt/python/bin/ffmpeg'
            
            # Check if ffmpeg exists, try fallback paths
            if not os.path.exists(ffmpeg_path):
                fallback_paths = ['/opt/bin/ffmpeg', '/usr/bin/ffmpeg', 'ffmpeg']
                for path in fallback_paths:
                    if os.path.exists(path):
                        ffmpeg_path = path
                        break
            
            logger.info(f"[Service10] Using ffmpeg at: {ffmpeg_path}")
            
            # Build FFmpeg command for standardization
            ffmpeg_cmd = [
                ffmpeg_path,
                '-i', input_file,
                '-c:v', OUTPUT_CODEC,
                '-preset', 'medium',  # Balance between speed and quality
                '-crf', '23',  # Constant Rate Factor (quality)
                # Scale and pad to maintain aspect ratio
                '-vf', f'scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,'
                       f'pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,'
                       f'fps={OUTPUT_FPS}',
                '-b:v', OUTPUT_BITRATE,
                '-maxrate', OUTPUT_BITRATE,
                '-bufsize', '4M',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-movflags', '+faststart',  # Optimize for web streaming
                '-y',  # Overwrite output
                output_file
            ]
            
            logger.info(f"[Service10] Running FFmpeg conversion to {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}@{OUTPUT_FPS}fps")
            
            # Run FFmpeg with timeout
            process = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=280,  # Leave 20 seconds buffer in 5-min Lambda timeout
                check=False
            )
            
            if process.returncode != 0:
                logger.error(f"[Service10] FFmpeg stderr: {process.stderr[:500]}")
                raise ValueError(f"FFmpeg conversion failed (exit code {process.returncode})")
            
            # Check output file exists and has reasonable size
            if not os.path.exists(output_file):
                raise ValueError("FFmpeg did not create output file")
            
            output_size = os.path.getsize(output_file)
            if output_size < 1000:  # Less than 1KB
                raise ValueError(f"Output file too small: {output_size} bytes (likely failed)")
            
            logger.info(f"[Service10] ✅ Conversion successful: {output_size:,} bytes")
            logger.info(f"[Service10] Size change: {input_size:,} → {output_size:,} bytes ({output_size/input_size*100:.1f}%)")
            
            # Upload standardized video to S3
            output_s3_key = f'videos/{session_id}/standardized_{suggestion_id}.mp4'
            
            logger.info(f"[Service10] Uploading to S3: {output_s3_key}")
            s3_client.upload_file(
                output_file,
                BUCKET,
                output_s3_key,
                ExtraArgs={
                    'ContentType': 'video/mp4',
                    'Metadata': {
                        'session_id': session_id,
                        'suggestion_id': str(suggestion_id),
                        'original_key': input_s3_key,
                        'standardized': 'true',
                        'resolution': f'{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}',
                        'fps': str(OUTPUT_FPS)
                    }
                }
            )
            
            logger.info(f"[Service10] ✅ Uploaded standardized video")
            
            # Update DynamoDB
            table = dynamodb.Table(TABLE_NAME)
            
            conversion_data = {
                'standardized_key': output_s3_key,
                'output_size': output_size,
                'output_resolution': f'{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}',
                'output_fps': OUTPUT_FPS,
                'output_codec': OUTPUT_CODEC,
                'converted_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            table.update_item(
                Key={'id': session_id},
                UpdateExpression='SET uploaded_videos.#suggId.converted_data = :data, '
                               'uploaded_videos.#suggId.#status = :status, '
                               'updated_at = :now',
                ExpressionAttributeNames={
                    '#suggId': str(suggestion_id),
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':data': conversion_data,
                    ':status': 'converted',
                    ':now': datetime.utcnow().isoformat() + 'Z'
                }
            )
            
            logger.info(f"[Service10] ✅ Updated DynamoDB")
            
            # Check if all videos are converted
            all_ready = check_all_videos_ready(session_id)
            
            if all_ready:
                logger.info(f"[Service10] 🎉 All videos converted for session {session_id}!")
                
                # Update session status to ready for processing
                table.update_item(
                    Key={'id': session_id},
                    UpdateExpression='SET #status = :status, updated_at = :now',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':status': 'ready_for_processing',
                        ':now': datetime.utcnow().isoformat() + 'Z'
                    }
                )
                
                # Trigger video stitching via SQS
                if QUEUE_URL:
                    trigger_video_stitching(session_id)
                else:
                    logger.warning("[Service10] ⚠️ SQS_QUEUE_URL not configured - skipping stitching trigger")
            else:
                logger.info(f"[Service10] Waiting for more videos to be converted")
            
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'success': True,
                    'session_id': session_id,
                    'suggestion_id': suggestion_id,
                    'standardized_key': output_s3_key,
                    'input_size': input_size,
                    'output_size': output_size,
                    'compression_ratio': round(output_size / input_size * 100, 1),
                    'all_videos_ready': all_ready
                })
            }
            
        finally:
            # FIXED: Clean up temp directory and all files
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.info("[Service10] Cleaned up temp directory")
                
    except subprocess.TimeoutExpired:
        logger.error("[Service10] ❌ FFmpeg conversion timed out")
        
        # Mark as failed in DynamoDB
        try:
            table = dynamodb.Table(TABLE_NAME)
            table.update_item(
                Key={'id': session_id},
                UpdateExpression='SET uploaded_videos.#suggId.#status = :status, '
                               'uploaded_videos.#suggId.error = :error',
                ExpressionAttributeNames={
                    '#suggId': str(suggestion_id),
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': 'conversion_failed',
                    ':error': 'Conversion timed out'
                }
            )
        except:
            pass
        
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Video conversion timed out',
                'message': 'Video is too complex or large to process',
                'suggestion': 'Try a shorter or lower resolution video'
            })
        }
        
    except ValueError as e:
        logger.error(f"[Service10] ❌ Conversion error: {str(e)}")
        
        # Mark as failed in DynamoDB
        try:
            table = dynamodb.Table(TABLE_NAME)
            table.update_item(
                Key={'id': session_id},
                UpdateExpression='SET uploaded_videos.#suggId.#status = :status, '
                               'uploaded_videos.#suggId.error = :error',
                ExpressionAttributeNames={
                    '#suggId': str(suggestion_id),
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': 'conversion_failed',
                    ':error': str(e)
                }
            )
        except:
            pass
        
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Conversion failed',
                'message': str(e)
            })
        }
        
    except Exception as e:
        logger.error(f"[Service10] ❌ Unexpected error: {str(e)}")
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


def check_all_videos_ready(session_id):
    """
    Check if all videos for a session have been converted
    
    Returns:
        bool: True if all videos converted, False otherwise
    """
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={'id': session_id})
        
        if 'Item' not in response:
            logger.warning(f"[Service10] Session {session_id} not found")
            return False
        
        session = response['Item']
        suggestions = session.get('suggestions', [])
        uploaded_videos = session.get('uploaded_videos', {})
        
        if not suggestions:
            logger.warning(f"[Service10] No suggestions found for session {session_id}")
            return False
        
        total_suggestions = len(suggestions)
        converted_count = 0
        
        # FIXED: Use actual sequence_number from suggestions, not enumerate
        for suggestion in suggestions:
            suggestion_id = str(suggestion.get('sequence_number', 0))
            
            if suggestion_id not in uploaded_videos:
                logger.info(f"[Service10] Suggestion {suggestion_id} has no upload")
                return False
            
            video_data = uploaded_videos[suggestion_id]
            video_status = video_data.get('status', '')
            
            if video_status == 'converted':
                converted_count += 1
            elif video_status in ['conversion_failed', 'validation_failed']:
                logger.warning(f"[Service10] Suggestion {suggestion_id} failed: {video_status}")
                return False
            else:
                logger.info(f"[Service10] Suggestion {suggestion_id} status: {video_status}")
                return False
        
        logger.info(f"[Service10] Conversion progress: {converted_count}/{total_suggestions}")
        return converted_count == total_suggestions
        
    except Exception as e:
        logger.error(f"[Service10] Error checking video readiness: {e}")
        return False


def trigger_video_stitching(session_id):
    """
    Send message to SQS to trigger video stitching pipeline
    """
    try:
        if not QUEUE_URL:
            logger.warning("[Service10] ⚠️ SQS_QUEUE_URL not configured")
            return
        
        message = {
            'session_id': session_id,
            'action': 'stitch_videos',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'source': 'service-10-format-converter'
        }
        
        logger.info(f"[Service10] Sending SQS message to: {QUEUE_URL}")
        
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message),
            MessageAttributes={
                'session_id': {
                    'StringValue': session_id,
                    'DataType': 'String'
                },
                'action': {
                    'StringValue': 'stitch_videos',
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"[Service10] ✅ Sent SQS message: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"[Service10] ⚠️ Failed to send SQS message (non-critical): {e}")