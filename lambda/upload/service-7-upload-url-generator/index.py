"""
Service 7: Upload URL Generator
Generates presigned S3 URLs for video uploads with validation

CORRECTED VERSION - Validates session and suggestions before generating URLs
"""

import json
import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from datetime import datetime

# Configure S3 client
s3_config = Config(
    region_name='us-west-1',
    s3={'addressing_style': 'virtual'}
)

s3_client = boto3.client('s3', config=s3_config)
dynamodb = boto3.resource('dynamodb')

# Get configuration from environment
BUCKET = os.environ.get('S3_BUCKET', 'ai-demo-builder')
SESSIONS_TABLE = os.environ.get('SESSIONS_TABLE', 'ai-demo-sessions')


def validate_session_and_suggestion(session_id: str, suggestion_id: int):
    """
    Validate that session exists and suggestion_id is valid
    
    Returns:
        tuple: (valid, error_message, session_data)
    """
    try:
        table = dynamodb.Table(SESSIONS_TABLE)
        
        # Get session from DynamoDB
        response = table.get_item(Key={'id': session_id})
        
        if 'Item' not in response:
            return False, f"Session '{session_id}' not found", None
        
        session = response['Item']
        
        # Check if session is in valid state for uploads
        status = session.get('status', '')
        if status not in ['ready', 'uploading']:
            return False, f"Session status is '{status}'. Cannot upload videos.", None
        
        # Validate suggestion_id exists in suggestions
        suggestions = session.get('suggestions', [])
        valid_ids = [s.get('sequence_number') for s in suggestions]
        
        if suggestion_id not in valid_ids:
            return False, f"Invalid suggestion_id {suggestion_id}. Valid IDs: {valid_ids}", None
        
        # Check if video already uploaded for this suggestion
        uploaded_videos = session.get('uploaded_videos', {})
        video_key = str(suggestion_id)
        
        if video_key in uploaded_videos:
            video_status = uploaded_videos[video_key].get('status', '')
            if video_status in ['uploaded', 'converted', 'processing']:
                return False, f"Video for suggestion {suggestion_id} already uploaded (status: {video_status})", None
        
        print(f"[Service7] ✅ Session and suggestion validated")
        return True, None, session
        
    except ClientError as e:
        error_msg = f"DynamoDB error: {str(e)}"
        print(f"[Service7] ❌ {error_msg}")
        return False, error_msg, None
    except Exception as e:
        error_msg = f"Validation error: {str(e)}"
        print(f"[Service7] ❌ {error_msg}")
        return False, error_msg, None


def mark_upload_initiated(session_id: str, suggestion_id: int, s3_key: str):
    """
    Update DynamoDB to mark upload as initiated
    """
    try:
        table = dynamodb.Table(SESSIONS_TABLE)
        
        video_key = str(suggestion_id)
        now = datetime.utcnow().isoformat() + 'Z'
        
        # Update session: add to uploaded_videos with "initiated" status
        table.update_item(
            Key={'id': session_id},
            UpdateExpression='SET uploaded_videos.#vid = :video_info, #status = :status, updated_at = :now',
            ExpressionAttributeNames={
                '#vid': video_key,
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':video_info': {
                    'status': 'initiated',
                    's3_key': s3_key,
                    'initiated_at': now
                },
                ':status': 'uploading',  # Change session status to "uploading"
                ':now': now
            }
        )
        
        print(f"[Service7] ✅ Marked upload as initiated in DynamoDB")
        return True
        
    except Exception as e:
        print(f"[Service7] ⚠️ Failed to update DynamoDB (non-critical): {str(e)}")
        return False


def lambda_handler(event, context):
    """
    Service 7: Upload URL Generator
    Generates presigned S3 URLs for video uploads after validation
    """
    try:
        print(f'[Service7] Starting Upload URL Generator')
        print(f'[Service7] Event: {json.dumps(event)}')
        
        # Parse body (API Gateway or direct invocation)
        if 'body' in event and isinstance(event['body'], str):
            body = json.loads(event['body'])
        else:
            body = event
        
        session_id = body.get('session_id')
        suggestion_id = body.get('suggestion_id')
        
        # Validate required parameters
        if not session_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': 'session_id is required'})
            }
        
        if not suggestion_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': 'suggestion_id is required'})
            }
        
        # Convert suggestion_id to int if it's a string
        try:
            suggestion_id = int(suggestion_id)
        except (ValueError, TypeError):
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': 'suggestion_id must be a number'})
            }
        
        print(f'[Service7] Session ID: {session_id}')
        print(f'[Service7] Suggestion ID: {suggestion_id}')
        
        # Validate session and suggestion
        valid, error_msg, session_data = validate_session_and_suggestion(session_id, suggestion_id)
        
        if not valid:
            print(f"[Service7] ❌ Validation failed: {error_msg}")
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': error_msg})
            }
        
        # Create S3 key
        s3_key = f'videos/{session_id}/{suggestion_id}.mp4'
        
        print(f'[Service7] Generating presigned URL for: {BUCKET}/{s3_key}')
        
        # Generate presigned URL
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET,
                'Key': s3_key,
                'ContentType': 'video/mp4'
            },
            ExpiresIn=3600,  # 1 hour
            HttpMethod='PUT'
        )
        
        print(f'[Service7] ✅ Generated presigned URL')
        
        # Mark upload as initiated in DynamoDB
        mark_upload_initiated(session_id, suggestion_id, s3_key)
        
        # Get project name for response
        project_name = session_data.get('project_name', 'unknown') if session_data else 'unknown'
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'upload_url': upload_url,
                'key': s3_key,
                'session_id': session_id,
                'suggestion_id': suggestion_id,
                'project_name': project_name,
                'bucket': BUCKET,
                'expires_in': 3600,
                'instructions': {
                    'method': 'PUT',
                    'headers': {
                        'Content-Type': 'video/mp4'
                    }
                }
            })
        }
        
    except ClientError as e:
        error_msg = f"AWS error: {str(e)}"
        print(f'[Service7] ❌ {error_msg}')
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': error_msg})
        }
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f'[Service7] ❌ {error_msg}')
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': error_msg})
        }