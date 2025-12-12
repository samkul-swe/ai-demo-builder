"""
Service 14: Video Optimizer
Optimizes and compresses stitched video into multiple resolutions
Triggered by Service 13 after stitching completes
"""

import os
import json
import subprocess
import boto3
from datetime import datetime
import tempfile
import shutil
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')  # ✅ FIXED: Added this line

# Configuration - FIXED to match other services
BUCKET = os.environ.get('S3_BUCKET', 'ai-demo-builder')
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'ai-demo-sessions')

# FFmpeg paths - FIXED
FFMPEG_PATH = os.environ.get('FFMPEG_PATH', '/opt/python/bin/ffmpeg')
FFPROBE_PATH = os.environ.get('FFPROBE_PATH', '/opt/python/bin/ffprobe')

# Check FFmpeg paths exist
if not os.path.exists(FFMPEG_PATH):
    fallback_paths = ['/opt/bin/ffmpeg', '/usr/bin/ffmpeg', 'ffmpeg']
    for path in fallback_paths:
        if os.path.exists(path):
            FFMPEG_PATH = path
            break

if not os.path.exists(FFPROBE_PATH):
    fallback_paths = ['/opt/bin/ffprobe', '/usr/bin/ffprobe', 'ffprobe']
    for path in fallback_paths:
        if os.path.exists(path):
            FFPROBE_PATH = path
            break

logger.info(f"[Service14] Using ffmpeg: {FFMPEG_PATH}")
logger.info(f"[Service14] Using ffprobe: {FFPROBE_PATH}")

# Output presets for different resolutions
PRESETS = {
    '1080p': {
        'width': 1920,
        'height': 1080,
        'bitrate': '5M',
        'maxrate': '6M',
        'bufsize': '10M',
        'crf': 23,
        'audio_bitrate': '192k'
    },
    '720p': {
        'width': 1280,
        'height': 720,
        'bitrate': '2.5M',
        'maxrate': '3M',
        'bufsize': '5M',
        'crf': 24,
        'audio_bitrate': '128k'
    },
    '480p': {
        'width': 854,
        'height': 480,
        'bitrate': '1M',
        'maxrate': '1.5M',
        'bufsize': '2M',
        'crf': 25,
        'audio_bitrate': '96k'
    }
}


def update_session_status(session_id, status, additional_data=None):
    """Update session status in DynamoDB"""
    table = dynamodb.Table(TABLE_NAME)
    
    update_expr = 'SET #status = :status, updated_at = :now'
    expr_names = {'#status': 'status'}
    expr_values = {
        ':status': status,
        ':now': datetime.utcnow().isoformat() + 'Z'
    }
    
    if additional_data:
        for key, value in additional_data.items():
            # Convert floats to strings for DynamoDB
            if isinstance(value, float):
                value = str(value)
            # Handle nested dicts/lists by converting to JSON string if needed
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            update_expr += f', {key} = :{key}'
            expr_values[f':{key}'] = value
    
    try:
        table.update_item(
            Key={'id': session_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
        logger.info(f"[Service14] Status updated: {session_id} -> {status}")
    except Exception as e:
        logger.error(f"[Service14] Could not update DynamoDB: {e}")


def get_video_info(video_path):
    """Get video information using ffprobe"""
    cmd = [
        FFPROBE_PATH,
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        info = json.loads(result.stdout)
        
        format_info = info.get('format', {})
        duration = float(format_info.get('duration', 0))
        file_size = int(format_info.get('size', 0))
        
        video_stream = None
        audio_stream = None
        for stream in info.get('streams', []):
            if stream['codec_type'] == 'video' and not video_stream:
                video_stream = stream
            elif stream['codec_type'] == 'audio' and not audio_stream:
                audio_stream = stream
        
        # Safe FPS parsing
        fps_str = video_stream.get('r_frame_rate', '30/1') if video_stream else '30/1'
        try:
            if '/' in fps_str:
                num, denom = map(float, fps_str.split('/'))
                fps = num / denom if denom != 0 else 30.0
            else:
                fps = float(fps_str)
        except:
            fps = 30.0
        
        return {
            'duration': duration,
            'file_size': file_size,
            'width': video_stream.get('width', 1920) if video_stream else 1920,
            'height': video_stream.get('height', 1080) if video_stream else 1080,
            'fps': fps,
            'video_codec': video_stream.get('codec_name') if video_stream else None,
            'audio_codec': audio_stream.get('codec_name') if audio_stream else None,
            'has_audio': audio_stream is not None
        }
    except Exception as e:
        logger.error(f"[Service14] Error getting video info: {e}")
        return None


def download_from_s3(s3_key, local_path):
    """Download file from S3"""
    logger.info(f"[Service14] Downloading s3://{BUCKET}/{s3_key}")
    s3_client.download_file(BUCKET, s3_key, local_path)
    return local_path


def upload_to_s3(local_path, s3_key, content_type='video/mp4'):
    """Upload file to S3"""
    logger.info(f"[Service14] Uploading to s3://{BUCKET}/{s3_key}")
    s3_client.upload_file(
        local_path,
        BUCKET,
        s3_key,
        ExtraArgs={'ContentType': content_type}
    )
    return f"https://{BUCKET}.s3.us-east-1.amazonaws.com/{s3_key}"


def generate_presigned_url(s3_key, expires_in=86400):
    """Generate presigned URL for download (24 hours default)"""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET, 'Key': s3_key},
            ExpiresIn=expires_in
        )
        return url
    except Exception as e:
        logger.error(f"[Service14] Error generating presigned URL: {e}")
        return None


def optimize_video(input_path, output_path, preset_name):
    """Encode video with specified preset"""
    preset = PRESETS.get(preset_name, PRESETS['1080p'])
    
    cmd = [
        FFMPEG_PATH,
        '-y',
        '-i', input_path,
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', str(preset['crf']),
        '-maxrate', preset['maxrate'],
        '-bufsize', preset['bufsize'],
        '-vf', f"scale={preset['width']}:{preset['height']}:force_original_aspect_ratio=decrease,pad={preset['width']}:{preset['height']}:(ow-iw)/2:(oh-ih)/2:black",
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', preset['audio_bitrate'],
        '-ar', '44100',
        '-ac', '2',
        '-movflags', '+faststart',
        '-brand', 'mp42',
        output_path
    ]
    
    logger.info(f"[Service14] Encoding {preset_name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    
    if result.returncode != 0:
        logger.error(f"[Service14] FFmpeg stderr: {result.stderr}")
        raise Exception(f"Failed to encode video ({preset_name}): {result.stderr}")
    
    return output_path


def generate_thumbnail(input_path, output_path, timestamp='00:00:01'):
    """Generate thumbnail image from video"""
    cmd = [
        FFMPEG_PATH,
        '-y',
        '-i', input_path,
        '-ss', timestamp,
        '-vframes', '1',
        '-vf', 'scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:black',
        '-q:v', '2',
        output_path
    ]
    
    logger.info(f"[Service14] Generating thumbnail")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        logger.warning(f"[Service14] Failed to generate thumbnail: {result.stderr}")
        return None
    
    return output_path


def trigger_notification_service(session_id):
    """Trigger Service 15 (Notification Service) asynchronously"""
    try:
        payload = {'session_id': session_id}
        
        notification_function = os.environ.get(
            'NOTIFICATION_FUNCTION_NAME', 
            'service-15-notification'
        )
        
        logger.info(f"[Service14] Triggering notification service: {notification_function}")
        
        lambda_client.invoke(
            FunctionName=notification_function,
            InvocationType='Event',  # Asynchronous
            Payload=json.dumps(payload)
        )
        
        logger.info(f"[Service14] ✅ Triggered Service 15 (Notification)")
        
    except Exception as e:
        logger.error(f"[Service14] ⚠️ Failed to trigger notifications (non-critical): {e}")


def trigger_notification_service(session_id):
    """Trigger Service 15 (Notification Service) asynchronously"""
    try:
        payload = {
            'session_id': session_id
        }
        
        notification_function = os.environ.get(
            'NOTIFICATION_FUNCTION_NAME',
            'service-15-notification'
        )
        
        logger.info(f"[Service14] Triggering notification: {notification_function}")
        
        lambda_client.invoke(
            FunctionName=notification_function,
            InvocationType='Event',  # Asynchronous
            Payload=json.dumps(payload)
        )
        
        logger.info(f"[Service14] ✅ Triggered Service 15 (Notification)")
        
    except Exception as e:
        logger.error(f"[Service14] ⚠️ Failed to trigger notifications (non-critical): {e}")


def process_optimization(session_id, stitched_key):
    """Main optimization logic"""
    logger.info(f"[Service14] Starting optimization for session: {session_id}")
    logger.info(f"[Service14] Input: {stitched_key}")
    
    # Default: generate 1080p and 720p versions
    resolutions = ['1080p', '720p']
    generate_thumb = True
    
    # STATUS UPDATE: optimizing
    update_session_status(session_id, 'optimizing', {
        'optimizing_started_at': datetime.utcnow().isoformat() + 'Z',
        'target_resolutions': json.dumps(resolutions)
    })
    
    work_dir = tempfile.mkdtemp()
    
    try:
        input_filename = os.path.basename(stitched_key)
        input_path = os.path.join(work_dir, input_filename)
        download_from_s3(stitched_key, input_path)
        
        input_info = get_video_info(input_path)
        if not input_info:
            raise Exception('Could not read input video')
        
        logger.info(f"[Service14] Input: {input_info['width']}x{input_info['height']}, {input_info['duration']:.2f}s")
        
        outputs = []
        
        for idx, resolution in enumerate(resolutions):
            if resolution not in PRESETS:
                logger.warning(f"[Service14] Unknown resolution {resolution}, skipping")
                continue
            
            # STATUS UPDATE: encoding resolution
            update_session_status(session_id, 'optimizing', {
                'processing_step': f'Encoding {resolution} ({idx + 1}/{len(resolutions)})'
            })
            
            output_filename = f"demo_{session_id}_{resolution}.mp4"
            output_path = os.path.join(work_dir, output_filename)
            
            logger.info(f"[Service14] Encoding {resolution}...")
            optimize_video(input_path, output_path, resolution)
            
            output_info = get_video_info(output_path)
            
            # Upload to final/ folder
            s3_key = f"demos/{session_id}/final_{output_filename}"
            public_url = upload_to_s3(output_path, s3_key)
            
            # Generate presigned URL (valid for 24 hours)
            presigned_url = generate_presigned_url(s3_key)
            
            outputs.append({
                'resolution': resolution,
                's3_key': s3_key,
                'public_url': public_url,
                'download_url': presigned_url,
                'width': PRESETS[resolution]['width'],
                'height': PRESETS[resolution]['height'],
                'duration': output_info['duration'] if output_info else input_info['duration'],
                'file_size': output_info['file_size'] if output_info else 0
            })
            
            logger.info(f"[Service14] ✅ {resolution} complete: {s3_key}")
        
        # Generate thumbnail
        thumbnail_info = None
        if generate_thumb:
            # STATUS UPDATE: generating thumbnail
            update_session_status(session_id, 'optimizing', {
                'processing_step': 'Generating thumbnail'
            })
            
            thumbnail_path = os.path.join(work_dir, f"thumbnail_{session_id}.jpg")
            if generate_thumbnail(input_path, thumbnail_path):
                thumb_s3_key = f"demos/{session_id}/thumbnail.jpg"
                thumb_url = upload_to_s3(thumbnail_path, thumb_s3_key, 'image/jpeg')
                thumbnail_info = {
                    's3_key': thumb_s3_key,
                    'public_url': thumb_url,
                    'download_url': generate_presigned_url(thumb_s3_key)
                }
                logger.info(f"[Service14] ✅ Thumbnail: {thumb_s3_key}")
        
        # Get primary output (prefer 720p for web sharing)
        primary_output = next((o for o in outputs if o['resolution'] == '720p'), outputs[0] if outputs else None)
        
        if not primary_output:
            raise Exception('No outputs generated')
        
        result = {
            'session_id': session_id,
            'input_key': stitched_key,
            'input_duration': input_info['duration'],
            'input_resolution': f"{input_info['width']}x{input_info['height']}",
            'outputs': outputs,
            'thumbnail': thumbnail_info,
            'resolutions_generated': len(outputs),
            'completed_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        # STATUS UPDATE: complete (final status!)
        update_session_status(session_id, 'complete', {
            'demo_url': primary_output['download_url'],
            'demo_url_720p': primary_output['download_url'],
            'demo_url_1080p': next((o['download_url'] for o in outputs if o['resolution'] == '1080p'), None),
            'thumbnail_url': thumbnail_info['download_url'] if thumbnail_info else None,
            'final_video_key': primary_output['s3_key'],
            'final_video_duration': str(primary_output['duration']),
            'final_video_size': primary_output['file_size'],
            'completed_at': datetime.utcnow().isoformat() + 'Z'
        })
        
        logger.info(f"[Service14] 🎉 Optimization complete for session {session_id}")
        
        # Trigger notification service
        trigger_notification_service(session_id)
        
        return result
        
    except Exception as e:
        # STATUS UPDATE: failed
        update_session_status(session_id, 'optimization_failed', {
            'error_message': str(e),
            'failed_at': datetime.utcnow().isoformat() + 'Z'
        })
        raise
        
    finally:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
            logger.info(f"[Service14] Cleaned up temp directory")


def lambda_handler(event, context):
    """
    Service 14: Video Optimizer
    Optimizes stitched video into multiple resolutions
    
    Triggered by Service 13 after stitching completes
    """
    logger.info(f"[Service14] Event: {json.dumps(event)}")
    
    try:
        # Parse event (from Service 13 async invoke)
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        # Accept both 'stitched_key' (from Service 13) and 'input_key'
        session_id = body.get('session_id') or body.get('project_name')
        stitched_key = body.get('stitched_key') or body.get('input_key')
        
        if not session_id:
            raise ValueError('session_id is required')
        
        if not stitched_key:
            raise ValueError('stitched_key or input_key is required')
        
        logger.info(f"[Service14] Processing session: {session_id}")
        
        # Process optimization
        result = process_optimization(session_id, stitched_key)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'data': result
            })
        }
        
    except ValueError as e:
        logger.error(f"[Service14] Validation error: {e}")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
        
    except Exception as e:
        logger.error(f"[Service14] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }