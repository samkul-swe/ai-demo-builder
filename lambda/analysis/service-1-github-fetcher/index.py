"""
Service 1: GitHub Repository Fetcher
WITH COMMIT SHA CACHE INVALIDATION

This version includes the latest commit SHA in the cache key,
ensuring cache is automatically invalidated when repo changes.
"""

import json
import os
import re
import requests
from typing import Dict, Any, Optional

# SSL certificate setup
try:
    import certifi
    cert_path = certifi.where()
    if os.path.exists(cert_path):
        os.environ['REQUESTS_CA_BUNDLE'] = cert_path
        os.environ['SSL_CERT_FILE'] = cert_path
except (ImportError, Exception):
    pass

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


def extract_owner_repo(github_url: str) -> Optional[Dict[str, str]]:
    """Extract owner and repo name from GitHub URL"""
    patterns = [
        r'github\.com/([^/]+)/([^/?#]+)',
        r'github\.com/([^/]+)/([^/?#]+)\.git',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, github_url)
        if match:
            return {
                'owner': match.group(1),
                'repo': match.group(2).replace('.git', '')
            }
    
    return None


def get_latest_commit_sha(owner: str, repo: str, token: str = None) -> str:
    """
    Fetch the latest commit SHA from GitHub
    This is used to create cache keys that automatically invalidate on code changes
    
    Args:
        owner: Repository owner
        repo: Repository name
        token: GitHub token (optional)
        
    Returns:
        Short commit SHA (7 chars) or 'unknown' if fetch fails
    """
    try:
        github_api = os.environ.get('GITHUB_API', 'https://api.github.com')
        url = f"{github_api}/repos/{owner}/{repo}/commits"
        
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'github-fetcher-service'
        }
        
        if token:
            headers['Authorization'] = f'token {token}'
        
        verify_ssl = True
        try:
            import certifi
            verify_ssl = certifi.where()
        except ImportError:
            pass
        
        # Fetch only the latest commit
        response = requests.get(
            url, 
            headers=headers, 
            params={'per_page': 1, 'page': 1},
            verify=verify_ssl,
            timeout=10
        )
        
        if response.status_code == 200:
            commits = response.json()
            if commits and len(commits) > 0:
                full_sha = commits[0]['sha']
                short_sha = full_sha[:7]  # Use short SHA (7 chars like git)
                print(f"[Service1] Latest commit SHA: {short_sha}")
                return short_sha
        
        print(f"[Service1] ⚠️  Could not fetch commit SHA (status: {response.status_code})")
        return 'unknown'
        
    except Exception as e:
        print(f"[Service1] ⚠️  Error fetching commit SHA: {str(e)}")
        return 'unknown'


def fetch_repository_info(owner: str, repo: str, token: str = None) -> Dict[str, Any]:
    """Fetch repository information from GitHub API"""
    github_api = os.environ.get('GITHUB_API', 'https://api.github.com')
    url = f"{github_api}/repos/{owner}/{repo}"
    
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'github-fetcher-service'
    }
    
    if token:
        headers['Authorization'] = f'token {token}'
    
    print(f"[Service1] Fetching repository info: {owner}/{repo}")
    
    verify_ssl = True
    try:
        import certifi
        verify_ssl = certifi.where()
    except ImportError:
        pass
    
    response = requests.get(url, headers=headers, verify=verify_ssl, timeout=30)
    
    if response.status_code == 404:
        raise Exception("Repository not found")
    elif response.status_code == 403:
        raise Exception("Rate limit exceeded or access forbidden")
    elif response.status_code == 401:
        raise Exception("Invalid or missing GitHub token")
    elif response.status_code != 200:
        raise Exception(f"GitHub API error: {response.status_code}")
    
    return response.json()


def fetch_readme(owner: str, repo: str, token: str = None) -> str:
    """Fetch README content from GitHub repository"""
    github_api = os.environ.get('GITHUB_API', 'https://api.github.com')
    url = f"{github_api}/repos/{owner}/{repo}/readme"
    
    headers = {
        'Accept': 'application/vnd.github.v3.raw',
        'User-Agent': 'github-fetcher-service'
    }
    
    if token:
        headers['Authorization'] = f'token {token}'
    
    print(f"[Service1] Fetching README: {owner}/{repo}")
    
    verify_ssl = True
    try:
        import certifi
        verify_ssl = certifi.where()
    except ImportError:
        pass
    
    response = requests.get(url, headers=headers, verify=verify_ssl, timeout=30)
    
    if response.status_code == 404:
        print(f"[Service1] README not found for {owner}/{repo}")
        return ""
    elif response.status_code != 200:
        print(f"[Service1] Warning: Could not fetch README ({response.status_code})")
        return ""
    
    return response.text


def invoke_lambda_service(function_name: str, payload: Dict[str, Any], region: str = 'us-east-1') -> Dict[str, Any]:
    """Invoke another Lambda function"""
    if boto3 is None:
        raise ImportError("boto3 is required for Lambda-to-Lambda invocation")
    
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        print(f"[Service1] Invoking {function_name}...")
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if isinstance(result, dict) and 'statusCode' in result:
            status_code = result.get('statusCode', 500)
            
            if status_code != 200:
                body = result.get('body', {})
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        pass
                
                error_msg = body.get('error', 'Unknown error') if isinstance(body, dict) else str(body)
                raise Exception(f"{function_name} returned error: {error_msg}")
            
            body = result.get('body', {})
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    pass
            
            print(f"[Service1] ✅ {function_name} invocation successful")
            return body
        
        print(f"[Service1] ✅ {function_name} invocation successful")
        return result
        
    except ClientError as e:
        raise Exception(f"Failed to invoke {function_name}: {str(e)}")


def call_service2_parse_readme(readme: str) -> Dict[str, Any]:
    """Call Service 2 to parse README content"""
    payload = {"readme": readme}
    return invoke_lambda_service('service-2-readme-parser', payload)


def call_service3_analyze_project(github_data: Dict[str, Any], parsed_readme: Dict[str, Any]) -> Dict[str, Any]:
    """Call Service 3 to analyze project"""
    github_data_for_service3 = {k: v for k, v in github_data.items() if k != 'readme'}
    
    payload = {
        "github_data": github_data_for_service3,
        "parsed_readme": parsed_readme
    }
    return invoke_lambda_service('service-3-project-analyzer', payload)


def call_service4_get_cache(key: str) -> Optional[Dict[str, Any]]:
    """Call Service 4 to get cached result"""
    try:
        payload = {
            "operation": "get",
            "key": key
        }
        result = invoke_lambda_service('service-4-cache-service', payload)
        
        if result.get('found'):
            print(f"[Service1] ✅ Cache hit for key: {key}")
            return result.get('value')
        else:
            print(f"[Service1] Cache miss for key: {key}")
            return None
    except Exception as e:
        print(f"[Service1] ⚠️  Cache get failed (non-critical): {str(e)}")
        return None


def call_service4_cache_result(key: str, value: Dict[str, Any], ttl: int = 3600) -> bool:
    """Call Service 4 to cache result"""
    try:
        payload = {
            "operation": "set",
            "key": key,
            "value": value,
            "ttl": ttl
        }
        invoke_lambda_service('service-4-cache-service', payload)
        print(f"[Service1] ✅ Cached result with key: {key}")
        return True
    except Exception as e:
        print(f"[Service1] ⚠️  Cache failed (non-critical): {str(e)}")
        return False


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function
    
    Standard Lambda entry point for Service 1: GitHub Fetcher
    Now includes commit SHA for smart cache invalidation
    """
    try:
        print(f"[Service1] Starting GitHub fetch service")
        
        # Extract github_url from event
        github_url = None
        if 'body' in event and isinstance(event.get('body'), str):
            try:
                body_data = json.loads(event['body'])
                github_url = body_data.get('github_url')
            except (json.JSONDecodeError, TypeError):
                github_url = None
        else:
            github_url = event.get('github_url')
        
        if not github_url:
            raise ValueError("Missing required field: github_url")
        
        # Extract owner/repo
        owner_repo = extract_owner_repo(github_url)
        if not owner_repo:
            raise ValueError(f"Invalid GitHub URL format: {github_url}")
        
        owner = owner_repo['owner']
        repo = owner_repo['repo']
        
        # Get GitHub token
        github_token = os.environ.get('GITHUB_TOKEN', '')
        
        # SMART CACHING: Get latest commit SHA
        # This ensures cache is invalidated when repo changes
        commit_sha = get_latest_commit_sha(owner, repo, github_token if github_token else None)
        
        # Cache key includes commit SHA - automatically invalidates on code changes!
        cache_key = f"github_{owner}_{repo}_{commit_sha}"
        print(f"[Service1] Cache key: {cache_key}")
        
        # Check cache
        cached_result = call_service4_get_cache(cache_key)
        
        if cached_result:
            # Cache hit - return immediately
            print(f"[Service1] ✅ Returning cached result (commit: {commit_sha})")
            is_api_gateway = 'requestContext' in event or ('body' in event and isinstance(event.get('body'), str))
            
            if is_api_gateway:
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    },
                    "body": json.dumps(cached_result)
                }
            else:
                return {
                    "statusCode": 200,
                    "body": cached_result
                }
        
        # Cache miss - fetch from GitHub
        print(f"[Service1] Cache miss - fetching from GitHub API")
        
        # Fetch repository info
        repo_info = fetch_repository_info(owner, repo, github_token if github_token else None)
        
        # Fetch README content
        readme_content = fetch_readme(owner, repo, github_token if github_token else None)
        
        github_data = {
            "projectName": repo_info.get('name', repo),
            "owner": repo_info.get('owner', {}).get('login', owner),
            "stars": repo_info.get('stargazers_count', 0),
            "language": repo_info.get('language', ''),
            "topics": repo_info.get('topics', []),
            "description": repo_info.get('description', ''),
            "readme": readme_content,
            "commit_sha": commit_sha  # Include in response for debugging
        }
        
        # Call Service 2 to parse README
        print(f"[Service1] Calling Service 2 to parse README...")
        try:
            parsed_readme = call_service2_parse_readme(github_data.get('readme', ''))
        except Exception as e:
            print(f"[Service1] ⚠️  Service 2 failed (non-critical): {str(e)}")
            parsed_readme = {"features": [], "sections": [], "error": str(e)}
        
        # Call Service 3 to analyze project
        print(f"[Service1] Calling Service 3 to analyze project...")
        try:
            project_analysis = call_service3_analyze_project(github_data, parsed_readme)
        except Exception as e:
            print(f"[Service1] ⚠️  Service 3 failed (non-critical): {str(e)}")
            project_analysis = {"projectType": "Unknown", "error": str(e)}
        
        # Combine results
        result = {
            "github_data": github_data,
            "parsed_readme": parsed_readme,
            "project_analysis": project_analysis
        }
        
        # Cache the result (with commit SHA in key)
        # Cache will auto-invalidate when repo gets new commits!
        call_service4_cache_result(cache_key, result, ttl=3600)
        
        # Return response
        is_api_gateway = 'requestContext' in event or ('body' in event and isinstance(event.get('body'), str))
        
        print(f"[Service1] ✅ Successfully processed {github_url} (commit: {commit_sha})")
        
        if is_api_gateway:
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(result)
            }
        else:
            return {
                "statusCode": 200,
                "body": result
            }
        
    except ValueError as e:
        print(f"[Service1] ❌ Validation Error: {str(e)}")
        error_response = {"error": str(e)}
        is_api_gateway = 'requestContext' in event or ('body' in event and isinstance(event.get('body'), str))
        
        if is_api_gateway:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(error_response)
            }
        else:
            return {
                "statusCode": 400,
                "body": error_response
            }
        
    except Exception as e:
        print(f"[Service1] ❌ Error: {str(e)}")
        error_message = str(e)
        
        if "Repository not found" in error_message:
            status_code = 404
        elif "Rate limit" in error_message or "forbidden" in error_message.lower():
            status_code = 403
        elif "Invalid" in error_message or "token" in error_message.lower():
            status_code = 401
        else:
            status_code = 500
        
        error_response = {"error": error_message}
        is_api_gateway = 'requestContext' in event or ('body' in event and isinstance(event.get('body'), str))
        
        if is_api_gateway:
            return {
                "statusCode": status_code,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(error_response)
            }
        else:
            return {
                "statusCode": status_code,
                "body": error_response
            }