#!/bin/bash
# AI Demo Builder - Complete Reset Script
# Deletes EVERYTHING and resets CDK bootstrap
# Version: 2.0 - Enhanced with better error handling

set +e  # Continue on errors

ACCOUNT_ID="288418345946"
REGION="us-east-1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ========================
# SAFETY CONFIRMATION
# ========================

echo ""
echo "=========================================="
echo "☢️  AI DEMO BUILDER - COMPLETE RESET"
echo "=========================================="
echo ""
echo -e "${RED}WARNING: This will delete ALL resources in ${REGION}:${NC}"
echo "  - CloudFormation stacks (AiDemoBuilderStack, CDKToolkit)"
echo "  - S3 buckets and ALL files"
echo "  - DynamoDB tables and ALL data"
echo "  - Lambda functions and layers"
echo "  - API Gateway"
echo "  - SQS queues and messages"
echo "  - SNS topics and subscriptions"
echo "  - EventBridge rules"
echo "  - CloudWatch logs"
echo "  - IAM roles and policies"
echo ""
echo -e "${YELLOW}Account: ${ACCOUNT_ID}${NC}"
echo -e "${YELLOW}Region:  ${REGION}${NC}"
echo ""
read -p "Type 'DELETE EVERYTHING' to confirm: " confirm

if [ "$confirm" != "DELETE EVERYTHING" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🧹 Starting cleanup..."
echo ""

# ========================
# HELPER FUNCTIONS
# ========================

delete_count=0

mark_deleted() {
    ((delete_count++))
    echo -e "   ${GREEN}✅ Deleted${NC}"
}

mark_not_found() {
    echo -e "   ${BLUE}⏭️  Not found${NC}"
}

mark_failed() {
    echo -e "   ${RED}❌ Failed: $1${NC}"
}

# ========================
# PHASE 1: DELETE APPLICATION RESOURCES
# ========================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 1: Application Resources"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. CloudFormation Stacks
echo "1. CloudFormation Stacks"
echo "------------------------"

for stack in AiDemoBuilderStack; do
    if aws cloudformation describe-stacks --stack-name $stack --region $REGION &>/dev/null; then
        echo "Deleting stack: $stack"
        aws cloudformation delete-stack --stack-name $stack --region $REGION
        mark_deleted
    else
        echo "Stack: $stack"
        mark_not_found
    fi
done

# Wait for stack deletion to start
sleep 10

echo ""

# 2. S3 Buckets (APPLICATION ONLY)
echo "2. S3 Buckets"
echo "-------------"

aws s3api list-buckets --query "Buckets[].Name" --output text 2>/dev/null | tr '\t' '\n' | while read bucket; do
    if [[ $bucket == *"ai-demo"* ]] || [[ $bucket == *"aidemo"* ]] || [[ $bucket =~ ^aidemobuild.* ]]; then
        echo "Bucket: $bucket"
        echo "   Emptying..."
        aws s3 rm s3://$bucket --recursive --region $REGION &>/dev/null
        echo "   Deleting..."
        aws s3api delete-bucket --bucket $bucket --region $REGION 2>/dev/null && mark_deleted || mark_failed "May be in use by CloudFormation"
    fi
done

echo ""

# 3. DynamoDB Tables
echo "3. DynamoDB Tables"
echo "------------------"

aws dynamodb list-tables --region $REGION --query 'TableNames[]' --output text 2>/dev/null | tr '\t' '\n' | while read table; do
    if [[ $table == *"ai-demo"* ]] || [[ $table == *"AiDemo"* ]]; then
        echo "Table: $table"
        aws dynamodb delete-table --table-name $table --region $REGION 2>/dev/null && mark_deleted || mark_failed "May not exist"
    fi
done

echo ""

# 4. Lambda Functions
echo "4. Lambda Functions"
echo "-------------------"

func_count=0
aws lambda list-functions --region $REGION --query 'Functions[].FunctionName' --output text 2>/dev/null | tr '\t' '\n' | while read func; do
    if [[ $func == service-* ]] || [[ $func == *AiDemo* ]] || [[ $func == *BucketNotifications* ]] || [[ $func == *S3AutoDelete* ]]; then
        echo "Function: $func"
        aws lambda delete-function --function-name $func --region $REGION 2>/dev/null && mark_deleted || mark_not_found
        ((func_count++))
    fi
done

if [ $func_count -eq 0 ]; then
    echo "No Lambda functions found"
fi

echo ""

# 5. Lambda Layers
echo "5. Lambda Layers"
echo "----------------"

layer_count=0
aws lambda list-layers --region $REGION --query 'Layers[].LayerName' --output text 2>/dev/null | tr '\t' '\n' | while read layer; do
    if [[ $layer == *FFmpeg* ]] || [[ $layer == *AiDemo* ]]; then
        echo "Layer: $layer"
        versions=$(aws lambda list-layer-versions --layer-name $layer --region $REGION --query 'LayerVersions[].Version' --output text 2>/dev/null)
        for version in $versions; do
            aws lambda delete-layer-version --layer-name $layer --version-number $version --region $REGION 2>/dev/null
        done
        mark_deleted
        ((layer_count++))
    fi
done

if [ $layer_count -eq 0 ]; then
    echo "No Lambda layers found"
fi

echo ""

# 6. API Gateway
echo "6. API Gateway"
echo "--------------"

api_count=0
aws apigateway get-rest-apis --region $REGION --query 'items[].[id,name]' --output text 2>/dev/null | while read -r api_id api_name; do
    if [[ $api_name == *"AI Demo"* ]] || [[ $api_name == *"AiDemo"* ]]; then
        echo "API: $api_name ($api_id)"
        aws apigateway delete-rest-api --rest-api-id $api_id --region $REGION 2>/dev/null && mark_deleted || mark_failed
        ((api_count++))
    fi
done

if [ $api_count -eq 0 ]; then
    echo "No API Gateways found"
fi

echo ""

# 7. SQS Queues
echo "7. SQS Queues"
echo "-------------"

aws sqs list-queues --region $REGION 2>/dev/null | grep -E 'video-processing|ai-demo' | while read queue_url; do
    if [ ! -z "$queue_url" ]; then
        echo "Queue: $(basename $queue_url)"
        aws sqs delete-queue --queue-url $queue_url --region $REGION 2>/dev/null && mark_deleted || mark_not_found
    fi
done

echo ""

# 8. SNS Topics
echo "8. SNS Topics"
echo "-------------"

aws sns list-topics --region $REGION --query 'Topics[].TopicArn' --output text 2>/dev/null | tr '\t' '\n' | while read topic; do
    if [[ $topic == *"demo-notification"* ]] || [[ $topic == *"AiDemo"* ]]; then
        echo "Topic: $(basename $topic)"
        aws sns delete-topic --topic-arn $topic --region $REGION 2>/dev/null && mark_deleted || mark_not_found
    fi
done

echo ""

# 9. EventBridge Rules
echo "9. EventBridge Rules"
echo "--------------------"

aws events list-rules --region $REGION --query 'Rules[].Name' --output text 2>/dev/null | tr '\t' '\n' | while read rule; do
    if [[ $rule == *"Cleanup"* ]] || [[ $rule == *"AiDemo"* ]]; then
        echo "Rule: $rule"
        # Remove all targets first
        targets=$(aws events list-targets-by-rule --rule $rule --region $REGION --query 'Targets[].Id' --output text 2>/dev/null)
        for target_id in $targets; do
            aws events remove-targets --rule $rule --ids $target_id --region $REGION 2>/dev/null
        done
        aws events delete-rule --name $rule --region $REGION 2>/dev/null && mark_deleted || mark_not_found
    fi
done

echo ""

# 10. CloudWatch Log Groups
echo "10. CloudWatch Log Groups"
echo "-------------------------"

log_count=0
aws logs describe-log-groups --region $REGION --query 'logGroups[].logGroupName' --output text 2>/dev/null | tr '\t' '\n' | while read lg; do
    if [[ $lg == *"/aws/lambda/service-"* ]] || [[ $lg == *"AiDemo"* ]]; then
        echo "Log Group: $lg"
        aws logs delete-log-group --log-group-name "$lg" --region $REGION 2>/dev/null && mark_deleted || mark_not_found
        ((log_count++))
    fi
done

if [ $log_count -eq 0 ]; then
    echo "No log groups found"
fi

echo ""

# 11. IAM Roles (Application Only)
echo "11. IAM Roles (Application)"
echo "---------------------------"

for role in lambda-execution-role $(aws iam list-roles --query "Roles[?contains(RoleName, 'AiDemo')].RoleName" --output text 2>/dev/null); do
    if [ ! -z "$role" ] && [ "$role" != "None" ]; then
        echo "Role: $role"
        # Detach managed policies
        aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null | tr '\t' '\n' | while read policy; do
            aws iam detach-role-policy --role-name $role --policy-arn $policy 2>/dev/null
        done
        # Delete inline policies
        aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null | tr '\t' '\n' | while read policy; do
            aws iam delete-role-policy --role-name $role --policy-name $policy 2>/dev/null
        done
        # Delete role
        aws iam delete-role --role-name $role 2>/dev/null && mark_deleted || mark_failed "May be in use"
    fi
done

echo ""
echo "⏳ Waiting 30 seconds for resources to fully delete..."
sleep 30

# ========================
# PHASE 2: REBUILD CDK BOOTSTRAP
# ========================

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 2: CDK Bootstrap Reset"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Delete existing CDKToolkit
echo "1. Deleting existing CDKToolkit stack..."
if aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &>/dev/null; then
    aws cloudformation delete-stack --stack-name CDKToolkit --region $REGION
    echo "   Waiting for deletion..."
    aws cloudformation wait stack-delete-complete --stack-name CDKToolkit --region $REGION 2>/dev/null || true
    echo -e "   ${GREEN}✅ CDKToolkit deleted${NC}"
else
    echo -e "   ${BLUE}⏭️  CDKToolkit doesn't exist${NC}"
fi

echo ""

# Delete CDK staging buckets
echo "2. Deleting CDK staging buckets..."
aws s3api list-buckets --query "Buckets[?starts_with(Name, 'cdk-') || starts_with(Name, 'cdktoolkit-')].Name" --output text 2>/dev/null | tr '\t' '\n' | while read bucket; do
    if [ ! -z "$bucket" ]; then
        echo "   Bucket: $bucket"
        aws s3 rm s3://$bucket --recursive 2>/dev/null
        aws s3api delete-bucket --bucket $bucket 2>/dev/null && echo -e "      ${GREEN}✅ Deleted${NC}" || echo -e "      ${BLUE}⏭️  Skipped${NC}"
    fi
done

echo ""

# Delete CDK IAM roles
echo "3. Deleting CDK IAM roles..."
aws iam list-roles --query "Roles[?starts_with(RoleName, 'cdk-hnb659fds-')].RoleName" --output text 2>/dev/null | tr '\t' '\n' | while read role; do
    if [ ! -z "$role" ]; then
        echo "   Role: $role"
        # Detach all policies
        aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null | tr '\t' '\n' | while read policy; do
            aws iam detach-role-policy --role-name $role --policy-arn $policy 2>/dev/null
        done
        # Delete inline policies
        aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null | tr '\t' '\n' | while read policy; do
            aws iam delete-role-policy --role-name $role --policy-name $policy 2>/dev/null
        done
        # Delete role
        aws iam delete-role --role-name $role 2>/dev/null && echo -e "      ${GREEN}✅ Deleted${NC}" || echo -e "      ${YELLOW}⚠️  May still be in use${NC}"
    fi
done

echo ""

# Delete SSM parameters (CDK stores bootstrap version here)
echo "4. Deleting CDK SSM parameters..."
aws ssm delete-parameter --name /cdk-bootstrap/hnb659fds/version --region $REGION 2>/dev/null && echo -e "   ${GREEN}✅ Deleted${NC}" || echo -e "   ${BLUE}⏭️  Not found${NC}"

echo ""

# Clear local CDK cache
echo "5. Clearing local CDK cache..."
rm -rf cdk.out 2>/dev/null && echo -e "   ${GREEN}✅ Deleted cdk.out${NC}"
rm -f cdk.context.json 2>/dev/null && echo -e "   ${GREEN}✅ Deleted cdk.context.json${NC}"
rm -rf ~/.cdk/cache 2>/dev/null && echo -e "   ${GREEN}✅ Cleared ~/.cdk/cache${NC}"

echo ""
echo -e "${YELLOW}⏳ Waiting 60 seconds for AWS to propagate deletions...${NC}"
sleep 60

# ========================
# PHASE 3: VERIFICATION
# ========================

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 3: Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

errors=0

# Check CloudFormation
echo "Checking CloudFormation stacks..."
remaining_stacks=$(aws cloudformation list-stacks --region $REGION \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_IN_PROGRESS \
  --query 'StackSummaries[?contains(StackName, `AiDemo`) || StackName==`CDKToolkit`].StackName' \
  --output text 2>/dev/null)

if [ -z "$remaining_stacks" ]; then
    echo -e "   ${GREEN}✅ No stacks remain${NC}"
else
    echo -e "   ${YELLOW}⚠️  Stacks still exist (may be deleting): $remaining_stacks${NC}"
fi

# Check S3
echo "Checking S3 buckets..."
remaining_buckets=$(aws s3 ls --region $REGION 2>/dev/null | grep -E 'ai-demo|aidemo|cdktoolkit' || echo "")
if [ -z "$remaining_buckets" ]; then
    echo -e "   ${GREEN}✅ No buckets remain${NC}"
else
    echo -e "   ${YELLOW}⚠️  Buckets still exist:${NC}"
    echo "$remaining_buckets"
    ((errors++))
fi

# Check DynamoDB
echo "Checking DynamoDB tables..."
remaining_tables=$(aws dynamodb list-tables --region $REGION 2>/dev/null | grep -E 'ai-demo|AiDemo' || echo "")
if [ -z "$remaining_tables" ]; then
    echo -e "   ${GREEN}✅ No tables remain${NC}"
else
    echo -e "   ${YELLOW}⚠️  Tables still exist:${NC}"
    echo "$remaining_tables"
    ((errors++))
fi

# Check Lambda
echo "Checking Lambda functions..."
remaining_funcs=$(aws lambda list-functions --region $REGION --query 'Functions[?starts_with(FunctionName, `service-`)].FunctionName' --output text 2>/dev/null)
if [ -z "$remaining_funcs" ]; then
    echo -e "   ${GREEN}✅ No Lambda functions remain${NC}"
else
    echo -e "   ${YELLOW}⚠️  Functions still exist: $remaining_funcs${NC}"
    ((errors++))
fi

echo ""

# ========================
# PHASE 4: FRESH CDK BOOTSTRAP
# ========================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 4: Fresh CDK Bootstrap"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $errors -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Warning: Some resources still exist${NC}"
    echo "   Recommendation: Wait 2 minutes and run bootstrap manually:"
    echo "   cdk bootstrap aws://$ACCOUNT_ID/$REGION"
    echo ""
    read -p "Continue with bootstrap anyway? (y/n): " continue_bootstrap
    if [ "$continue_bootstrap" != "y" ]; then
        echo "Exiting. Run bootstrap manually when ready."
        exit 0
    fi
fi

echo "Bootstrapping CDK for $ACCOUNT_ID in $REGION..."
echo ""

cd infrastructure 2>/dev/null || cd .

cdk bootstrap aws://$ACCOUNT_ID/$REGION \
    --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
    --trust $ACCOUNT_ID \
    --trust-for-lookup $ACCOUNT_ID \
    --verbose

BOOTSTRAP_EXIT_CODE=$?

echo ""

if [ $BOOTSTRAP_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Bootstrap successful!${NC}"
    
    # Verify bootstrap
    echo ""
    echo "Verifying bootstrap..."
    sleep 5
    
    if aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &>/dev/null; then
        echo -e "   ${GREEN}✅ CDKToolkit stack exists${NC}"
        
        EXEC_ROLE="cdk-hnb659fds-cfn-exec-role-$ACCOUNT_ID-$REGION"
        if aws iam get-role --role-name $EXEC_ROLE &>/dev/null 2>&1; then
            echo -e "   ${GREEN}✅ Execution role exists${NC}"
        else
            echo -e "   ${RED}❌ Execution role missing${NC}"
            echo ""
            echo "Try manual bootstrap:"
            echo "   cdk bootstrap aws://$ACCOUNT_ID/$REGION --force"
            exit 1
        fi
    else
        echo -e "   ${RED}❌ CDKToolkit stack not found${NC}"
        exit 1
    fi
    
else
    echo -e "${RED}❌ Bootstrap failed!${NC}"
    echo ""
    echo "Common fixes:"
    echo "  1. Check AWS credentials: aws sts get-caller-identity"
    echo "  2. Check region: echo \$AWS_REGION"
    echo "  3. Try with --force flag: cdk bootstrap aws://$ACCOUNT_ID/$REGION --force"
    echo "  4. Check IAM permissions (need AdministratorAccess or similar)"
    exit 1
fi

# ========================
# PHASE 5: FINAL SUMMARY
# ========================

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 RESET COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Summary:"
echo "  • Deleted resources: $delete_count"
echo "  • CDK bootstrap: Fresh"
echo "  • AWS Region: $REGION"
echo "  • Account: $ACCOUNT_ID"
echo ""
echo "Your AWS account is clean and ready for fresh deployment!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "DEPLOYMENT CHECKLIST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Before deploying, verify:"
echo ""
echo "1. .env file has your API keys:"
read -p "   Press Enter to check .env..."
if [ -f ../.env ]; then
    echo -e "   ${GREEN}✅ .env exists${NC}"
    if grep -q "GEMINI_API_KEY=AIza" ../.env 2>/dev/null; then
        echo -e "   ${GREEN}✅ GEMINI_API_KEY is set${NC}"
    else
        echo -e "   ${YELLOW}⚠️  GEMINI_API_KEY not set or empty${NC}"
    fi
    if grep -q "GITHUB_TOKEN=ghp_" ../.env 2>/dev/null; then
        echo -e "   ${GREEN}✅ GITHUB_TOKEN is set${NC}"
    else
        echo -e "   ${YELLOW}⚠️  GITHUB_TOKEN not set (optional)${NC}"
    fi
else
    echo -e "   ${RED}❌ .env file not found!${NC}"
    echo "   Create it: cp .env.example .env"
fi
echo ""

echo "2. FFmpeg layer is set up:"
if [ -f ../layers/ffmpeg/python/bin/ffmpeg ]; then
    echo -e "   ${GREEN}✅ FFmpeg layer exists${NC}"
    ls -lh ../layers/ffmpeg/python/bin/ | grep -E 'ffmpeg|ffprobe'
else
    echo -e "   ${RED}❌ FFmpeg layer missing!${NC}"
    echo "   Run: ./setup-ffmpeg-layer.sh"
fi
echo ""

echo "3. All Lambda code exists:"
missing_services=0
for i in {1..4}; do
    if [ $i -eq 4 ]; then
        path="../lambda/support/service-$i-*"
    else
        path="../lambda/analysis/service-$i-*"
    fi
    if ! ls $path 2>/dev/null | grep -q index.py; then
        echo -e "   ${RED}❌ Service $i missing${NC}"
        ((missing_services++))
    fi
done
for i in {5..6}; do
    if ! ls ../lambda/ai/service-$i-*/index.py 2>/dev/null | grep -q .; then
        echo -e "   ${RED}❌ Service $i missing${NC}"
        ((missing_services++))
    fi
done
for i in {7..10}; do
    if ! ls ../lambda/upload/service-$i-*/index.py 2>/dev/null | grep -q .; then
        echo -e "   ${RED}❌ Service $i missing${NC}"
        ((missing_services++))
    fi
done
for i in {11..14}; do
    if ! ls ../lambda/processing/service-$i-*/index.py 2>/dev/null | grep -q .; then
        echo -e "   ${RED}❌ Service $i missing${NC}"
        ((missing_services++))
    fi
done
for i in {15..17}; do
    if ! ls ../lambda/support/service-$i-*/index.py 2>/dev/null | grep -q .; then
        echo -e "   ${RED}❌ Service $i missing${NC}"
        ((missing_services++))
    fi
done

if [ $missing_services -eq 0 ]; then
    echo -e "   ${GREEN}✅ All 17 services found${NC}"
else
    echo -e "   ${RED}❌ $missing_services services missing${NC}"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "READY TO DEPLOY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. cd infrastructure"
echo "  2. source .venv/bin/activate"
echo "  3. cdk synth     # Test synthesis"
echo "  4. cdk deploy    # Deploy everything"
echo ""
echo "If deployment fails with ResourceExistenceCheck:"
echo "  Run this script again - some resources may still be deleting"
echo ""