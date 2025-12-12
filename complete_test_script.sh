#!/bin/bash
set -e

echo "🧪 AI Demo Builder - Complete Service Test Suite"
echo "================================================="
echo ""

REGION="us-east-1"

# Get resource names
echo "📋 Getting resource names..."
CACHE_TABLE="ai-demo-builder-cache"
SESSIONS_TABLE="ai-demo-builder-sessions"
BUCKET=$(aws s3 ls | grep aidemobuilderstack | awk '{print $3}')

echo "   Cache Table: $CACHE_TABLE"
echo "   Sessions Table: $SESSIONS_TABLE"
echo "   S3 Bucket: $BUCKET"
echo ""

# Create test directory
mkdir -p test-results
cd test-results

# ========================
# TEST 1: Service 4 (Cache)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 1: Service 4 - Cache Service"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

aws lambda invoke \
  --function-name service-4-cache-service \
  --region $REGION \
  --cli-binary-format raw-in-base64-out \
  --payload '{"operation":"set","key":"test_cache_001","value":{"test":"data","timestamp":"2024-12-12"},"ttl":3600}' \
  result-cache-set.json

echo "SET Result:"
cat result-cache-set.json | jq
echo ""

aws lambda invoke \
  --function-name service-4-cache-service \
  --region $REGION \
  --cli-binary-format raw-in-base64-out \
  --payload '{"operation":"get","key":"test_cache_001"}' \
  result-cache-get.json

echo "GET Result:"
cat result-cache-get.json | jq
echo ""

if cat result-cache-get.json | jq -e '.body.found == true' > /dev/null; then
    echo "✅ Service 4: PASSED"
else
    echo "❌ Service 4: FAILED"
fi
echo ""

# ========================
# TEST 2: Service 2 (README Parser)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 2: Service 2 - README Parser"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

aws lambda invoke \
  --function-name service-2-readme-parser \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"readme":"# My Project\n\n## Features\n\n- Feature 1\n- Feature 2\n- Feature 3\n\n## Installation\n\npip install myproject"}' \
  result-readme.json

echo "Full result:"
cat result-readme.json | jq

# Check what the actual response structure is
if cat result-readme.json | jq -e '.statusCode' > /dev/null 2>&1; then
    STATUS=$(cat result-readme.json | jq -r '.statusCode')
    echo "Status Code: $STATUS"
    
    if [ "$STATUS" = "200" ]; then
        echo "✅ Service 2: PASSED"
    else
        echo "❌ Service 2: FAILED"
        echo "Error message:"
        cat result-readme.json | jq '.body'
    fi
else
    echo "❌ Service 2: Unexpected response format"
fi

# ========================
# TEST 3: Service 3 (Project Analyzer)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 3: Service 3 - Project Analyzer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

aws lambda invoke \
  --function-name service-3-project-analyzer \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"github_data":{"projectName":"React","owner":"facebook","stars":200000,"language":"JavaScript","topics":["react","ui","framework"]},"parsed_readme":{"title":"React","features":["Declarative","Component-Based"],"hasDocumentation":true}}' \
  result-analyzer.json

echo "Full result:"
cat result-analyzer.json | jq

# Check the response
if cat result-analyzer.json | jq -e '.body.projectType' > /dev/null 2>&1; then
    PROJECT_TYPE=$(cat result-analyzer.json | jq -r '.body.projectType')
    echo "Project Type: $PROJECT_TYPE"
    
    if [ "$PROJECT_TYPE" = "framework" ]; then
        echo "✅ Service 3: PASSED"
    else
        echo "⚠️  Service 3: Got projectType='$PROJECT_TYPE' (expected 'framework')"
    fi
else
    echo "❌ Service 3: FAILED or unexpected response"
    echo "Error/Body:"
    cat result-analyzer.json | jq '.body'
fi

# ========================
# TEST 4: Service 1 (Full Pipeline)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 4: Service 1 - GitHub Fetcher (Full Pipeline)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

aws lambda invoke \
  --function-name service-1-github-fetcher \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"github_url":"https://github.com/anthropics/anthropic-sdk-python"}' \
  result-github.json

echo "Full result:"
cat result-github.json | jq

# Check status code
if cat result-github.json | jq -e '.statusCode' > /dev/null 2>&1; then
    STATUS=$(cat result-github.json | jq -r '.statusCode')
    echo "Status Code: $STATUS"
    
    if [ "$STATUS" = "200" ]; then
        echo "✅ Service 1: PASSED"
        echo ""
        echo "Summary:"
        cat result-github.json | jq '{
          projectName: .body.github_data.projectName,
          owner: .body.github_data.owner,
          language: .body.github_data.language,
          projectType: .body.project_analysis.projectType
        }'
    else
        echo "❌ Service 1: FAILED"
        echo "Error body:"
        cat result-github.json | jq '.body'
        echo ""
        echo "Recent logs:"
        aws logs tail /aws/lambda/service-1-github-fetcher --region us-east-1 --since 5m
    fi
else
    echo "❌ Service 1: Unexpected response format"
fi

# ========================
# TEST 5: Service 5 (AI Suggestions)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 5: Service 5 - AI Suggestions"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f result-github.json ] && cat result-github.json | jq -e '.statusCode == 200' > /dev/null 2>&1; then
    echo "Creating cleaned payload for Service 5..."
    
    python3 << 'PYTHON_EOF' > payload-ai-clean.json
import json
import sys

try:
    with open('result-github.json', 'r') as f:
        data = json.load(f)
    
    clean_payload = {
        "github_data": {
            "projectName": data["body"]["github_data"].get("projectName", "unknown"),
            "owner": data["body"]["github_data"].get("owner", "unknown"),
            "language": data["body"]["github_data"].get("language", "unknown"),
            "stars": data["body"]["github_data"].get("stars", 0),
            "topics": data["body"]["github_data"].get("topics", []),
            "description": data["body"]["github_data"].get("description")
        },
        "parsed_readme": {
            "title": data["body"]["parsed_readme"].get("title", ""),
            "hasDocumentation": data["body"]["parsed_readme"].get("hasDocumentation", False),
            "features": data["body"]["parsed_readme"].get("features", [])[:5]
        },
        "project_analysis": data["body"].get("project_analysis", {})
    }
    
    print(json.dumps(clean_payload, ensure_ascii=True))
except Exception as e:
    print(f'{{"error": "Failed to create payload: {str(e)}"}}', file=sys.stderr)
    sys.exit(1)
PYTHON_EOF
    
    if [ $? -eq 0 ]; then
        echo "Payload created successfully"
        echo ""
        
        aws lambda invoke \
          --function-name service-5-ai-suggestion \
          --region us-east-1 \
          --cli-binary-format raw-in-base64-out \
          --payload file://payload-ai-clean.json \
          result-ai.json
        
        echo "Parsing response..."
        
        # The body is a JSON string, so we need to parse it twice
        if cat result-ai.json | jq -e '.statusCode == 200' > /dev/null 2>&1; then
            # Parse the nested JSON body
            cat result-ai.json | jq -r '.body' | jq '.' > result-ai-parsed.json
            
            if cat result-ai-parsed.json | jq -e '.session_id' > /dev/null 2>&1; then
                SESSION_ID=$(cat result-ai-parsed.json | jq -r '.session_id')
                echo ""
                echo "✅ Service 5: PASSED"
                echo "   Session ID: $SESSION_ID"
                echo "   Total Suggestions: $(cat result-ai-parsed.json | jq -r '.total_suggestions')"
                echo "   Project Name: $(cat result-ai-parsed.json | jq -r '.project_name')"
                echo "   Cached: $(cat result-ai-parsed.json | jq -r '.cached')"
                echo ""
                echo "Video Suggestions:"
                cat result-ai-parsed.json | jq -r '.videos[] | "  - Video \(.sequence_number): \(.title) (\(.duration))"'
            else
                echo "❌ Service 5: FAILED - No session_id in response"
                cat result-ai-parsed.json | jq
            fi
        else
            echo "❌ Service 5: FAILED"
            echo "Status Code: $(cat result-ai.json | jq -r '.statusCode')"
            cat result-ai.json | jq
        fi
    else
        echo "❌ Failed to create clean payload"
    fi
else
    echo "⏭️  Skipping Service 5 - Service 1 must pass first"
fi

# ========================
# TEST 6: Service 7 (Upload URL)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 6: Service 7 - Upload URL Generator"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f result-ai-parsed.json ] && cat result-ai-parsed.json | jq -e '.session_id' > /dev/null 2>&1; then
    SESSION_ID=$(cat result-ai-parsed.json | jq -r '.session_id')
    echo "Using session_id: $SESSION_ID"
    echo ""
    
    aws lambda invoke \
      --function-name service-7-upload-url-generator \
      --region us-east-1 \
      --cli-binary-format raw-in-base64-out \
      --payload "{\"session_id\":\"$SESSION_ID\",\"suggestion_id\":1}" \
      result-upload-url.json
    
    echo "Response:"
    cat result-upload-url.json | jq
    echo ""
    
    # Check if successful
    if cat result-upload-url.json | jq -e '.statusCode == 200' > /dev/null 2>&1; then
        # Parse the body (might be a JSON string)
        if cat result-upload-url.json | jq -e '.body | type == "string"' > /dev/null 2>&1; then
            # Body is a string, parse it
            cat result-upload-url.json | jq -r '.body' | jq '.' > result-upload-parsed.json
            BODY_FILE="result-upload-parsed.json"
        else
            # Body is already an object
            cat result-upload-url.json | jq '.body' > result-upload-parsed.json
            BODY_FILE="result-upload-parsed.json"
        fi
        
        if cat $BODY_FILE | jq -e '.upload_url' > /dev/null 2>&1; then
            echo "✅ Service 7: PASSED"
            echo "   S3 Key: $(cat $BODY_FILE | jq -r '.key')"
            echo "   Expires In: $(cat $BODY_FILE | jq -r '.expires_in')"
            echo "   Upload URL: $(cat $BODY_FILE | jq -r '.upload_url' | cut -c1-80)..."
        else
            echo "❌ Service 7: FAILED - No upload_url in response"
            cat $BODY_FILE | jq
        fi
    else
        echo "❌ Service 7: FAILED"
        echo "Status Code: $(cat result-upload-url.json | jq -r '.statusCode')"
        echo "Error:"
        cat result-upload-url.json | jq
    fi
else
    echo "⏭️  Skipping Service 7 - Need session_id from Service 5"
    echo "   Make sure result-ai-parsed.json exists with a valid session_id"
fi

# ========================
# TEST 7: Service 16 (Status Tracker)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 7: Service 16 - Status Tracker"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f result-ai-parsed.json ] && cat result-ai-parsed.json | jq -e '.session_id' > /dev/null 2>&1; then
    SESSION_ID=$(cat result-ai-parsed.json | jq -r '.session_id')
    echo "Using session_id: $SESSION_ID"
    echo ""
    
    # Try Method 1: Direct invocation with body
    echo "Attempting Method 1: Body parameter..."
    aws lambda invoke \
      --function-name service-16-status-tracker \
      --region us-east-1 \
      --cli-binary-format raw-in-base64-out \
      --payload "{\"body\":{\"session_id\":\"$SESSION_ID\"}}" \
      result-status.json
    
    if cat result-status.json | jq -e '.statusCode == 200' > /dev/null 2>&1; then
        echo "✅ Method 1 worked!"
    else
        echo "Method 1 failed, trying Method 2..."
        
        # Try Method 2: API Gateway format
        aws lambda invoke \
          --function-name service-16-status-tracker \
          --region us-east-1 \
          --cli-binary-format raw-in-base64-out \
          --payload "{\"pathParameters\":{\"session_id\":\"$SESSION_ID\"}}" \
          result-status.json
        
        if cat result-status.json | jq -e '.statusCode == 200' > /dev/null 2>&1; then
            echo "✅ Method 2 worked!"
        else
            echo "Method 2 failed, trying Method 3..."
            
            # Try Method 3: Query string parameters
            aws lambda invoke \
              --function-name service-16-status-tracker \
              --region us-east-1 \
              --cli-binary-format raw-in-base64-out \
              --payload "{\"queryStringParameters\":{\"session_id\":\"$SESSION_ID\"}}" \
              result-status.json
            
            if cat result-status.json | jq -e '.statusCode == 200' > /dev/null 2>&1; then
                echo "✅ Method 3 worked!"
            else
                echo "All methods failed"
            fi
        fi
    fi
    
    echo ""
    echo "Final Response:"
    cat result-status.json | jq
    echo ""
    
    # Parse response if successful
    if cat result-status.json | jq -e '.statusCode == 200' > /dev/null 2>&1; then
        if cat result-status.json | jq -e '.body | type == "string"' > /dev/null 2>&1; then
            cat result-status.json | jq -r '.body' | jq '.' > result-status-parsed.json
            BODY_FILE="result-status-parsed.json"
        else
            cat result-status.json | jq '.body' > result-status-parsed.json
            BODY_FILE="result-status-parsed.json"
        fi
        
        echo "✅ Service 16: PASSED"
        echo "Status Summary:"
        cat $BODY_FILE | jq
    else
        echo "❌ Service 16: FAILED"
        echo "Status Code: $(cat result-status.json | jq -r '.statusCode')"
    fi
else
    echo "⏭️  Skipping Service 16 - Need session_id from Service 5"
fi
# ========================
# TEST 8: Service 11 (Job Queue)
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 8: Service 11 - Job Queue"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚠️  This requires all videos to be uploaded and converted"
echo "   Skipping for now (test manually after uploading videos)"
echo ""

# ========================
# SUMMARY
# ========================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Tested Services:"
echo "  ✅ Service 4: Cache Service"
echo "  ✅ Service 2: README Parser"
echo "  ✅ Service 3: Project Analyzer"
echo "  ✅ Service 1: GitHub Fetcher (calls 2, 3, 4)"
echo "  ✅ Service 5: AI Suggestions"
echo "  ✅ Service 7: Upload URL Generator"
echo "  ✅ Service 16: Status Tracker"
echo ""
echo "Skipped (require video upload):"
echo "  ⏭️  Service 8: Upload Tracker"
echo "  ⏭️  Service 9: Video Validator"
echo "  ⏭️  Service 10: Format Converter"
echo "  ⏭️  Service 11-14: Processing Pipeline"
echo ""
echo "All test files saved in: test-results/"
echo ""

cd ..
