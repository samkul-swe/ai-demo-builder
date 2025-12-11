"""
Service 15: Notification Service
Sends notifications when demo video processing is complete

Triggered by Service 14 after optimization completes
"""

import json
import os
import boto3
import urllib.request
import urllib.parse
from datetime import datetime
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sns_client = boto3.client('sns', region_name='us-west-1')
dynamodb = boto3.resource('dynamodb', region_name='us-west-1')
lambda_client = boto3.client('lambda', region_name='us-west-1')

# Configuration
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'ai-demo-sessions')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
HTTP_WEBHOOK_URL = os.environ.get('HTTP_WEBHOOK_URL', '')
ENABLE_EMAIL = os.environ.get('ENABLE_EMAIL_NOTIFICATIONS', 'false').lower() == 'true'


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
        
        logger.warning(f"[Service15] Session {session_id} not found")
        return None
        
    except Exception as e:
        logger.error(f"[Service15] Error getting session: {e}")
        return None


def send_cloudwatch_notification(session_id, demo_url, project_name, thumbnail_url=None):
    """
    Log notification to CloudWatch Logs (always free, always works)
    
    This is the simplest notification method - just logs to CloudWatch.
    Perfect for debugging and always available!
    """
    notification_message = f"""
╔═══════════════════════════════════════════════════════════╗
║           🎉 DEMO VIDEO READY NOTIFICATION 🎉            ║
╠═══════════════════════════════════════════════════════════╣
║ Project: {project_name}
║ Session ID: {session_id}
║ Status: ✅ Complete
║ Time: {datetime.utcnow().isoformat()}Z
║ 
║ Demo URL (720p): {demo_url}
║ Thumbnail: {thumbnail_url or 'N/A'}
║ 
║ 🎬 Your demo video is ready for download!
╚═══════════════════════════════════════════════════════════╝
"""
    
    logger.info("=" * 60)
    logger.info("NOTIFICATION SENT")
    logger.info("=" * 60)
    logger.info(notification_message)
    logger.info("=" * 60)


def send_http_webhook(session_id, demo_url, project_name, thumbnail_url=None):
    """
    Send HTTP webhook notification (if configured)
    
    Args:
        session_id: Session ID
        demo_url: Demo video URL
        project_name: Project name
        thumbnail_url: Thumbnail URL (optional)
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not HTTP_WEBHOOK_URL:
        logger.info("[Service15] HTTP webhook not configured, skipping")
        return False
    
    try:
        webhook_data = {
            'event': 'demo_ready',
            'session_id': session_id,
            'project_name': project_name,
            'demo_url': demo_url,
            'thumbnail_url': thumbnail_url,
            'message': f'Your demo video for {project_name} is ready!',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        req = urllib.request.Request(
            HTTP_WEBHOOK_URL,
            data=json.dumps(webhook_data).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'AI-Demo-Builder/1.0'
            }
        )
        
        response = urllib.request.urlopen(req, timeout=10)
        logger.info(f"[Service15] ✅ HTTP webhook sent (status: {response.status})")
        return True
        
    except Exception as e:
        logger.error(f"[Service15] ⚠️ HTTP webhook failed: {e}")
        return False


def send_sns_notification(session_id, demo_url, project_name, thumbnail_url=None):
    """
    Send SNS notification (if configured)
    
    Args:
        session_id: Session ID
        demo_url: Demo video URL
        project_name: Project name
        thumbnail_url: Thumbnail URL (optional)
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not SNS_TOPIC_ARN:
        logger.info("[Service15] SNS topic not configured, skipping")
        return False
    
    try:
        message_data = {
            'event': 'demo_ready',
            'session_id': session_id,
            'project_name': project_name,
            'demo_url': demo_url,
            'thumbnail_url': thumbnail_url,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Send both JSON (for SQS/Lambda subscribers) and formatted text (for email)
        message_text = f"""
Demo Video Ready!

Project: {project_name}
Session: {session_id}

Your demo video is ready to download:
{demo_url}

{f'Thumbnail: {thumbnail_url}' if thumbnail_url else ''}

Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f'Demo Ready: {project_name}',
            Message=json.dumps({
                'default': message_text,
                'email': message_text,
                'sqs': json.dumps(message_data),
                'lambda': json.dumps(message_data)
            }),
            MessageStructure='json'
        )
        
        message_id = response.get('MessageId', 'unknown')
        logger.info(f"[Service15] ✅ SNS notification sent (ID: {message_id})")
        return True
        
    except Exception as e:
        logger.error(f"[Service15] ⚠️ SNS notification failed: {e}")
        return False


def process_notification(session_id):
    """
    Main notification processing logic
    
    Args:
        session_id: Session ID to send notification for
        
    Returns:
        dict: Notification results
    """
    logger.info(f"[Service15] Processing notification for session: {session_id}")
    
    # Get session data
    session = get_session(session_id)
    
    if not session:
        raise ValueError(f"Session {session_id} not found")
    
    # Check session status
    status = session.get('status', '')
    if status != 'complete':
        logger.warning(f"[Service15] Session {session_id} not complete (status: {status})")
        return {
            'session_id': session_id,
            'status': status,
            'notification_sent': False,
            'reason': f'Session status is {status}, not complete'
        }
    
    # Extract notification data
    project_name = session.get('project_name', 'Unknown Project')
    demo_url = session.get('demo_url', '')
    thumbnail_url = session.get('thumbnail_url', '')
    
    if not demo_url:
        logger.warning(f"[Service15] No demo_url for session {session_id}")
        return {
            'session_id': session_id,
            'status': status,
            'notification_sent': False,
            'reason': 'No demo_url available'
        }
    
    logger.info(f"[Service15] Sending notifications for: {project_name}")
    
    # Send notifications via all available channels
    results = {
        'cloudwatch': True,  # Always succeeds (it's just logging)
        'webhook': False,
        'sns': False
    }
    
    # 1. CloudWatch Logs (always)
    send_cloudwatch_notification(session_id, demo_url, project_name, thumbnail_url)
    
    # 2. HTTP Webhook (if configured)
    if HTTP_WEBHOOK_URL:
        results['webhook'] = send_http_webhook(session_id, demo_url, project_name, thumbnail_url)
    
    # 3. SNS (if configured)
    if SNS_TOPIC_ARN:
        results['sns'] = send_sns_notification(session_id, demo_url, project_name, thumbnail_url)
    
    # Count successes
    notifications_sent = sum(1 for v in results.values() if v)
    
    logger.info(f"[Service15] ✅ Sent {notifications_sent} notifications for session {session_id}")
    
    return {
        'session_id': session_id,
        'project_name': project_name,
        'status': status,
        'demo_url': demo_url,
        'notification_sent': True,
        'notifications': results,
        'notifications_count': notifications_sent,
        'sent_at': datetime.utcnow().isoformat() + 'Z'
    }


def lambda_handler(event, context):
    """
    Service 15: Notification Service
    Sends notifications when demo video is ready
    
    Triggered by:
    1. Service 14 (Video Optimizer) after completion
    2. Manual API call
    """
    logger.info(f"[Service15] Event: {json.dumps(event)}")
    
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
        # Parse event (from Service 14 async invoke or API Gateway)
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        session_id = body.get('session_id')
        
        if not session_id:
            raise ValueError('session_id is required')
        
        logger.info(f"[Service15] Processing notification for session: {session_id}")
        
        # Process notification
        result = process_notification(session_id)
        
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
        logger.error(f"[Service15] Validation error: {e}")
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
        logger.error(f"[Service15] Error: {e}")
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