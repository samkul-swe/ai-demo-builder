"""
Service 16: Status Tracker
Provides real-time status updates for demo video processing
"""

import json
import os
import boto3
from datetime import datetime
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Configuration
TABLE_NAME = os.environ.get('SESSIONS_TABLE')


def get_session(session_id):
    """
    Retrieve session from DynamoDB
    
    Args:
        session_id: Session ID
        
    Returns:
        dict: Session data or None if not found
    """
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={'id': session_id})
        
        if 'Item' in response:
            return response['Item']
        
        logger.warning(f"[Service16] Session {session_id} not found")
        return None
        
    except Exception as e:
        logger.error(f"[Service16] Error getting session: {e}")
        return None


def calculate_progress(session):
    """
    Calculate detailed processing progress
    
    Args:
        session: Session data from DynamoDB
        
    Returns:
        dict: Detailed progress information
    """
    status = session.get('status', 'unknown')
    suggestions = session.get('suggestions', [])
    uploaded_videos = session.get('uploaded_videos', {})
    
    total_videos = len(suggestions)
    uploaded_count = len([v for v in uploaded_videos.values() if v.get('status') in ['uploaded', 'validated', 'converted']])
    validated_count = len([v for v in uploaded_videos.values() if v.get('status') in ['validated', 'converted']])
    converted_count = len([v for v in uploaded_videos.values() if v.get('status') == 'converted'])
    
    # Comprehensive status map matching your actual system
    status_info = {
        'ready': {
            'percentage': 10,
            'step': 'Ready for Upload',
            'step_number': 1,
            'total_steps': 7,
            'message': 'Session created. Ready to upload videos.',
            'emoji': '📝'
        },
        'uploading': {
            'percentage': 20 + (uploaded_count / total_videos * 20 if total_videos > 0 else 0),
            'step': 'Uploading Videos',
            'step_number': 2,
            'total_steps': 7,
            'message': f'Uploading videos... ({uploaded_count}/{total_videos} uploaded)',
            'emoji': '⬆️'
        },
        'ready_for_processing': {
            'percentage': 50,
            'step': 'Videos Ready',
            'step_number': 3,
            'total_steps': 7,
            'message': 'All videos uploaded and validated. Ready for processing.',
            'emoji': '✅'
        },
        'queued': {
            'percentage': 55,
            'step': 'Queued for Processing',
            'step_number': 4,
            'total_steps': 7,
            'message': 'Demo generation job queued. Processing will start shortly...',
            'emoji': '⏳'
        },
        'slides_ready': {
            'percentage': 60,
            'step': 'Creating Slides',
            'step_number': 4,
            'total_steps': 7,
            'message': 'Generating transition slides...',
            'emoji': '🎨'
        },
        'stitching': {
            'percentage': 70,
            'step': 'Stitching Videos',
            'step_number': 5,
            'total_steps': 7,
            'message': 'Combining videos and slides together...',
            'emoji': '🎬'
        },
        'stitched': {
            'percentage': 80,
            'step': 'Stitching Complete',
            'step_number': 5,
            'total_steps': 7,
            'message': 'Videos stitched successfully. Starting optimization...',
            'emoji': '✨'
        },
        'optimizing': {
            'percentage': 90,
            'step': 'Optimizing Video',
            'step_number': 6,
            'total_steps': 7,
            'message': 'Generating optimized versions (720p, 1080p)...',
            'emoji': '⚡'
        },
        'complete': {
            'percentage': 100,
            'step': 'Complete',
            'step_number': 7,
            'total_steps': 7,
            'message': '🎉 Your demo video is ready!',
            'emoji': '✅'
        },
        # Error states
        'validation_failed': {
            'percentage': 0,
            'step': 'Validation Failed',
            'step_number': 2,
            'total_steps': 7,
            'message': 'Video validation failed. Please check your videos.',
            'emoji': '❌'
        },
        'conversion_failed': {
            'percentage': 0,
            'step': 'Conversion Failed',
            'step_number': 3,
            'total_steps': 7,
            'message': 'Video conversion failed. Please try again.',
            'emoji': '❌'
        },
        'stitching_failed': {
            'percentage': 0,
            'step': 'Stitching Failed',
            'step_number': 5,
            'total_steps': 7,
            'message': 'Video stitching failed. Please contact support.',
            'emoji': '❌'
        },
        'optimization_failed': {
            'percentage': 0,
            'step': 'Optimization Failed',
            'step_number': 6,
            'total_steps': 7,
            'message': 'Video optimization failed. Please try again.',
            'emoji': '❌'
        }
    }
    
    # Get status info or default
    info = status_info.get(status, {
        'percentage': 0,
        'step': 'Unknown',
        'step_number': 0,
        'total_steps': 7,
        'message': f'Status: {status}',
        'emoji': '❓'
    })
    
    # Add current operation details if available
    current_operation = None
    if status == 'stitching':
        current_item = session.get('current_item', 0)
        total_items = session.get('total_items', 0)
        if current_item and total_items:
            current_operation = f"Processing item {current_item} of {total_items}"
    elif status == 'optimizing':
        processing_step = session.get('processing_step', '')
        if processing_step:
            current_operation = processing_step
    
    return {
        'percentage': int(info['percentage']),
        'step': info['step'],
        'step_number': info['step_number'],
        'total_steps': info['total_steps'],
        'message': info['message'],
        'emoji': info['emoji'],
        'current_operation': current_operation,
        'videos': {
            'total': total_videos,
            'uploaded': uploaded_count,
            'validated': validated_count,
            'converted': converted_count,
            'pending': total_videos - uploaded_count
        }
    }


def build_timeline(session):
    """
    Build timeline of processing events
    
    Args:
        session: Session data
        
    Returns:
        dict: Timeline information
    """
    timeline = {
        'created_at': session.get('created_at', ''),
        'queued_at': session.get('queued_at', ''),
        'stitching_started_at': session.get('stitching_started_at', ''),
        'stitching_completed_at': session.get('stitching_completed_at', ''),
        'optimizing_started_at': session.get('optimizing_started_at', ''),
        'completed_at': session.get('completed_at', '')
    }
    
    # Calculate elapsed time
    if timeline['created_at']:
        try:
            created = datetime.fromisoformat(timeline['created_at'].replace('Z', '+00:00'))
            now = datetime.utcnow()
            elapsed = (now - created).total_seconds()
            
            timeline['elapsed_seconds'] = int(elapsed)
            timeline['elapsed_formatted'] = format_duration(elapsed)
        except:
            pass
    
    return timeline


def format_duration(seconds):
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def get_video_details(session):
    """
    Get detailed information about uploaded videos
    
    Args:
        session: Session data
        
    Returns:
        list: Video details
    """
    uploaded_videos = session.get('uploaded_videos', {})
    suggestions = session.get('suggestions', [])
    
    video_details = []
    
    for suggestion in suggestions:
        seq_num = str(suggestion.get('sequence_number', 0))
        video_data = uploaded_videos.get(seq_num, {})
        
        video_details.append({
            'sequence_number': seq_num,
            'title': suggestion.get('title', f'Video {seq_num}'),
            'status': video_data.get('status', 'pending'),
            'uploaded': seq_num in uploaded_videos,
            'validated': video_data.get('status') in ['validated', 'converted'],
            'converted': video_data.get('status') == 'converted',
            's3_key': video_data.get('s3_key', ''),
            'duration': suggestion.get('duration', 'N/A')
        })
    
    return video_details


def get_result_urls(session):
    """
    Get all result URLs if available
    
    Args:
        session: Session data
        
    Returns:
        dict: Result URLs
    """
    if session.get('status') != 'complete':
        return None
    
    return {
        'demo_url': session.get('demo_url', ''),
        'demo_url_720p': session.get('demo_url_720p', ''),
        'demo_url_1080p': session.get('demo_url_1080p', ''),
        'thumbnail_url': session.get('thumbnail_url', ''),
        'final_video_key': session.get('final_video_key', ''),
        'final_video_duration': session.get('final_video_duration', ''),
        'final_video_size': session.get('final_video_size', 0)
    }


def get_error_info(session):
    """
    Get error information if processing failed
    
    Args:
        session: Session data
        
    Returns:
        dict: Error information or None
    """
    status = session.get('status', '')
    
    if not status.endswith('_failed'):
        return None
    
    return {
        'status': status,
        'message': session.get('error_message', 'An error occurred during processing'),
        'failed_at': session.get('failed_at', ''),
        'step': status.replace('_failed', '')
    }


def lambda_handler(event, context):
    """
    Service 16: Status Tracker
    Provides real-time status updates for demo processing
    
    GET /status/{session_id}
    """
    logger.info(f"[Service16] Event: {json.dumps(event)}")
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            },
            'body': ''
        }
    
    try:
        # Extract session_id from multiple possible locations
        session_id = None
        
        # 1. Try path parameters (preferred)
        if event.get('pathParameters'):
            session_id = event['pathParameters'].get('session_id')
        
        # 2. Try query string parameters
        if not session_id and event.get('queryStringParameters'):
            session_id = event['queryStringParameters'].get('session_id')
        
        # 3. Try body (for POST requests)
        if not session_id and event.get('body'):
            try:
                body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
                session_id = body.get('session_id')
            except:
                pass
        
        if not session_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': 'session_id is required in path, query, or body'
                })
            }
        
        logger.info(f"[Service16] Getting status for session: {session_id}")
        
        # Get session from DynamoDB
        session = get_session(session_id)
        
        if not session:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': f'Session {session_id} not found'
                })
            }
        
        # Build comprehensive status response
        status = session.get('status', 'unknown')
        progress = calculate_progress(session)
        timeline = build_timeline(session)
        video_details = get_video_details(session)
        result_urls = get_result_urls(session)
        error_info = get_error_info(session)
        
        response_data = {
            'session_id': session_id,
            'project_name': session.get('project_name', 'Unknown Project'),
            'owner': session.get('owner', 'unknown'),
            'github_url': session.get('github_url', ''),
            'status': status,
            'progress': progress,
            'timeline': timeline,
            'videos': video_details,
            'suggestions_count': len(session.get('suggestions', [])),
            'result': result_urls,
            'error': error_info
        }
        
        logger.info(f"[Service16] Status: {status}, Progress: {progress['percentage']}%")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache, no-store, must-revalidate'  # Don't cache status
            },
            'body': json.dumps({
                'success': True,
                'data': response_data
            })
        }
        
    except Exception as e:
        logger.error(f"[Service16] Error: {e}")
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