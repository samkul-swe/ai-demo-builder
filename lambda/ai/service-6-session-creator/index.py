"""
Service 6: Session Creator
Stores AI-generated demo session data in DynamoDB
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
SESSIONS_TABLE_NAME = os.environ.get('SESSIONS_TABLE_NAME', 'ai-demo-sessions')


def lambda_handler(event, context):
    """
    Service 6: Session Creator
    Stores session data in DynamoDB after AI suggestions are generated
    
    Called asynchronously (fire-and-forget) by Service 5
    """
    try:
        print("[Service6] Starting Session Creator")
        print(f"[Service6] Table: {SESSIONS_TABLE_NAME}")
        print(f"[Service6] Event keys: {list(event.keys())}")

        # Extract data from Service 5
        session_id = event.get('session_id')
        github_data = event.get('github_data', {})
        project_analysis = event.get('project_analysis', {})
        suggestions = event.get('suggestions', {})
        project_metadata = event.get('project_metadata', {})
        
        # Validate required fields
        if not session_id:
            raise ValueError("session_id is required")
        
        if not github_data:
            raise ValueError("github_data is required")
        
        # Extract project details
        project_name = github_data.get('projectName', 'Unknown')
        owner = github_data.get('owner', 'unknown')
        commit_sha = github_data.get('commit_sha', 'unknown')
        github_url = f"https://github.com/{owner}/{project_name}"
        
        if not project_name or project_name == 'Unknown':
            raise ValueError("projectName is required in github_data")
        
        print(f"[Service6] Session ID: {session_id}")
        print(f"[Service6] Project: {owner}/{project_name}")
        print(f"[Service6] Commit SHA: {commit_sha}")
        
        # Create timestamps
        now = datetime.utcnow()
        created_at = now.isoformat() + 'Z'
        
        # Set expiration (30 days from now)
        expires_at = int((now + timedelta(days=30)).timestamp())
        
        # Get videos from suggestions
        videos = suggestions.get('videos', [])
        
        print(f"[Service6] Storing {len(videos)} video suggestions")
        
        # Create session item matching your table schema
        session_item = {
            # Composite key (matches your table schema)
            'project_name': project_name,  # Partition key
            'session_id': session_id,      # Sort key
            
            # Also store as 'id' for backward compatibility
            'id': session_id,
            'owner': owner,
            'github_url': github_url,
            'commit_sha': commit_sha,
            
            # Session status
            'status': 'ready',  # User can now start uploading videos
            
            # AI-generated suggestions (store as-is from Service 5)
            'suggestions': videos,
            'overall_flow': suggestions.get('overall_flow', ''),
            'total_estimated_duration': suggestions.get('total_estimated_duration', ''),
            'project_specific_tips': suggestions.get('project_specific_tips', []),
            
            # Video upload tracking (initially empty)
            'uploaded_videos': {},
            
            # Project metadata
            'project_metadata': project_metadata,
            
            # Full data for reference (optional but useful)
            'github_data': github_data,
            'project_analysis': project_analysis,
            
            # Timestamps
            'created_at': created_at,
            'updated_at': created_at,
            'expires_at': expires_at
        }
        
        # Store in DynamoDB
        print(f"[Service6] Writing to DynamoDB table: {SESSIONS_TABLE_NAME}")
        table = dynamodb.Table(SESSIONS_TABLE_NAME)
        
        response = table.put_item(Item=session_item)
        
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        print(f"[Service6] ✅ Session stored successfully (HTTP {status_code})")
        
        return {
            'statusCode': 200,
            'body': {
                'session_id': session_id,
                'project_name': project_name,
                'owner': owner,
                'status': 'stored',
                'table': SESSIONS_TABLE_NAME,
                'created_at': created_at,
                'suggestions_count': len(videos)
            }
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        print(f"[Service6] ❌ DynamoDB ClientError ({error_code}): {error_msg}")
        
        # Common DynamoDB errors
        if error_code == 'ResourceNotFoundException':
            print(f"[Service6] Table '{SESSIONS_TABLE_NAME}' does not exist!")
        elif error_code == 'ValidationException':
            print(f"[Service6] Invalid data format for DynamoDB")
        elif error_code == 'ProvisionedThroughputExceededException':
            print(f"[Service6] DynamoDB throughput exceeded")
        
        # Re-raise so CloudWatch captures it
        raise
        
    except ValueError as e:
        print(f"[Service6] ❌ Validation Error: {str(e)}")
        raise
        
    except Exception as e:
        print(f"[Service6] ❌ Unexpected Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise