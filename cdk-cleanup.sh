#!/bin/bash

# Focused CDK Stack Cleanup Script
# This script specifically targets the AiDemoBuilderStack and related CDK resources

set -e

echo "========================================"
echo "CDK Stack Cleanup Script"
echo "========================================"
echo ""

# Get the current region
REGION=$(aws configure get region)
if [ -z "$REGION" ]; then
    echo "No default region set. Please enter your AWS region (e.g., us-west-2):"
    read REGION
fi

echo "Using region: $REGION"
STACK_NAME="AiDemoBuilderStack"

echo ""
echo "This script will:"
echo "  1. Delete the $STACK_NAME CloudFormation stack"
echo "  2. Clean up any orphaned resources"
echo "  3. Allow you to redeploy cleanly"
echo ""
echo "Press Ctrl+C to cancel, or press Enter to continue..."
read

echo ""
echo "Step 1: Checking CloudFormation Stack Status..."
echo "------------------------------------------------"
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &>/dev/null; then
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].StackStatus' --output text)
    echo "Stack found with status: $STACK_STATUS"
    
    case $STACK_STATUS in
        *ROLLBACK_COMPLETE|*ROLLBACK_FAILED|*DELETE_FAILED)
            echo ""
            echo "Stack is in a failed state. Attempting to delete..."
            aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION
            echo "Waiting for deletion..."
            aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $REGION 2>/dev/null || echo "Deletion in progress or completed"
            ;;
        *IN_PROGRESS)
            echo "Stack operation in progress. Waiting for it to complete..."
            sleep 30
            ;;
        *)
            echo "Deleting stack..."
            aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION
            echo "Waiting for deletion to complete..."
            aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $REGION 2>/dev/null || echo "Deletion completed"
            ;;
    esac
    echo "✓ Stack deletion completed"
else
    echo "Stack $STACK_NAME not found. Checking for failed change sets..."
    
    # Try to delete any failed change sets
    CHANGE_SETS=$(aws cloudformation list-change-sets --stack-name $STACK_NAME --region $REGION --query 'Summaries[].ChangeSetName' --output text 2>/dev/null)
    if [ ! -z "$CHANGE_SETS" ]; then
        for cs in $CHANGE_SETS; do
            echo "Deleting change set: $cs"
            aws cloudformation delete-change-set --stack-name $STACK_NAME --change-set-name $cs --region $REGION 2>/dev/null || true
        done
    fi
fi

echo ""
echo "Step 2: Getting CloudFormation Events..."
echo "------------------------------------------------"
echo "Last 10 events for debugging:"
aws cloudformation describe-stack-events --stack-name $STACK_NAME --region $REGION --max-items 10 2>/dev/null || echo "No events found (stack may be deleted)"

echo ""
echo "Step 3: Checking for orphaned CDK resources..."
echo "------------------------------------------------"

# Check for CDK-created S3 buckets
echo "Checking S3 buckets..."
CDK_BUCKETS=$(aws s3api list-buckets --query "Buckets[?starts_with(Name, 'aidemobuilderstac') || starts_with(Name, 'cdk-')].Name" --output text 2>/dev/null)
if [ ! -z "$CDK_BUCKETS" ]; then
    echo "Found CDK-related buckets:"
    for bucket in $CDK_BUCKETS; do
        echo "  - $bucket"
        echo "    Emptying bucket..."
        aws s3 rm s3://$bucket --recursive --region $REGION 2>/dev/null || true
        echo "    Deleting bucket..."
        aws s3api delete-bucket --bucket $bucket --region $REGION 2>/dev/null || echo "    Could not delete (may need manual cleanup)"
    done
else
    echo "No CDK-related S3 buckets found"
fi

# Check for CDK-created IAM roles
echo ""
echo "Checking IAM roles..."
CDK_ROLES=$(aws iam list-roles --query "Roles[?starts_with(RoleName, 'AiDemoBuilderStack')].RoleName" --output text 2>/dev/null)
if [ ! -z "$CDK_ROLES" ]; then
    echo "Found CDK-related roles:"
    for role in $CDK_ROLES; do
        echo "  - $role"
        
        # Detach policies
        POLICIES=$(aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null)
        for policy in $POLICIES; do
            aws iam detach-role-policy --role-name $role --policy-arn $policy 2>/dev/null || true
        done
        
        # Delete inline policies
        INLINE=$(aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null)
        for policy in $INLINE; do
            aws iam delete-role-policy --role-name $role --policy-name $policy 2>/dev/null || true
        done
        
        # Delete role
        aws iam delete-role --role-name $role 2>/dev/null || echo "    Could not delete role"
    done
else
    echo "No CDK-related IAM roles found"
fi

echo ""
echo "Step 4: Verifying cleanup..."
echo "------------------------------------------------"
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &>/dev/null; then
    echo "⚠ Stack still exists. May need additional time or manual intervention."
else
    echo "✓ Stack successfully deleted"
fi

echo ""
echo "========================================"
echo "Cleanup Complete!"
echo "========================================"
echo ""
echo "You can now try deploying again with:"
echo "  cdk deploy"
echo ""
echo "If you still encounter errors, run:"
echo "  aws cloudformation describe-stack-events --stack-name $STACK_NAME --max-items 20"
echo ""
echo "Or use the comprehensive cleanup script: bash aws-cleanup.sh"
echo ""