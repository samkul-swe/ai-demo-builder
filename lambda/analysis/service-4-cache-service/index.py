"""
Service 4: Cache Service
Manages DynamoDB cache for storing and retrieving cached data
"""

import json
import os
from typing import Dict, Any, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    # For local testing without boto3
    boto3 = None
    ClientError = Exception


def get_dynamodb_table():
    """
    Get DynamoDB table instance
    
    Returns:
        DynamoDB Table resource
    """
    if boto3 is None:
        raise ImportError("boto3 is required for DynamoDB operations")
    
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get('CACHE_TABLE')
    
    print(f"[Service4] Connecting to DynamoDB table: {table_name}")
    return dynamodb.Table(table_name)


def get_cache_item(key: str) -> Optional[Dict[str, Any]]:
    """
    Get item from cache
    
    Args:
        key: Cache key
        
    Returns:
        Cached value if found, None otherwise
    """
    try:
        table = get_dynamodb_table()
        response = table.get_item(
            Key={
                'cacheKey': key  # Matches your schema
            }
        )
        
        if 'Item' in response:
            item = response['Item']
            
            # Check if TTL has expired (DynamoDB doesn't auto-delete immediately)
            if 'ttl' in item:
                import time
                current_time = int(time.time())
                if current_time > item['ttl']:
                    print(f"[Service4] Cache expired for key: {key}")
                    # Delete expired item
                    table.delete_item(Key={'cacheKey': key})
                    return None
            
            # Extract the value
            cached_value = item.get('value')
            print(f"[Service4] ✅ Cache hit for key: {key}")
            return cached_value
        else:
            print(f"[Service4] Cache miss for key: {key}")
            return None
            
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ResourceNotFoundException':
            raise Exception(f"DynamoDB table not found: {os.environ.get('CACHE_TABLE')}")
        print(f"[Service4] ⚠️  DynamoDB error (non-critical): {str(e)}")
        return None  # Return None on error so Service 1 can continue


def set_cache_item(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """
    Store item in cache
    
    Args:
        key: Cache key
        value: Value to cache
        ttl: Optional TTL in seconds (default: 3600 = 1 hour)
        
    Returns:
        True if successful
    """
    try:
        table = get_dynamodb_table()
        
        # Default TTL: 1 hour
        if ttl is None:
            ttl = 3600
        
        import time
        expiration_timestamp = int(time.time()) + ttl
        
        item = {
            'cacheKey': key,      # Matches your schema
            'value': value,       # Matches your schema
            'ttl': expiration_timestamp  # Matches your schema
        }
        
        table.put_item(Item=item)
        print(f"[Service4] ✅ Cached item for key: {key} (expires in {ttl}s)")
        return True
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ResourceNotFoundException':
            raise Exception(f"DynamoDB table not found: {os.environ.get('CACHE_TABLE')}")
        print(f"[Service4] ⚠️  Failed to cache (non-critical): {str(e)}")
        return False  # Don't fail Service 1 if cache write fails


def delete_cache_item(key: str) -> bool:
    """
    Delete item from cache
    
    Args:
        key: Cache key to delete
        
    Returns:
        True if successful
    """
    try:
        table = get_dynamodb_table()
        table.delete_item(
            Key={
                'cacheKey': key  # Matches your schema
            }
        )
        print(f"[Service4] ✅ Deleted cache item: {key}")
        return True
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ResourceNotFoundException':
            raise Exception(f"DynamoDB table not found: {os.environ.get('CACHE_TABLE')}")
        print(f"[Service4] ⚠️  Failed to delete (non-critical): {str(e)}")
        return False


def process_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the Lambda event and perform cache operation
    
    Args:
        event: Lambda event containing operation, key, and optionally value
        
    Returns:
        Cache operation result
    """
    operation = event.get('operation', '').lower()
    key = event.get('key')
    
    if not operation:
        raise ValueError("Missing required field: operation")
    
    if not key:
        raise ValueError("Missing required field: key")
    
    # Handle different operations
    if operation == 'get':
        cached_value = get_cache_item(key)
        return {
            "found": cached_value is not None,
            "value": cached_value
        }
    
    elif operation == 'set':
        value = event.get('value')
        if value is None:
            raise ValueError("Missing required field: value for set operation")
        
        # Optional TTL (in seconds, defaults to 3600)
        ttl = event.get('ttl', 3600)
        success = set_cache_item(key, value, ttl)
        return {
            "success": success,
            "key": key
        }
    
    elif operation == 'delete':
        success = delete_cache_item(key)
        return {
            "success": success,
            "key": key
        }
    
    else:
        raise ValueError(f"Unsupported operation: {operation}. Supported operations: get, set, delete")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function
    
    Standard Lambda entry point for Service 4: Cache Service
    
    Args:
        event: Input data containing operation, key, and optionally value
        context: Lambda runtime context
        
    Returns:
        Standard Lambda response with statusCode and body
    """
    try:
        print(f"[Service4] Starting cache service")
        print(f"[Service4] Operation: {event.get('operation', 'N/A')}, Key: {event.get('key', 'N/A')[:50]}...")
        
        result = process_request(event)
        
        return {
            "statusCode": 200,
            "body": result
        }
        
    except ValueError as e:
        print(f"[Service4] ❌ Validation Error: {str(e)}")
        return {
            "statusCode": 400,
            "body": {"error": str(e)}
        }
        
    except ImportError as e:
        print(f"[Service4] ❌ Import Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": {"error": "boto3 library not available. This service requires boto3 for AWS Lambda."}
        }
        
    except Exception as e:
        print(f"[Service4] ❌ Error: {str(e)}")
        error_message = str(e)
        
        # Check for DynamoDB table not found
        if "table not found" in error_message.lower():
            status_code = 503  # Service unavailable
        else:
            status_code = 500
        
        return {
            "statusCode": status_code,
            "body": {"error": error_message}
        }