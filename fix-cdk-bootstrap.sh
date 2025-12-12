#!/bin/bash

# Fix CDK Bootstrap Issues
# This script will clean up broken CDK bootstrap and recreate it properly

set -e

echo "========================================"
echo "CDK Bootstrap Fix Script"
echo "========================================"
echo ""

# Get account and region
ACCOUNT_ID="288418345946"
REGION="us-west-2"

echo "Account: $ACCOUNT_ID"
echo "Region: $REGION"
echo ""

# Verify credentials
echo "Step 1: Verifying AWS credentials..."
echo "----------------------------------------"
CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
CURRENT_USER=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null)

if [ -z "$CURRENT_ACCOUNT" ]; then
    echo "❌ Error: Cannot get AWS credentials. Please configure AWS CLI:"
    echo "   aws configure"
    exit 1
fi

echo "✓ Authenticated as: $CURRENT_USER"
echo "✓ Account ID: $CURRENT_ACCOUNT"

if [ "$CURRENT_ACCOUNT" != "$ACCOUNT_ID" ]; then
    echo "⚠ Warning: Current account ($CURRENT_ACCOUNT) doesn't match expected ($ACCOUNT_ID)"
    echo "Do you want to continue anyway? (y/n)"
    read -r response
    if [ "$response" != "y" ]; then
        exit 1
    fi
    ACCOUNT_ID=$CURRENT_ACCOUNT
fi

echo ""
echo "Step 2: Deleting existing CDK bootstrap stack..."
echo "----------------------------------------"
CDK_STACK_NAME="CDKToolkit"

if aws cloudformation describe-stacks --stack-name $CDK_STACK_NAME --region $REGION &>/dev/null; then
    echo "Found existing CDKToolkit stack. Deleting..."
    
    # First, empty the staging bucket if it exists
    STAGING_BUCKET=$(aws cloudformation describe-stacks --stack-name $CDK_STACK_NAME --region $REGION --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' --output text 2>/dev/null || echo "")
    
    if [ ! -z "$STAGING_BUCKET" ]; then
        echo "Emptying staging bucket: $STAGING_BUCKET"
        aws s3 rm s3://$STAGING_BUCKET --recursive --region $REGION 2>/dev/null || true
    fi
    
    echo "Deleting CDKToolkit stack..."
    aws cloudformation delete-stack --stack-name $CDK_STACK_NAME --region $REGION
    
    echo "Waiting for stack deletion (this may take a few minutes)..."
    aws cloudformation wait stack-delete-complete --stack-name $CDK_STACK_NAME --region $REGION 2>/dev/null || echo "Stack deletion completed or timed out"
    
    echo "✓ CDKToolkit stack deleted"
else
    echo "No existing CDKToolkit stack found"
fi

echo ""
echo "Step 3: Checking for orphaned CDK resources..."
echo "----------------------------------------"

# Check for CDK roles
echo "Checking IAM roles..."
CDK_ROLES=$(aws iam list-roles --query "Roles[?starts_with(RoleName, 'cdk-hnb659fds-')].RoleName" --output text 2>/dev/null || echo "")

if [ ! -z "$CDK_ROLES" ]; then
    echo "Found CDK roles to clean up:"
    for role in $CDK_ROLES; do
        echo "  Processing role: $role"
        
        # Detach managed policies
        ATTACHED=$(aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || echo "")
        for policy in $ATTACHED; do
            echo "    - Detaching policy: $policy"
            aws iam detach-role-policy --role-name $role --policy-arn $policy 2>/dev/null || true
        done
        
        # Delete inline policies
        INLINE=$(aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null || echo "")
        for policy in $INLINE; do
            echo "    - Deleting inline policy: $policy"
            aws iam delete-role-policy --role-name $role --policy-name $policy 2>/dev/null || true
        done
        
        # Remove from instance profiles
        PROFILES=$(aws iam list-instance-profiles-for-role --role-name $role --query 'InstanceProfiles[].InstanceProfileName' --output text 2>/dev/null || echo "")
        for profile in $PROFILES; do
            echo "    - Removing from instance profile: $profile"
            aws iam remove-role-from-instance-profile --instance-profile-name $profile --role-name $role 2>/dev/null || true
            aws iam delete-instance-profile --instance-profile-name $profile 2>/dev/null || true
        done
        
        # Delete the role
        echo "    - Deleting role: $role"
        aws iam delete-role --role-name $role 2>/dev/null || echo "      Could not delete role (may need manual cleanup)"
    done
    echo "✓ Roles processed"
else
    echo "No CDK roles found"
fi

# Check for CDK buckets
echo ""
echo "Checking S3 buckets..."
CDK_BUCKETS=$(aws s3api list-buckets --query "Buckets[?starts_with(Name, 'cdk-hnb659fds-')].Name" --output text 2>/dev/null || echo "")

if [ ! -z "$CDK_BUCKETS" ]; then
    echo "Found CDK buckets to clean up:"
    for bucket in $CDK_BUCKETS; do
        echo "  Processing bucket: $bucket"
        echo "    - Emptying bucket..."
        aws s3 rm s3://$bucket --recursive --region $REGION 2>/dev/null || true
        echo "    - Deleting bucket..."
        aws s3api delete-bucket --bucket $bucket --region $REGION 2>/dev/null || echo "      Could not delete bucket"
    done
    echo "✓ Buckets processed"
else
    echo "No CDK buckets found"
fi

echo ""
echo "Step 4: Waiting for cleanup to complete..."
echo "----------------------------------------"
sleep 10
echo "✓ Cleanup wait complete"

echo ""
echo "Step 5: Bootstrapping CDK with fresh setup..."
echo "----------------------------------------"
echo "Running: cdk bootstrap aws://$ACCOUNT_ID/$REGION"
echo ""

# Bootstrap with admin execution policies
cdk bootstrap aws://$ACCOUNT_ID/$REGION \
    --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
    --verbose

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ CDK bootstrap completed successfully!"
else
    echo ""
    echo "❌ Bootstrap failed. You may need to:"
    echo "   1. Check your IAM permissions (you need admin-like permissions)"
    echo "   2. Wait a few minutes for IAM to propagate"
    echo "   3. Run: cdk bootstrap aws://$ACCOUNT_ID/$REGION --force"
    exit 1
fi

echo ""
echo "Step 6: Verifying bootstrap..."
echo "----------------------------------------"
if aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &>/dev/null; then
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION --query 'Stacks[0].StackStatus' --output text)
    echo "✓ CDKToolkit stack status: $STACK_STATUS"
    
    echo ""
    echo "CDK Bootstrap Resources:"
    aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output table
else
    echo "⚠ Warning: CDKToolkit stack not found after bootstrap"
fi

echo ""
echo "========================================"
echo "Bootstrap Fix Complete!"
echo "========================================"
echo ""
echo "You can now deploy your stack:"
echo "  cdk deploy"
echo ""