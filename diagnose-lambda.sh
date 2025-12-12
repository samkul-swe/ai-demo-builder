#!/bin/bash

# Lambda Function Diagnostic Script

echo "========================================"
echo "Lambda Function Diagnostics"
echo "========================================"
echo ""

REGION="us-east-1"
FUNCTION_NAME="service-5-ai-suggestion"

echo "Checking Lambda function: $FUNCTION_NAME"
echo ""

# Step 1: Check if function exists
echo "Step 1: Verifying function exists..."
echo "===================================="
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION &>/dev/null; then
    echo "✓ Function exists"
    
    # Get function details
    echo ""
    echo "Function configuration:"
    aws lambda get-function-configuration --function-name $FUNCTION_NAME --region $REGION \
        --query '{Runtime:Runtime,Handler:Handler,Timeout:Timeout,Memory:MemorySize,Environment:Environment}' \
        --output json
else
    echo "✗ Function not found"
    echo ""
    echo "Available Lambda functions:"
    aws lambda list-functions --region $REGION --query 'Functions[].FunctionName' --output table
    exit 1
fi

# Step 2: Check recent invocations
echo ""
echo "Step 2: Checking recent invocations..."
echo "======================================="
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=$FUNCTION_NAME \
    --start-time $(date -u -d '10 minutes ago' --iso-8601=seconds) \
    --end-time $(date -u --iso-8601=seconds) \
    --period 300 \
    --statistics Sum \
    --region $REGION \
    --query 'Datapoints[0].Sum' \
    --output text

# Step 3: Get CloudWatch logs
echo ""
echo "Step 3: Recent CloudWatch Logs (last 10 minutes)..."
echo "===================================================="
LOG_GROUP="/aws/lambda/$FUNCTION_NAME"

if aws logs describe-log-groups --log-group-name-prefix $LOG_GROUP --region $REGION &>/dev/null; then
    echo "Getting latest logs..."
    echo ""
    
    # Get the most recent log stream
    LATEST_STREAM=$(aws logs describe-log-streams \
        --log-group-name $LOG_GROUP \
        --region $REGION \
        --order-by LastEventTime \
        --descending \
        --max-items 1 \
        --query 'logStreams[0].logStreamName' \
        --output text)
    
    if [ "$LATEST_STREAM" != "None" ] && [ ! -z "$LATEST_STREAM" ]; then
        echo "Latest log stream: $LATEST_STREAM"
        echo ""
        echo "Last 20 log entries:"
        echo "--------------------"
        aws logs get-log-events \
            --log-group-name $LOG_GROUP \
            --log-stream-name "$LATEST_STREAM" \
            --region $REGION \
            --limit 20 \
            --query 'events[].[timestamp,message]' \
            --output text | tail -20
    else
        echo "No log streams found yet. Function may not have been invoked."
    fi
else
    echo "✗ Log group not found. Function may not have been invoked yet."
fi

# Step 4: Check for errors
echo ""
echo "Step 4: Searching for errors in logs..."
echo "========================================"
aws logs filter-log-events \
    --log-group-name $LOG_GROUP \
    --region $REGION \
    --start-time $(date -u -d '30 minutes ago' +%s)000 \
    --filter-pattern "ERROR" \
    --query 'events[].message' \
    --output text 2>/dev/null | head -20

if [ $? -ne 0 ]; then
    echo "No errors found in logs (or logs not available yet)"
fi

# Step 5: Test Lambda function directly
echo ""
echo "Step 5: Testing Lambda function directly..."
echo "==========================================="
echo "Invoking function with test payload..."

TEST_PAYLOAD='{"repo_url": "https://github.com/example/repo"}'

INVOKE_RESULT=$(aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --region $REGION \
    --payload "$TEST_PAYLOAD" \
    --cli-binary-format raw-in-base64-out \
    /tmp/lambda-response.json 2>&1)

echo "$INVOKE_RESULT"

if [ -f /tmp/lambda-response.json ]; then
    echo ""
    echo "Lambda response:"
    cat /tmp/lambda-response.json | jq '.' 2>/dev/null || cat /tmp/lambda-response.json
    echo ""
fi

# Step 6: Check environment variables
echo ""
echo "Step 6: Checking environment variables..."
echo "=========================================="
aws lambda get-function-configuration \
    --function-name $FUNCTION_NAME \
    --region $REGION \
    --query 'Environment.Variables' \
    --output json

# Step 7: Check IAM permissions
echo ""
echo "Step 7: Checking IAM role..."
echo "============================"
ROLE_ARN=$(aws lambda get-function-configuration \
    --function-name $FUNCTION_NAME \
    --region $REGION \
    --query 'Role' \
    --output text)

echo "Role ARN: $ROLE_ARN"
echo ""
echo "Attached policies:"
ROLE_NAME=$(echo $ROLE_ARN | cut -d'/' -f2)
aws iam list-attached-role-policies --role-name $ROLE_NAME --output table 2>/dev/null

echo ""
echo "========================================"
echo "Common Issues & Solutions"
echo "========================================"
echo ""
echo "If you see 'Internal server error', common causes are:"
echo ""
echo "1. Missing dependencies in Lambda function"
echo "   → Check requirements.txt is included"
echo "   → Ensure all imports are available"
echo ""
echo "2. Environment variables not set correctly"
echo "   → Check BUCKET_NAME, SESSIONS_TABLE, etc. are set"
echo ""
echo "3. IAM permissions missing"
echo "   → Lambda needs permissions for S3, DynamoDB, etc."
echo ""
echo "4. Python syntax errors or runtime errors"
echo "   → Check CloudWatch logs above for stack traces"
echo ""
echo "5. Handler function not found"
echo "   → Ensure handler is 'index.lambda_handler' and file is index.py"
echo ""
echo "To view live logs as requests come in:"
echo "  aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"
echo ""
