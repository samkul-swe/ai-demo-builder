"""
Service 13: Video Stitcher
Stitches slides and videos together into final demo
Triggered by Service 12 after slides are created
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
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Configuration - FIXED to match other services
BUCKET = os.environ.get('S3_BUCKET', 'ai-demo-builder')
TABLE_NAME = os.environ.get('SESSIONS_TABLE', 'ai-demo-sessions')
OPTIMIZER_FUNCTION = os.environ.get('OPTIMIZER_FUNCTION_NAME', 'service-14-video-optimizer')

# FFmpeg paths
FFMPEG_PATH = os.environ.get('FFMPEG_PATH', '/opt/python/bin/ffmpeg')
FFPROBE_PATH = os.environ.get('FFPROBE_PATH', '/opt/python/bin/ffprobe')

# Check FFmpeg paths exist, use fallbacks if needed
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

logger.info(f"[Service13] Using ffmpeg: {FFMPEG_PATH}")
logger.info(f"[Service13] Using ffprobe: {FFPROBE_PATH}")

# Video settings
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
SLIDE_DURATION = 3  # seconds per slide
VIDEO_BITRATE = '5M'
AUDIO_BITRATE = '192k'


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
            update_expr += f', {key} = :{key}'
            expr_values[f':{key}'] = value
    
    try:
        # ✅ FIXED: Use correct key format
        table.update_item(
            Key={'id': session_id},  # ✅ Changed from {PARTITION_KEY: session_id}
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
        logger.info(f"[Service13] Status updated: {session_id} -> {status}")
    except Exception as e:
        logger.error(f"[Service13] Could not update DynamoDB: {e}")


def get_session_data(session_id):
    """
    Retrieve session data from DynamoDB to get video keys
    
    Returns:
        dict: Session data with slides, videos, suggestions
    """
    try:
        table = dynamodb.Table(TABLE_NAME)
        
        # ✅ FIXED: Use correct key format
        response = table.get_item(Key={'id': session_id})
        
        if 'Item' not in response:
            raise ValueError(f"Session {session_id} not found")
        
        session = response['Item']
        logger.info(f"[Service13] Retrieved session: {session_id}")
        
        return session
        
    except Exception as e:
        logger.error(f"[Service13] Error getting session: {e}")
        raise


def build_media_sequence(session_id, slides_from_service12):
    """
    Build ordered sequence of slides + videos for stitching
    
    Flow:
    1. Title slide
    2. Section slide 1 → Video 1
    3. Section slide 2 → Video 2
    ...
    N. Section slide N → Video N
    N+1. End slide
    
    Returns:
        list: Ordered media items with type, s3_key, order
    """
    # Get session data (has uploaded_videos)
    session = get_session_data(session_id)
    
    uploaded_videos = session.get('uploaded_videos', {})
    suggestions = session.get('suggestions', [])
    
    media_items = []
    
    # Extract slides (already ordered by Service 12)
    slides_by_type = {}
    for slide in slides_from_service12:
        slide_type = slide.get('type', 'section')
        order = slide.get('order', 0)
        s3_key = slide.get('s3_key', '')
        
        if slide_type == 'title':
            slides_by_type['title'] = {'s3_key': s3_key, 'order': 0}
        elif slide_type == 'section':
            video_seq = slide.get('video_sequence', order)
            slides_by_type[f'section_{video_seq}'] = {
                's3_key': s3_key,
                'order': order,
                'video_sequence': video_seq
            }
        elif slide_type == 'end':
            slides_by_type['end'] = {'s3_key': s3_key, 'order': 999}
    
    # 1. Add title slide
    if 'title' in slides_by_type:
        media_items.append({
            'type': 'slide',
            'key': slides_by_type['title']['s3_key'],
            'order': 0,
            'duration': SLIDE_DURATION
        })
        logger.info(f"[Service13] Added title slide")
    
    # 2. Add section slides + videos in sequence
    for suggestion in sorted(suggestions, key=lambda x: x.get('sequence_number', 0)):
        seq_num = suggestion.get('sequence_number')
        
        # Add section slide
        section_key = f'section_{seq_num}'
        if section_key in slides_by_type:
            media_items.append({
                'type': 'slide',
                'key': slides_by_type[section_key]['s3_key'],
                'order': seq_num * 100,
                'duration': SLIDE_DURATION
            })
            logger.info(f"[Service13] Added section slide {seq_num}")
        
        # Add corresponding video (from Service 10)
        video_key = str(seq_num)
        if video_key in uploaded_videos:
            video_data = uploaded_videos[video_key]
            converted_data = video_data.get('converted_data', {})
            standardized_key = converted_data.get('standardized_key', '')
            
            if standardized_key and video_data.get('status') == 'converted':
                media_items.append({
                    'type': 'video',
                    'key': standardized_key,
                    'order': seq_num * 100 + 50
                })
                logger.info(f"[Service13] Added video {seq_num}: {standardized_key}")
            else:
                logger.warning(f"[Service13] Video {seq_num} not converted yet")
        else:
            logger.warning(f"[Service13] Video {seq_num} not found in uploaded_videos")
    
    # 3. Add end slide
    if 'end' in slides_by_type:
        media_items.append({
            'type': 'slide',
            'key': slides_by_type['end']['s3_key'],
            'order': 999,
            'duration': SLIDE_DURATION
        })
        logger.info(f"[Service13] Added end slide")
    
    # Sort by order
    media_items.sort(key=lambda x: x.get('order', 0))
    
    logger.info(f"[Service13] Built sequence: {len(media_items)} items")
    return media_items


def get_video_info(video_path):
    """Get video duration and properties using ffprobe"""
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
        
        duration = float(info.get('format', {}).get('duration', 0))
        
        video_stream = None
        audio_stream = None
        for stream in info.get('streams', []):
            if stream['codec_type'] == 'video' and not video_stream:
                video_stream = stream
            elif stream['codec_type'] == 'audio' and not audio_stream:
                audio_stream = stream
        
        return {
            'duration': duration,
            'width': video_stream.get('width', VIDEO_WIDTH) if video_stream else VIDEO_WIDTH,
            'height': video_stream.get('height', VIDEO_HEIGHT) if video_stream else VIDEO_HEIGHT,
            'has_audio': audio_stream is not None
        }
    except Exception as e:
        logger.error(f"[Service13] Error getting video info: {e}")
        return {'duration': 0, 'width': VIDEO_WIDTH, 'height': VIDEO_HEIGHT, 'has_audio': False}


def download_from_s3(s3_key, local_path):
    """Download file from S3"""
    logger.info(f"[Service13] Downloading s3://{BUCKET}/{s3_key}")
    s3_client.download_file(BUCKET, s3_key, local_path)
    return local_path


def upload_to_s3(local_path, s3_key):
    """Upload file to S3"""
    logger.info(f"[Service13] Uploading to s3://{BUCKET}/{s3_key}")
    s3_client.upload_file(
        local_path, 
        BUCKET, 
        s3_key,
        ExtraArgs={'ContentType': 'video/mp4'}
    )
    return f"https://{BUCKET}.s3.us-east-1.amazonaws.com/{s3_key}"


def create_video_from_slide(slide_path, output_path, duration=SLIDE_DURATION):
    """Convert a slide image to a video clip"""
    cmd = [
        FFMPEG_PATH,
        '-y',
        '-loop', '1',
        '-i', slide_path,
        '-c:v', 'libx264',
        '-t', str(duration),
        '-pix_fmt', 'yuv420p',
        '-vf', f'scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black',
        '-r', str(VIDEO_FPS),
        '-preset', 'fast',
        output_path
    ]
    
    logger.info(f"[Service13] Creating video from slide")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        logger.error(f"[Service13] FFmpeg stderr: {result.stderr}")
        raise Exception(f"Failed to create video from slide: {result.stderr}")
    
    return output_path


def add_silent_audio(input_path, output_path):
    """Add silent audio track to video without audio"""
    cmd = [
        FFMPEG_PATH,
        '-y',
        '-i', input_path,
        '-f', 'lavfi',
        '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-shortest',
        output_path
    ]
    
    logger.info(f"[Service13] Adding silent audio")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    if result.returncode != 0:
        logger.error(f"[Service13] FFmpeg stderr: {result.stderr}")
        raise Exception(f"Failed to add silent audio: {result.stderr}")
    
    return output_path


def concatenate_videos(video_paths, output_path):
    """Concatenate multiple videos using FFmpeg concat demuxer"""
    concat_file = output_path.replace('.mp4', '_concat.txt')
    
    with open(concat_file, 'w') as f:
        for video_path in video_paths:
            escaped_path = video_path.replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
    
    logger.info(f"[Service13] Concatenating {len(video_paths)} videos")
    
    cmd = [
        FFMPEG_PATH,
        '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', AUDIO_BITRATE,
        '-movflags', '+faststart',
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    if os.path.exists(concat_file):
        os.remove(concat_file)
    
    if result.returncode != 0:
        logger.error(f"[Service13] FFmpeg stderr: {result.stderr}")
        raise Exception(f"Failed to concatenate videos: {result.stderr}")
    
    return output_path


def process_stitching(session_id, slides):
    """Main stitching logic"""
    logger.info(f"[Service13] Starting stitching for session: {session_id}")
    logger.info(f"[Service13] Received {len(slides)} slides from Service 12")
    
    # STATUS UPDATE: stitching
    update_session_status(session_id, 'stitching', {
        'stitching_started_at': datetime.utcnow().isoformat() + 'Z'
    })
    
    # Build complete media sequence (slides + videos)
    media_items = build_media_sequence(session_id, slides)
    
    if not media_items:
        raise ValueError('No media items to stitch')
    
    logger.info(f"[Service13] Processing {len(media_items)} total items")
    
    work_dir = tempfile.mkdtemp()
    
    try:
        normalized_videos = []
        
        for idx, item in enumerate(media_items):
            item_type = item.get('type', 'video')
            s3_key = item.get('key')
            
            if not s3_key:
                continue
            
            # STATUS UPDATE: processing item X of Y
            update_session_status(session_id, 'stitching', {
                'current_item': idx + 1,
                'total_items': len(media_items),
                'processing_step': f'Processing {item_type} {idx + 1}/{len(media_items)}'
            })
            
            ext = '.png' if item_type == 'slide' else '.mp4'
            local_path = os.path.join(work_dir, f'input_{idx}{ext}')
            download_from_s3(s3_key, local_path)
            
            normalized_path = os.path.join(work_dir, f'normalized_{idx}.mp4')
            
            if item_type == 'slide':
                slide_duration = item.get('duration', SLIDE_DURATION)
                slide_video = os.path.join(work_dir, f'slide_video_{idx}.mp4')
                create_video_from_slide(local_path, slide_video, slide_duration)
                add_silent_audio(slide_video, normalized_path)
            else:
                # Video already normalized by Service 10, but add audio if needed
                info = get_video_info(local_path)
                if not info.get('has_audio'):
                    add_silent_audio(local_path, normalized_path)
                else:
                    shutil.copy(local_path, normalized_path)
            
            normalized_videos.append(normalized_path)
            logger.info(f"[Service13] Processed item {idx + 1}/{len(media_items)}: {item_type}")
        
        if not normalized_videos:
            raise ValueError('No valid media items processed')
        
        # STATUS UPDATE: concatenating
        update_session_status(session_id, 'stitching', {
            'processing_step': 'Concatenating all videos'
        })
        
        output_filename = f"demo_{session_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.mp4"
        output_path = os.path.join(work_dir, output_filename)
        
        concatenate_videos(normalized_videos, output_path)
        
        output_info = get_video_info(output_path)
        
        # STATUS UPDATE: uploading
        update_session_status(session_id, 'stitching', {
            'processing_step': 'Uploading stitched video'
        })
        
        output_s3_key = f"demos/{session_id}/stitched_{output_filename}"
        output_url = upload_to_s3(output_path, output_s3_key)
        
        result = {
            'session_id': session_id,
            'stitched_key': output_s3_key,
            'stitched_url': output_url,
            'duration': output_info['duration'],
            'resolution': f"{output_info['width']}x{output_info['height']}",
            'items_processed': len(normalized_videos),
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        # STATUS UPDATE: stitched (ready for optimization)
        update_session_status(session_id, 'stitched', {
            'stitched_video_key': output_s3_key,
            'stitched_video_url': output_url,
            'stitched_video_duration': str(output_info['duration']),
            'stitched_video_resolution': f"{output_info['width']}x{output_info['height']}",
            'stitching_completed_at': datetime.utcnow().isoformat() + 'Z'
        })
        
        # Trigger Service 14 (Optimizer) asynchronously
        trigger_optimizer(session_id, output_s3_key)
        
        return result
        
    except Exception as e:
        # STATUS UPDATE: failed
        update_session_status(session_id, 'stitching_failed', {
            'error_message': str(e),
            'failed_at': datetime.utcnow().isoformat() + 'Z'
        })
        raise
        
    finally:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
            logger.info(f"[Service13] Cleaned up temp directory")


def trigger_optimizer(session_id, stitched_key):
    """Trigger Service 14 (Video Optimizer) asynchronously"""
    try:
        payload = {
            'session_id': session_id,
            'stitched_key': stitched_key
        }
        
        logger.info(f"[Service13] Triggering optimizer: {OPTIMIZER_FUNCTION}")
        
        lambda_client.invoke(
            FunctionName=OPTIMIZER_FUNCTION,
            InvocationType='Event',  # Asynchronous
            Payload=json.dumps(payload)
        )
        
        logger.info(f"[Service13] ✅ Triggered Service 14 (Video Optimizer)")
        
    except Exception as e:
        logger.error(f"[Service13] ⚠️ Failed to trigger optimizer (non-critical): {e}")


def lambda_handler(event, context):
    """
    Service 13: Video Stitcher
    Stitches slides and videos into final demo
    
    Triggered by Service 12 after slides are created
    """
    logger.info(f"[Service13] Event: {json.dumps(event)}")
    
    try:
        # Parse event (from Service 12 async invoke)
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        session_id = body.get('session_id')
        slides = body.get('slides', [])
        
        if not session_id:
            raise ValueError('session_id is required')
        
        if not slides:
            raise ValueError('slides are required')
        
        logger.info(f"[Service13] Processing session: {session_id}")
        
        # Process stitching
        result = process_stitching(session_id, slides)
        
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
        logger.error(f"[Service13] Validation error: {e}")
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
        logger.error(f"[Service13] Error: {e}")
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