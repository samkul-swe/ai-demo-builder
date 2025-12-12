"""
Service 8: Upload Tracker
Tracks video upload progress - triggered by S3 events or API calls
"""

import json
import os
import boto3
from urllib.parse import unquote_plus
from datetime import datetime
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Environment variables
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'ai-demo-sessions')
BUCKET = os.environ.get('S3_BUCKET', 'ai-demo-builder')
VALIDATOR_FUNCTION = os.environ.get('VALIDATOR_FUNCTION_NAME', 'service-9-video-validator')


def lambda_handler(event, context):
    """
    Service 8: Upload Tracker
    Track video upload progress - triggered by S3 events or API calls
    """
    logger.info(f"[Service8] Event: {json.dumps(event)}")
    
    try:
        # Check if this is an S3 event
        if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:s3':
            return handle_s3_event(event)
        
        # Check if this is an API Gateway request
        if 'httpMethod' in event:
            return handle_api_request(event)
        
        # Unknown event type
        logger.warning("[Service8] Unknown event type")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Unknown event type'})
        }
        
    except Exception as e:
        logger.error(f"[Service8] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def handle_s3_event(event):
    """
    Handle S3 object creation events
    Triggered when a video is uploaded to S3
    """
    results = []
    table = dynamodb.Table(TABLE_NAME)
    
    for record in event['Records']:
        # Check if this is an object creation event
        if not record['eventName'].startswith('ObjectCreated:'):
            logger.info(f"[Service8] Skipping non-creation event: {record['eventName']}")
            continue
        
        # Parse S3 event
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        size = record['s3']['object']['size']
        event_time = record.get('eventTime', datetime.utcnow().isoformat() + 'Z')
        
        logger.info(f"[Service8] File uploaded: {key}, Size: {size} bytes")
        
        # Parse key format: videos/session-id/suggestion-id.mp4
        key_parts = key.split('/')
        if len(key_parts) >= 3 and key_parts[0] == 'videos':
            session_id = key_parts[1]
            file_name = key_parts[2]
            
            # FIXED: Extract suggestion_id from filename
            # Format: "1.mp4" or "1_timestamp.mp4"
            suggestion_id = file_name.split('.')[0].split('_')[0]
            
            logger.info(f"[Service8] Parsed - Session: {session_id}, Suggestion: {suggestion_id}")
            
            try:
                # Update DynamoDB with upload completion
                response = table.update_item(
                    Key={'id': session_id},
                    UpdateExpression='SET uploaded_videos.#suggId = :videoInfo, #status = :status, updated_at = :updated',
                    ExpressionAttributeNames={
                        '#suggId': suggestion_id,
                        '#status': 'status'
                    },
                    ExpressionAttributeValues={
                        ':videoInfo': {
                            'status': 'uploaded',
                            's3_key': key,
                            'file_size': size,
                            'uploaded_at': event_time
                        },
                        ':status': 'uploading',
                        ':updated': datetime.utcnow().isoformat() + 'Z'
                    },
                    ReturnValues='ALL_NEW'
                )
                
                logger.info(f"[Service8] ✅ Updated upload status for session {session_id}, suggestion {suggestion_id}")
                
                # Check if all videos are uploaded
                updated_session = response.get('Attributes', {})
                check_upload_completion(updated_session)
                
                # Trigger video validation
                trigger_validation(session_id, suggestion_id, key)
                
                results.append({
                    'sessionId': session_id,
                    'suggestionId': suggestion_id,
                    'key': key,
                    'size': size,
                    'status': 'uploaded'
                })
                
            except Exception as e:
                logger.error(f"[Service8] Failed to update DynamoDB: {e}")
                results.append({
                    'key': key,
                    'error': str(e)
                })
        else:
            logger.warning(f"[Service8] Invalid S3 key format: {key}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({'processed': results})
    }


def handle_api_request(event):
    """
    Handle API Gateway requests for upload status
    GET /upload-status?session_id=xxx
    """
    logger.info("[Service8] Handling API request")
    
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
    
    # Get session_id from query parameters or path parameters
    session_id = None
    
    # Try query parameters first
    params = event.get('queryStringParameters', {}) or {}
    session_id = params.get('session_id')
    
    # Try path parameters if not in query
    if not session_id:
        path_params = event.get('pathParameters', {}) or {}
        session_id = path_params.get('session_id')
    
    if not session_id:
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': 'Missing session_id parameter'})
        }
    
    # Get session from DynamoDB
    table = dynamodb.Table(TABLE_NAME)
    try:
        response = table.get_item(Key={'id': session_id})
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': 'Session not found'})
            }
        
        session = response['Item']
        
        # Verify S3 files exist for uploaded videos
        uploaded_videos = session.get('uploaded_videos', {})
        for suggestion_id, video_info in uploaded_videos.items():
            if 's3_key' in video_info:
                # Verify file exists in S3
                try:
                    s3_response = s3_client.head_object(Bucket=BUCKET, Key=video_info['s3_key'])
                    video_info['exists'] = True
                    video_info['s3_size'] = s3_response.get('ContentLength', 0)
                except Exception as e:
                    logger.warning(f"[Service8] File not found in S3: {video_info['s3_key']}")
                    video_info['exists'] = False
        
        # Calculate progress
        total_suggestions = len(session.get('suggestions', []))
        total_uploaded = len([v for v in uploaded_videos.values() if v.get('status') in ['uploaded', 'converted']])
        total_validated = len([v for v in uploaded_videos.values() if v.get('status') == 'converted'])
        
        # Prepare response
        response_data = {
            'session_id': session_id,
            'project_name': session.get('project_name', 'Unknown'),
            'status': session.get('status', 'unknown'),
            'progress': {
                'total_suggestions': total_suggestions,
                'uploaded': total_uploaded,
                'validated': total_validated,
                'pending': total_suggestions - total_uploaded,
                'percentage': int((total_uploaded / total_suggestions * 100)) if total_suggestions > 0 else 0,
                'all_uploaded': total_uploaded == total_suggestions,
                'all_validated': total_validated == total_suggestions
            },
            'uploaded_videos': uploaded_videos,
            'created_at': session.get('created_at'),
            'updated_at': session.get('updated_at')
        }
        
        logger.info(f"[Service8] Upload status: {total_uploaded}/{total_suggestions} uploaded")
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response_data)
        }
        
    except Exception as e:
        logger.error(f"[Service8] Error retrieving session: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)})
        }


def check_upload_completion(session):
    """
    Check if all videos are uploaded and update session status if complete
    """
    try:
        session_id = session.get('id')
        total_suggestions = len(session.get('suggestions', []))
        uploaded_videos = session.get('uploaded_videos', {})
        total_uploaded = len([v for v in uploaded_videos.values() if v.get('status') in ['uploaded', 'converted']])
        
        if total_uploaded == total_suggestions and total_suggestions > 0:
            logger.info(f"[Service8] 🎉 All videos uploaded for session {session_id} ({total_uploaded}/{total_suggestions})")
            # Note: Don't change status to "ready_to_process" yet
            # Wait until all videos are validated/converted by Services 9-10
        else:
            logger.info(f"[Service8] Upload progress: {total_uploaded}/{total_suggestions}")
    
    except Exception as e:
        logger.warning(f"[Service8] Error checking completion: {e}")


def trigger_validation(session_id, suggestion_id, s3_key):
    """
    Trigger Service 9 (Video Validator) asynchronously
    """
    try:
        payload = {
            'session_id': session_id,
            'suggestion_id': suggestion_id,
            's3_key': s3_key
        }
        
        logger.info(f"[Service8] Triggering validation: {VALIDATOR_FUNCTION}")
        
        lambda_client.invoke(
            FunctionName=VALIDATOR_FUNCTION,
            InvocationType='Event',  # Asynchronous - fire and forget
            Payload=json.dumps(payload)
        )
        
        logger.info(f"[Service8] ✅ Triggered validation for {s3_key}")
        
    except Exception as e:
        logger.error(f"[Service8] ⚠️ Failed to trigger validation (non-critical): {e}")