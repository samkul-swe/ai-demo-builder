#!/bin/bash

# CDK Early Validation Error Diagnostic Script
# This script will help identify what's causing the ResourceExistenceCheck failure

set -e

echo "========================================"
echo "CDK Early Validation Diagnostic"
echo "========================================"
echo ""

REGION="us-west-2"
ACCOUNT_ID="288418345946"

echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""

echo "Step 1: Checking CloudFormation Events..."
echo "----------------------------------------"
echo "Checking for CDKToolkit stack events..."
aws cloudformation describe-stack-events \
    --stack-name CDKToolkit \
    --region $REGION \
    --max-items 20 \
    2>/dev/null || echo "No CDKToolkit stack events found"

echo ""
echo "Checking for AiDemoBuilderStack events..."
aws cloudformation describe-stack-events \
    --stack-name AiDemoBuilderStack \
    --region $REGION \
    --max-items 20 \
    2>/dev/null || echo "No AiDemoBuilderStack events found"

echo ""
echo "Step 2: Checking for CloudFormation Hooks..."
echo "----------------------------------------"
echo "Listing account-level hooks..."
aws cloudformation list-types \
    --type HOOK \
    --region $REGION \
    --filters TypeNamePrefix=AWS::EarlyValidation 2>/dev/null || echo "No hooks found or no permission to list"

echo ""
echo "Step 3: Checking Stack Sets..."
echo "----------------------------------------"
aws cloudformation list-stack-sets --region $REGION 2>/dev/null || echo "No stack sets or no permission"

echo ""
echo "Step 4: Checking for failed stacks..."
echo "----------------------------------------"
FAILED_STACKS=$(aws cloudformation list-stacks \
    --region $REGION \
    --stack-status-filter CREATE_FAILED ROLLBACK_FAILED DELETE_FAILED UPDATE_ROLLBACK_FAILED \
    --query 'StackSummaries[].[StackName,StackStatus]' \
    --output table 2>/dev/null)

if [ ! -z "$FAILED_STACKS" ]; then
    echo "Found failed stacks:"
    echo "$FAILED_STACKS"
else
    echo "No failed stacks found"
fi

echo ""
echo "Step 5: Checking your IAM permissions..."
echo "----------------------------------------"
echo "Current identity:"
aws sts get-caller-identity

echo ""
echo "Checking if you can describe VPCs (basic EC2 permission test)..."
aws ec2 describe-vpcs --region $REGION --max-results 5 2>/dev/null && echo "✓ EC2 read permissions OK" || echo "⚠ EC2 read permissions may be limited"

echo ""
echo "Checking if you can list S3 buckets..."
aws s3 ls 2>/dev/null && echo "✓ S3 read permissions OK" || echo "⚠ S3 read permissions may be limited"

echo ""
echo "Step 6: Checking for existing CDK resources that might conflict..."
echo "----------------------------------------"

echo "Checking for CDK staging buckets..."
aws s3api list-buckets --query "Buckets[?starts_with(Name, 'cdk-')].Name" --output table 2>/dev/null || echo "Cannot list buckets"

echo ""
echo "Checking for CDK IAM roles..."
aws iam list-roles --query "Roles[?starts_with(RoleName, 'cdk-')].RoleName" --output table 2>/dev/null || echo "Cannot list IAM roles"

echo ""
echo "Step 7: Testing basic CloudFormation capability..."
echo "----------------------------------------"
echo "Creating a minimal test stack to verify CloudFormation works..."

TEST_STACK_NAME="cdk-diagnostic-test-stack"
TEST_TEMPLATE='{
  "AWSTemplateFormatVersion": "2010-09-09",
  "Description": "Minimal test stack",
  "Resources": {
    "DummyWaitHandle": {
      "Type": "AWS::CloudFormation::WaitConditionHandle"
    }
  }
}'

echo "$TEST_TEMPLATE" > /tmp/test-template.json

echo "Attempting to create test stack..."
aws cloudformation create-stack \
    --stack-name $TEST_STACK_NAME \
    --template-body file:///tmp/test-template.json \
    --region $REGION 2>&1 | head -20

sleep 5

echo ""
echo "Checking test stack status..."
TEST_STATUS=$(aws cloudformation describe-stacks --stack-name $TEST_STACK_NAME --region $REGION --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")
echo "Test stack status: $TEST_STATUS"

if [ "$TEST_STATUS" != "NOT_FOUND" ]; then
    echo "Cleaning up test stack..."
    aws cloudformation delete-stack --stack-name $TEST_STACK_NAME --region $REGION 2>/dev/null || true
fi

echo ""
echo "========================================"
echo "Diagnostic Complete"
echo "========================================"
echo ""
echo "ANALYSIS:"
echo "---------"
echo ""
echo "The AWS::EarlyValidation::ResourceExistenceCheck error typically means:"
echo ""
echo "1. CloudFormation Hook Enabled (Most Likely)"
echo "   - Your AWS account has a CloudFormation hook that validates resources"
echo "   - The hook is rejecting the deployment because it references non-existent resources"
echo "   - Solution: Either disable the hook or fix the resource references"
echo ""
echo "2. Missing VPC or Subnets"
echo "   - Your CDK code references VPCs, subnets, or security groups that don't exist"
echo "   - Solution: Check your CDK code for .fromLookup() calls"
echo ""
echo "3. Account-Level Restrictions"
echo "   - Your AWS Organization may have Service Control Policies (SCPs)"
echo "   - Solution: Contact your AWS administrator"
echo ""
echo "RECOMMENDED NEXT STEPS:"
echo "----------------------"
echo ""
echo "1. Check if you're using VPC lookup in your CDK code:"
echo "   grep -r 'fromLookup\\|fromVpcId\\|fromSubnetId' ."
echo ""
echo "2. Try deploying to a different region to see if it's region-specific:"
echo "   cdk bootstrap aws://$ACCOUNT_ID/us-west-2"
echo ""
echo "3. Check with your AWS administrator about CloudFormation hooks"
echo ""
echo "4. Review your CDK code for any references to existing resources"
echo ""