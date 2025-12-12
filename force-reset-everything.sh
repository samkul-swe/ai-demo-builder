#!/bin/bash

# Force delete stuck CloudFormation stacks and reset CDK

echo "========================================"
echo "Force Delete Stuck Stacks & Reset CDK"
echo "========================================"
echo ""

ACCOUNT_ID="288418345946"
REGION="us-east-1"

echo "This will forcefully clean up everything and start fresh."
echo "Press Enter to continue..."
read

# Step 1: Try to delete with retain resources
echo ""
echo "Step 1: Attempting to delete AiDemoBuilderStack with retain..."
echo "==============================================================="

# First, try normal delete
aws cloudformation delete-stack --stack-name AiDemoBuilderStack --region $REGION 2>&1

# Wait a bit
sleep 5

# Check status
STACK_STATUS=$(aws cloudformation describe-stacks --stack-name AiDemoBuilderStack --region $REGION --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DELETED")

if [[ "$STACK_STATUS" != "DELETED" ]] && [[ "$STACK_STATUS" != "DELETE_COMPLETE" ]]; then
    echo "Stack is stuck in: $STACK_STATUS"
    echo ""
    echo "Getting list of resources in stack..."
    
    # Get all resources
    RESOURCES=$(aws cloudformation list-stack-resources --stack-name AiDemoBuilderStack --region $REGION --query 'StackResourceSummaries[].LogicalResourceId' --output text 2>/dev/null)
    
    if [ ! -z "$RESOURCES" ]; then
        echo "Resources in stack:"
        echo "$RESOURCES"
        echo ""
        echo "Attempting to manually delete resources..."
        
        # Delete resources manually
        echo ""
        echo "Deleting IAM roles..."
        aws iam list-roles --query "Roles[?starts_with(RoleName, 'AiDemo') || RoleName=='lambda-execution-role'].RoleName" --output text | \
          while read role; do
            if [ ! -z "$role" ]; then
                echo "  - $role"
                aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null | \
                  xargs -I {} aws iam detach-role-policy --role-name $role --policy-arn {} 2>/dev/null
                aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null | \
                  xargs -I {} aws iam delete-role-policy --role-name $role --policy-name {} 2>/dev/null
                aws iam delete-role --role-name $role 2>/dev/null || echo "    Could not delete"
            fi
          done
        
        echo ""
        echo "Deleting S3 buckets..."
        aws s3api list-buckets --query "Buckets[?starts_with(Name, 'ai-demo') || starts_with(Name, 'aidemo')].Name" --output text | \
          while read bucket; do
            if [ ! -z "$bucket" ]; then
                echo "  - $bucket"
                aws s3 rm s3://$bucket --recursive --region $REGION 2>/dev/null
                aws s3api delete-bucket --bucket $bucket --region $REGION 2>/dev/null || echo "    Could not delete"
            fi
          done
        
        echo ""
        echo "Deleting DynamoDB tables..."
        aws dynamodb list-tables --region $REGION --query "TableNames[?contains(@, 'AiDemo') || contains(@, 'ai-demo')]" --output text | \
          while read table; do
            if [ ! -z "$table" ]; then
                echo "  - $table"
                aws dynamodb delete-table --table-name $table --region $REGION 2>/dev/null || echo "    Could not delete"
            fi
          done
        
        echo ""
        echo "Deleting Lambda functions..."
        aws lambda list-functions --region $REGION --query "Functions[?starts_with(FunctionName, 'service-')].FunctionName" --output text | \
          while read func; do
            if [ ! -z "$func" ]; then
                echo "  - $func"
                aws lambda delete-function --function-name $func --region $REGION 2>/dev/null || echo "    Could not delete"
            fi
          done
        
        echo ""
        echo "Deleting API Gateways..."
        aws apigateway get-rest-apis --region $REGION --query "items[?contains(name, 'AiDemo') || contains(name, 'AI Demo')].id" --output text | \
          while read api; do
            if [ ! -z "$api" ]; then
                echo "  - $api"
                aws apigateway delete-rest-api --rest-api-id $api --region $REGION 2>/dev/null || echo "    Could not delete"
            fi
          done
        
        echo ""
        echo "Deleting SQS queues..."
        aws sqs list-queues --region $REGION --query "QueueUrls[?contains(@, 'video-processing') || contains(@, 'ai-demo')]" --output text | \
          while read queue; do
            if [ ! -z "$queue" ]; then
                echo "  - $queue"
                aws sqs delete-queue --queue-url $queue --region $REGION 2>/dev/null || echo "    Could not delete"
            fi
          done
        
        echo ""
        echo "Deleting SNS topics..."
        aws sns list-topics --region $REGION --query "Topics[?contains(TopicArn, 'demo-notifications')].TopicArn" --output text | \
          while read topic; do
            if [ ! -z "$topic" ]; then
                echo "  - $topic"
                aws sns delete-topic --topic-arn $topic --region $REGION 2>/dev/null || echo "    Could not delete"
            fi
          done
        
        echo ""
        echo "Waiting 30 seconds for deletions to propagate..."
        sleep 30
        
        # Try to delete stack again
        echo ""
        echo "Attempting to delete stack again..."
        aws cloudformation delete-stack --stack-name AiDemoBuilderStack --region $REGION 2>&1
        sleep 10
    fi
else
    echo "✓ Stack deleted successfully"
fi

# Step 2: Completely rebuild CDK bootstrap
echo ""
echo "Step 2: Completely rebuilding CDK bootstrap..."
echo "==============================================="

# Delete CDKToolkit
echo "Deleting CDKToolkit stack..."
aws cloudformation delete-stack --stack-name CDKToolkit --region $REGION 2>/dev/null
echo "Waiting for deletion..."
aws cloudformation wait stack-delete-complete --stack-name CDKToolkit --region $REGION 2>/dev/null || echo "Stack deleted or didn't exist"

# Delete CDK S3 buckets
echo ""
echo "Deleting CDK S3 buckets..."
aws s3api list-buckets --query "Buckets[?starts_with(Name, 'cdk-hnb659fds-')].Name" --output text | \
  while read bucket; do
    if [ ! -z "$bucket" ]; then
        echo "  - $bucket"
        aws s3 rm s3://$bucket --recursive 2>/dev/null
        aws s3api delete-bucket --bucket $bucket 2>/dev/null || echo "    Could not delete"
    fi
  done

# Delete CDK IAM roles
echo ""
echo "Deleting CDK IAM roles..."
aws iam list-roles --query "Roles[?starts_with(RoleName, 'cdk-hnb659fds-')].RoleName" --output text | \
  while read role; do
    if [ ! -z "$role" ]; then
        echo "  - $role"
        aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null | \
          xargs -I {} aws iam detach-role-policy --role-name $role --policy-arn {} 2>/dev/null
        aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null | \
          xargs -I {} aws iam delete-role-policy --role-name $role --policy-name {} 2>/dev/null
        aws iam delete-role --role-name $role 2>/dev/null || echo "    Could not delete"
    fi
  done

# Clear CDK context
echo ""
echo "Clearing CDK cache and context..."
rm -f cdk.context.json
rm -rf cdk.out
rm -rf ~/.cdk/cache

echo ""
echo "Waiting 15 seconds for AWS to catch up..."
sleep 15

# Fresh bootstrap
echo ""
echo "Creating fresh CDK bootstrap..."
cdk bootstrap aws://$ACCOUNT_ID/$REGION \
    --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
    --trust $ACCOUNT_ID \
    --trust-for-lookup $ACCOUNT_ID \
    --verbose

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Bootstrap successful!"
    
    # Verify
    echo ""
    echo "Verifying CDK bootstrap..."
    sleep 5
    
    if aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &>/dev/null; then
        echo "✓ CDKToolkit stack exists"
        
        EXEC_ROLE="cdk-hnb659fds-cfn-exec-role-$ACCOUNT_ID-$REGION"
        if aws iam get-role --role-name $EXEC_ROLE &>/dev/null; then
            echo "✓ Execution role exists: $EXEC_ROLE"
        else
            echo "❌ Execution role missing: $EXEC_ROLE"
            echo ""
            echo "Bootstrap may have failed. Try running:"
            echo "  cdk bootstrap aws://$ACCOUNT_ID/$REGION --force"
            exit 1
        fi
    else
        echo "❌ CDKToolkit stack not found"
        exit 1
    fi
else
    echo ""
    echo "❌ Bootstrap failed!"
    exit 1
fi

echo ""
echo "========================================"
echo "Reset Complete!"
echo "========================================"
echo ""
echo "Everything has been cleaned up and CDK is freshly bootstrapped."
echo ""
echo "Now deploy your stack:"
echo "  cdk deploy"
echo ""
