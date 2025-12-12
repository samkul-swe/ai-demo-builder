"""
Service 11: Job Queue Service
Manages video processing queue - triggers when user clicks "Generate Demo"

PYTHON VERSION - Simplified for your use case
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
sqs = boto3.client('sqs', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Environment variables
QUEUE_URL = os.environ.get('SQS_QUEUE_URL', '')
TABLE_NAME = os.environ.get('SESSIONS_TABLE')


def validate_session_ready(session_id):
    """
    Validate that session exists and all videos are converted
    
    Returns:
        tuple: (is_valid, error_message, session_data)
    """
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={'id': session_id})
        
        if 'Item' not in response:
            return False, f"Session '{session_id}' not found", None
        
        session = response['Item']
        
        # Check session status
        status = session.get('status', '')
        if status == 'complete':
            return False, "Demo already generated for this session", session
        
        if status == 'processing':
            return False, "Demo is already being processed", session
        
        if status not in ['ready_for_processing', 'uploading']:
            return False, f"Session not ready (status: {status})", session
        
        # Check if all videos are converted
        suggestions = session.get('suggestions', [])
        uploaded_videos = session.get('uploaded_videos', {})
        
        if not suggestions:
            return False, "No suggestions found in session", session
        
        total_suggestions = len(suggestions)
        converted_count = 0
        
        for suggestion in suggestions:
            suggestion_id = str(suggestion.get('sequence_number', 0))
            
            if suggestion_id not in uploaded_videos:
                return False, f"Video {suggestion_id} not uploaded yet", session
            
            video_data = uploaded_videos[suggestion_id]
            if video_data.get('status') != 'converted':
                current_status = video_data.get('status', 'unknown')
                return False, f"Video {suggestion_id} not converted yet (status: {current_status})", session
            
            converted_count += 1
        
        if converted_count != total_suggestions:
            return False, f"Only {converted_count}/{total_suggestions} videos converted", session
        
        logger.info(f"[Service11] ✅ Session validated: {converted_count}/{total_suggestions} videos ready")
        return True, None, session
        
    except Exception as e:
        logger.error(f"[Service11] Error validating session: {e}")
        return False, f"Validation error: {str(e)}", None


def send_to_queue(session_id, session_data):
    """
    Send job to SQS queue for video processing
    
    Returns:
        dict: Message details
    """
    try:
        if not QUEUE_URL:
            raise ValueError("SQS_QUEUE_URL not configured")
        
        # Create job message
        message = {
            'session_id': session_id,
            'action': 'stitch_videos',
            'project_name': session_data.get('project_name', 'unknown'),
            'total_videos': len(session_data.get('suggestions', [])),
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'source': 'service-11-job-queue'
        }
        
        logger.info(f"[Service11] Sending message to SQS: {QUEUE_URL}")
        
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
                },
                'project_name': {
                    'StringValue': session_data.get('project_name', 'unknown'),
                    'DataType': 'String'
                }
            }
        )
        
        message_id = response['MessageId']
        logger.info(f"[Service11] ✅ SQS message sent: {message_id}")
        
        return {
            'message_id': message_id,
            'queue_url': QUEUE_URL,
            'sent_at': datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        logger.error(f"[Service11] ❌ Failed to send SQS message: {e}")
        raise


def update_session_status(session_id, status, additional_data=None):
    """
    Update session status in DynamoDB
    """
    try:
        table = dynamodb.Table(TABLE_NAME)
        
        update_expr = 'SET #status = :status, updated_at = :now'
        expr_names = {'#status': 'status'}
        expr_values = {
            ':status': status,
            ':now': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Add additional data if provided
        if additional_data:
            for key, value in additional_data.items():
                attr_name = f'#{key}'
                attr_value = f':{key}'
                update_expr += f', {attr_name} = {attr_value}'
                expr_names[attr_name] = key
                expr_values[attr_value] = value
        
        table.update_item(
            Key={'id': session_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
        
        logger.info(f"[Service11] ✅ Updated session status: {session_id} → {status}")
        
    except Exception as e:
        logger.error(f"[Service11] ⚠️ Failed to update status: {e}")


def lambda_handler(event, context):
    """
    Service 11: Job Queue Service
    Validates session and queues video processing job
    
    This is called when user clicks "Generate Demo" button
    """
    logger.info(f"[Service11] Event: {json.dumps(event)}")
    
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
        # Parse event (API Gateway or direct invocation)
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        # Get session_id from path parameters or body
        session_id = None
        
        # Try path parameters first (e.g., POST /generate/{session_id})
        if 'pathParameters' in event:
            session_id = event['pathParameters'].get('session_id')
        
        # Try body
        if not session_id:
            session_id = body.get('session_id')
        
        if not session_id:
            logger.error("[Service11] Missing session_id")
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'error': 'session_id is required',
                    'hint': 'Provide session_id in request body or path parameter'
                })
            }
        
        logger.info(f"[Service11] Processing session: {session_id}")
        
        # Validate session is ready for processing
        is_valid, error_msg, session_data = validate_session_ready(session_id)
        
        if not is_valid:
            logger.error(f"[Service11] Validation failed: {error_msg}")
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'error': 'Session validation failed',
                    'message': error_msg,
                    'session_id': session_id
                })
            }
        
        # Update session status to "queued"
        update_session_status(session_id, 'queued', {
            'queued_at': datetime.utcnow().isoformat() + 'Z'
        })
        
        # Send job to SQS queue
        queue_result = send_to_queue(session_id, session_data)
        
        # Prepare response
        response_data = {
            'session_id': session_id,
            'project_name': session_data.get('project_name', 'unknown'),
            'status': 'queued',
            'message': 'Video processing job queued successfully',
            'queue_details': queue_result,
            'next_steps': [
                'Service 12 will create transition slides',
                'Service 13 will stitch videos together',
                'Service 14 will optimize final video',
                'You can check progress at GET /status/{session_id}'
            ]
        }
        
        logger.info(f"[Service11] ✅ Job queued successfully for session {session_id}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response_data)
        }
        
    except ValueError as e:
        logger.error(f"[Service11] ❌ Validation error: {e}")
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': str(e)
            })
        }
        
    except Exception as e:
        logger.error(f"[Service11] ❌ Unexpected error: {e}")
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