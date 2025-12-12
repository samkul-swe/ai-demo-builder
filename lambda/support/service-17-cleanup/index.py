"""
Service 17: Cleanup Service
Removes expired sessions and associated S3 objects

Supports:
1. Scheduled cleanup (CloudWatch Events - daily)
2. Immediate intermediate cleanup (triggered by Service 14)
3. Manual cleanup (API call)
"""

import json
import os
import boto3
from datetime import datetime, timedelta
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3_client = boto3.client('s3', region_name='us-east-1')

# Configuration
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'ai-demo-sessions')
BUCKET = os.environ.get('S3_BUCKET', 'ai-demo-builder')
DAYS_TO_KEEP = int(os.environ.get('DAYS_TO_KEEP', '30'))
FAILED_SESSION_DAYS = int(os.environ.get('FAILED_SESSION_DAYS', '7'))


def list_s3_objects(prefix):
    """
    List all S3 objects with given prefix
    
    Args:
        prefix: S3 prefix to list
        
    Returns:
        list: List of object keys
    """
    try:
        objects = []
        paginator = s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            if 'Contents' in page:
                objects.extend([obj['Key'] for obj in page['Contents']])
        
        return objects
        
    except Exception as e:
        logger.error(f"[Service17] Error listing S3 objects: {e}")
        return []


def delete_s3_objects(keys):
    """
    Delete multiple S3 objects
    
    Args:
        keys: List of S3 object keys to delete
        
    Returns:
        int: Number of objects deleted
    """
    if not keys:
        return 0
    
    try:
        # S3 allows deleting up to 1000 objects at once
        deleted_count = 0
        
        for i in range(0, len(keys), 1000):
            batch = keys[i:i+1000]
            objects = [{'Key': key} for key in batch]
            
            response = s3_client.delete_objects(
                Bucket=BUCKET,
                Delete={'Objects': objects}
            )
            
            deleted = len(response.get('Deleted', []))
            deleted_count += deleted
            
            logger.info(f"[Service17] Deleted {deleted} S3 objects")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"[Service17] Error deleting S3 objects: {e}")
        return 0


def delete_session_record(session_id):
    """
    Delete session record from DynamoDB
    
    Args:
        session_id: Session ID to delete
        
    Returns:
        bool: True if successful
    """
    try:
        table = dynamodb.Table(TABLE_NAME)
        table.delete_item(Key={'id': session_id})
        
        logger.info(f"[Service17] Deleted session record: {session_id}")
        return True
        
    except Exception as e:
        logger.error(f"[Service17] Error deleting session: {e}")
        return False


def cleanup_all_session_files(session_id):
    """
    Delete ALL files for a session (complete cleanup)
    
    Args:
        session_id: Session ID
        
    Returns:
        dict: Cleanup results
    """
    logger.info(f"[Service17] Complete cleanup for session: {session_id}")
    
    prefixes = [
        f'videos/{session_id}/',   # Original uploads + standardized
        f'slides/{session_id}/',   # Slide images
        f'demos/{session_id}/'     # Stitched + final demos
    ]
    
    total_deleted = 0
    deleted_by_prefix = {}
    
    for prefix in prefixes:
        objects = list_s3_objects(prefix)
        deleted = delete_s3_objects(objects)
        deleted_by_prefix[prefix] = deleted
        total_deleted += deleted
    
    return {
        'session_id': session_id,
        'total_files_deleted': total_deleted,
        'details': deleted_by_prefix
    }


def cleanup_intermediate_files(session_id):
    """
    Delete intermediate files, keep only final demos
    
    Use this after demo is complete to save storage costs.
    Keeps: final optimized videos (720p, 1080p, thumbnail)
    Deletes: uploads, standardized, slides, stitched
    
    Args:
        session_id: Session ID
        
    Returns:
        dict: Cleanup results
    """
    logger.info(f"[Service17] Intermediate cleanup for session: {session_id}")
    
    # 1. Delete original uploads
    uploads = list_s3_objects(f'videos/{session_id}/')
    # Keep nothing from videos/ (all are intermediate)
    deleted_uploads = delete_s3_objects(uploads)
    
    # 2. Delete slides (no longer needed)
    slides = list_s3_objects(f'slides/{session_id}/')
    deleted_slides = delete_s3_objects(slides)
    
    # 3. Delete stitched video (keep only optimized finals)
    demos = list_s3_objects(f'demos/{session_id}/')
    # Keep only files with 'final_' prefix
    to_delete = [key for key in demos if 'stitched_' in key or 'final_' not in key]
    deleted_demos = delete_s3_objects(to_delete)
    
    total_deleted = deleted_uploads + deleted_slides + deleted_demos
    
    logger.info(f"[Service17] ✅ Cleaned {total_deleted} intermediate files for {session_id}")
    
    return {
        'session_id': session_id,
        'total_files_deleted': total_deleted,
        'uploads_deleted': deleted_uploads,
        'slides_deleted': deleted_slides,
        'demos_deleted': deleted_demos
    }


def scan_expired_sessions():
    """
    Scan DynamoDB for expired sessions
    
    Note: DynamoDB TTL will automatically delete records, but NOT S3 files.
    This function finds sessions that should be cleaned up.
    
    Returns:
        list: List of expired session IDs
    """
    try:
        table = dynamodb.Table(TABLE_NAME)
        
        now_timestamp = int(datetime.utcnow().timestamp())
        threshold_timestamp = int((datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)).timestamp())
        failed_threshold = int((datetime.utcnow() - timedelta(days=FAILED_SESSION_DAYS)).timestamp())
        
        expired_sessions = []
        
        # Scan with pagination
        scan_kwargs = {}
        
        while True:
            response = table.scan(**scan_kwargs)
            
            for item in response.get('Items', []):
                session_id = item.get('id')
                expires_at = item.get('expires_at', 0)
                status = item.get('status', '')
                created_at_str = item.get('created_at', '')
                
                # Parse created_at timestamp
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    created_timestamp = int(created_at.timestamp())
                except:
                    created_timestamp = 0
                
                # Cleanup conditions:
                # 1. Session has explicit expires_at that's passed
                if expires_at and expires_at < now_timestamp:
                    expired_sessions.append(session_id)
                    continue
                
                # 2. Complete sessions older than DAYS_TO_KEEP
                if status == 'complete' and created_timestamp < threshold_timestamp:
                    expired_sessions.append(session_id)
                    continue
                
                # 3. Failed sessions older than FAILED_SESSION_DAYS
                if status.endswith('_failed') and created_timestamp < failed_threshold:
                    expired_sessions.append(session_id)
                    continue
            
            # Check for more pages
            last_key = response.get('LastEvaluatedKey')
            if not last_key:
                break
            
            scan_kwargs['ExclusiveStartKey'] = last_key
        
        logger.info(f"[Service17] Found {len(expired_sessions)} expired sessions")
        return expired_sessions
        
    except Exception as e:
        logger.error(f"[Service17] Error scanning for expired sessions: {e}")
        return []


def scheduled_cleanup():
    """
    Scheduled cleanup - runs daily via CloudWatch Events
    
    Finds and deletes expired sessions and their S3 files
    
    Returns:
        dict: Cleanup results
    """
    logger.info("[Service17] Starting scheduled cleanup")
    
    expired_sessions = scan_expired_sessions()
    
    results = {
        'sessions_found': len(expired_sessions),
        'sessions_cleaned': 0,
        'total_files_deleted': 0,
        'errors': []
    }
    
    for session_id in expired_sessions:
        try:
            # Delete all S3 files
            cleanup_result = cleanup_all_session_files(session_id)
            results['total_files_deleted'] += cleanup_result['total_files_deleted']
            
            # Delete DynamoDB record
            delete_session_record(session_id)
            
            results['sessions_cleaned'] += 1
            logger.info(f"[Service17] ✅ Cleaned session: {session_id}")
            
        except Exception as e:
            error_msg = f"Error cleaning {session_id}: {str(e)}"
            logger.error(f"[Service17] {error_msg}")
            results['errors'].append(error_msg)
    
    logger.info(f"[Service17] ✅ Scheduled cleanup complete: {results['sessions_cleaned']}/{results['sessions_found']} sessions")
    
    return results


def lambda_handler(event, context):
    """
    Service 17: Cleanup Service
    
    Supports multiple modes:
    1. Scheduled cleanup (CloudWatch Events)
    2. Immediate intermediate cleanup (from Service 14)
    3. Manual cleanup (API call)
    """
    logger.info(f"[Service17] Event: {json.dumps(event)}")
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            },
            'body': ''
        }
    
    try:
        # Determine cleanup mode
        
        # Mode 1: Scheduled cleanup (CloudWatch Events)
        if event.get('source') == 'aws.events':
            logger.info("[Service17] Running scheduled cleanup")
            results = scheduled_cleanup()
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'success': True,
                    'mode': 'scheduled',
                    'data': results
                })
            }
        
        # Mode 2 & 3: API call or Lambda invoke
        # Parse body
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        session_id = body.get('session_id')
        cleanup_mode = body.get('mode', 'complete')  # 'complete' or 'intermediate'
        
        if not session_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': 'session_id is required'
                })
            }
        
        logger.info(f"[Service17] Cleanup mode: {cleanup_mode} for session: {session_id}")
        
        # Mode 2: Intermediate cleanup (keep finals)
        if cleanup_mode == 'intermediate':
            results = cleanup_intermediate_files(session_id)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': True,
                    'mode': 'intermediate',
                    'data': results
                })
            }
        
        # Mode 3: Complete cleanup (delete everything)
        else:
            results = cleanup_all_session_files(session_id)
            
            # Also delete session record
            delete_session_record(session_id)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': True,
                    'mode': 'complete',
                    'data': results
                })
            }
        
    except Exception as e:
        logger.error(f"[Service17] Error: {e}")
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