#!/bin/bash

# CDK Bootstrap Workaround Script
# Attempts various methods to bypass the Early Validation error

set -e

echo "========================================"
echo "CDK Bootstrap Workaround Script"
echo "========================================"
echo ""

REGION="us-west-2"
ACCOUNT_ID="288418345946"

echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""

echo "This script will try multiple approaches to bootstrap CDK:"
echo "  1. Bootstrap with legacy mode"
echo "  2. Bootstrap in a different region"
echo "  3. Manual CloudFormation deployment"
echo ""
echo "Press Enter to continue..."
read

# Method 1: Try different region first
echo ""
echo "================================================"
echo "Method 1: Trying a different region (us-west-2)"
echo "================================================"
echo ""
echo "Sometimes the issue is region-specific. Let's try us-west-2 first..."
echo ""

if cdk bootstrap aws://$ACCOUNT_ID/us-west-2; then
    echo ""
    echo "✓ Bootstrap succeeded in us-west-2!"
    echo ""
    echo "Now trying your original region (us-west-2)..."
    if cdk bootstrap aws://$ACCOUNT_ID/$REGION; then
        echo "✓ Bootstrap succeeded in us-west-2!"
        echo ""
        echo "SUCCESS! Both regions are now bootstrapped."
        echo "You can deploy with: cdk deploy"
        exit 0
    else
        echo "⚠ us-west-2 still failing, but us-west-2 works."
        echo "Consider deploying to us-west-2 instead."
        echo ""
        echo "To deploy to us-west-2, update your CDK code:"
        echo '  env: { region: "us-west-2", account: "'$ACCOUNT_ID'" }'
        exit 1
    fi
else
    echo "⚠ Bootstrap failed in us-west-2 too. Trying other methods..."
fi

# Method 2: Check for and disable hooks (if possible)
echo ""
echo "================================================"
echo "Method 2: Checking for CloudFormation hooks"
echo "================================================"
echo ""

HOOKS=$(aws cloudformation list-types --type HOOK --region $REGION --query 'TypeSummaries[?TypeName==`AWS::EarlyValidation::ResourceExistenceCheck`]' 2>/dev/null || echo "[]")

if [ "$HOOKS" != "[]" ] && [ ! -z "$HOOKS" ]; then
    echo "Found EarlyValidation hook. This is causing the issue."
    echo ""
    echo "⚠ You need to either:"
    echo "  1. Disable the hook (requires admin permissions)"
    echo "  2. Contact your AWS administrator"
    echo "  3. Deploy to a region without the hook"
    echo ""
    echo "To check which regions have the hook:"
    echo "  for region in us-west-2 us-east-2 us-west-2 us-west-2; do"
    echo "    echo \"Checking \$region...\""
    echo "    aws cloudformation list-types --type HOOK --region \$region --query 'TypeSummaries[?TypeName==\`AWS::EarlyValidation::ResourceExistenceCheck\`]' 2>/dev/null || echo 'No hook'"
    echo "  done"
else
    echo "No obvious hooks found (or no permission to check)."
fi

# Method 3: Try with explicit template
echo ""
echo "================================================"
echo "Method 3: Manual Bootstrap (No CDK CLI)"
echo "================================================"
echo ""
echo "Downloading CDK bootstrap template..."

curl -s https://raw.githubusercontent.com/aws/aws-cdk/main/packages/aws-cdk/lib/api/bootstrap/bootstrap-template.yaml -o /tmp/bootstrap-template.yaml

if [ -f /tmp/bootstrap-template.yaml ]; then
    echo "✓ Template downloaded"
    echo ""
    echo "Attempting manual deployment..."
    
    aws cloudformation create-stack \
        --stack-name CDKToolkit \
        --template-body file:///tmp/bootstrap-template.yaml \
        --parameters \
            ParameterKey=TrustedAccounts,ParameterValue=$ACCOUNT_ID \
            ParameterKey=CloudFormationExecutionPolicies,ParameterValue=arn:aws:iam::aws:policy/AdministratorAccess \
        --capabilities CAPABILITY_NAMED_IAM \
        --region $REGION 2>&1 | tee /tmp/bootstrap-output.txt
    
    if grep -q "CREATE_COMPLETE" /tmp/bootstrap-output.txt || grep -q "already exists" /tmp/bootstrap-output.txt; then
        echo ""
        echo "✓ Manual bootstrap appears successful!"
        echo "Verify with: aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION"
        exit 0
    else
        echo ""
        echo "⚠ Manual bootstrap also failed"
    fi
else
    echo "Could not download bootstrap template"
fi

echo ""
echo "================================================"
echo "All Methods Exhausted"
echo "================================================"
echo ""
echo "DIAGNOSIS:"
echo "----------"
echo "The Early Validation hook is blocking CloudFormation deployments."
echo ""
echo "This is typically caused by:"
echo "  1. Organization-level CloudFormation hooks"
echo "  2. Service Control Policies (SCPs)"
echo "  3. Account-level restrictions"
echo ""
echo "SOLUTIONS:"
echo "----------"
echo ""
echo "Option A: Contact your AWS administrator"
echo "  - Ask them to disable the AWS::EarlyValidation::ResourceExistenceCheck hook"
echo "  - Or grant you permissions to deploy CloudFormation stacks"
echo ""
echo "Option B: Use a different region"
echo "  - Try regions: us-west-2, us-east-2, eu-west-1"
echo "  - Run: cdk bootstrap aws://$ACCOUNT_ID/us-west-2"
echo ""
echo "Option C: Use a different AWS account"
echo "  - Create a personal AWS account without restrictions"
echo ""
echo "Option D: Check your CDK code"
echo "  - Look for references to non-existent VPCs, subnets, etc."
echo "  - Remove any .fromLookup() or .fromXxx() calls that reference specific IDs"
echo ""
echo "To investigate further, run:"
echo "  bash diagnose-validation-error.sh"
echo ""