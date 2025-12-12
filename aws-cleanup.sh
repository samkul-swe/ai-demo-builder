#!/bin/bash

# AWS Complete Cleanup Script
# This script will delete AWS resources in the correct order to avoid dependency errors

set -e

echo "========================================"
echo "AWS Resource Cleanup Script"
echo "========================================"
echo ""

# Get the current region
REGION=$(aws configure get region)
if [ -z "$REGION" ]; then
    echo "No default region set. Please enter your AWS region (e.g., us-west-2):"
    read REGION
fi

echo "Using region: $REGION"
echo ""
echo "WARNING: This will delete resources in your AWS account!"
echo "Press Ctrl+C to cancel, or press Enter to continue..."
read

echo ""
echo "Step 1: Deleting CDK Stack (if exists)..."
echo "----------------------------------------"
CDK_STACK_NAME="AiDemoBuilderStack"
if aws cloudformation describe-stacks --stack-name $CDK_STACK_NAME --region $REGION &>/dev/null; then
    echo "Found stack: $CDK_STACK_NAME"
    echo "Deleting stack..."
    aws cloudformation delete-stack --stack-name $CDK_STACK_NAME --region $REGION
    echo "Waiting for stack deletion to complete (this may take several minutes)..."
    aws cloudformation wait stack-delete-complete --stack-name $CDK_STACK_NAME --region $REGION 2>/dev/null || echo "Stack deletion completed or stack not found"
    echo "✓ Stack deleted"
else
    echo "Stack $CDK_STACK_NAME not found, skipping..."
fi

echo ""
echo "Step 2: Deleting All CloudFormation Stacks..."
echo "----------------------------------------"
STACKS=$(aws cloudformation list-stacks --region $REGION --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query 'StackSummaries[].StackName' --output text)
if [ ! -z "$STACKS" ]; then
    for stack in $STACKS; do
        if [[ $stack != CDKToolkit* ]]; then  # Keep CDK toolkit for now
            echo "Deleting stack: $stack"
            aws cloudformation delete-stack --stack-name $stack --region $REGION
        fi
    done
    echo "Waiting for stacks to delete..."
    sleep 30
else
    echo "No additional stacks found"
fi

echo ""
echo "Step 3: Emptying and Deleting S3 Buckets..."
echo "----------------------------------------"
BUCKETS=$(aws s3api list-buckets --query 'Buckets[].Name' --output text --region $REGION)
if [ ! -z "$BUCKETS" ]; then
    for bucket in $BUCKETS; do
        BUCKET_REGION=$(aws s3api get-bucket-location --bucket $bucket --output text 2>/dev/null || echo "us-west-2")
        if [ "$BUCKET_REGION" = "None" ]; then
            BUCKET_REGION="us-west-2"
        fi
        
        if [ "$BUCKET_REGION" = "$REGION" ]; then
            echo "Processing bucket: $bucket"
            
            # Remove all versions and delete markers
            echo "  - Removing all object versions..."
            aws s3api list-object-versions --bucket $bucket --output json --region $REGION 2>/dev/null | \
                jq -r '.Versions[]?, .DeleteMarkers[]? | "\(.Key)\t\(.VersionId)"' 2>/dev/null | \
                while IFS=$'\t' read -r key versionId; do
                    if [ ! -z "$key" ]; then
                        aws s3api delete-object --bucket $bucket --key "$key" --version-id "$versionId" --region $REGION 2>/dev/null || true
                    fi
                done
            
            # Empty the bucket
            echo "  - Emptying bucket..."
            aws s3 rm s3://$bucket --recursive --region $REGION 2>/dev/null || true
            
            # Delete the bucket
            echo "  - Deleting bucket..."
            aws s3api delete-bucket --bucket $bucket --region $REGION 2>/dev/null || echo "  - Could not delete $bucket (may have dependency)"
        fi
    done
    echo "✓ S3 buckets processed"
else
    echo "No S3 buckets found"
fi

echo ""
echo "Step 4: Deleting EC2 Instances..."
echo "----------------------------------------"
INSTANCES=$(aws ec2 describe-instances --region $REGION --filters "Name=instance-state-name,Values=running,stopped" --query 'Reservations[].Instances[].InstanceId' --output text)
if [ ! -z "$INSTANCES" ]; then
    echo "Terminating instances: $INSTANCES"
    aws ec2 terminate-instances --instance-ids $INSTANCES --region $REGION
    echo "Waiting for instances to terminate..."
    aws ec2 wait instance-terminated --instance-ids $INSTANCES --region $REGION 2>/dev/null || echo "Instances terminated or not found"
    echo "✓ EC2 instances terminated"
else
    echo "No EC2 instances found"
fi

echo ""
echo "Step 5: Deleting Load Balancers..."
echo "----------------------------------------"
# Application/Network Load Balancers
ALBS=$(aws elbv2 describe-load-balancers --region $REGION --query 'LoadBalancers[].LoadBalancerArn' --output text 2>/dev/null)
if [ ! -z "$ALBS" ]; then
    for alb in $ALBS; do
        echo "Deleting ALB/NLB: $alb"
        aws elbv2 delete-load-balancer --load-balancer-arn $alb --region $REGION
    done
    sleep 10
    echo "✓ Load balancers deleted"
else
    echo "No ALB/NLB found"
fi

# Classic Load Balancers
CLBS=$(aws elb describe-load-balancers --region $REGION --query 'LoadBalancerDescriptions[].LoadBalancerName' --output text 2>/dev/null)
if [ ! -z "$CLBS" ]; then
    for clb in $CLBS; do
        echo "Deleting Classic LB: $clb"
        aws elb delete-load-balancer --load-balancer-name $clb --region $REGION
    done
    echo "✓ Classic load balancers deleted"
else
    echo "No Classic LBs found"
fi

echo ""
echo "Step 6: Deleting Target Groups..."
echo "----------------------------------------"
TGS=$(aws elbv2 describe-target-groups --region $REGION --query 'TargetGroups[].TargetGroupArn' --output text 2>/dev/null)
if [ ! -z "$TGS" ]; then
    for tg in $TGS; do
        echo "Deleting target group: $tg"
        aws elbv2 delete-target-group --target-group-arn $tg --region $REGION 2>/dev/null || echo "Could not delete $tg"
    done
    echo "✓ Target groups deleted"
else
    echo "No target groups found"
fi

echo ""
echo "Step 7: Deleting RDS Instances..."
echo "----------------------------------------"
RDS_INSTANCES=$(aws rds describe-db-instances --region $REGION --query 'DBInstances[].DBInstanceIdentifier' --output text 2>/dev/null)
if [ ! -z "$RDS_INSTANCES" ]; then
    for rds in $RDS_INSTANCES; do
        echo "Deleting RDS instance: $rds"
        aws rds delete-db-instance --db-instance-identifier $rds --skip-final-snapshot --region $REGION 2>/dev/null || echo "Could not delete $rds"
    done
    echo "✓ RDS instances deletion initiated"
else
    echo "No RDS instances found"
fi

echo ""
echo "Step 8: Deleting ECS Clusters and Services..."
echo "----------------------------------------"
CLUSTERS=$(aws ecs list-clusters --region $REGION --query 'clusterArns[]' --output text 2>/dev/null)
if [ ! -z "$CLUSTERS" ]; then
    for cluster in $CLUSTERS; do
        echo "Processing ECS cluster: $cluster"
        
        # Get services in the cluster
        SERVICES=$(aws ecs list-services --cluster $cluster --region $REGION --query 'serviceArns[]' --output text 2>/dev/null)
        if [ ! -z "$SERVICES" ]; then
            for service in $SERVICES; do
                echo "  - Updating service to 0 tasks: $service"
                aws ecs update-service --cluster $cluster --service $service --desired-count 0 --region $REGION 2>/dev/null || true
                echo "  - Deleting service: $service"
                aws ecs delete-service --cluster $cluster --service $service --force --region $REGION 2>/dev/null || true
            done
        fi
        
        echo "  - Deleting cluster: $cluster"
        aws ecs delete-cluster --cluster $cluster --region $REGION 2>/dev/null || true
    done
    echo "✓ ECS clusters processed"
else
    echo "No ECS clusters found"
fi

echo ""
echo "Step 9: Deleting Lambda Functions..."
echo "----------------------------------------"
FUNCTIONS=$(aws lambda list-functions --region $REGION --query 'Functions[].FunctionName' --output text 2>/dev/null)
if [ ! -z "$FUNCTIONS" ]; then
    for func in $FUNCTIONS; do
        echo "Deleting Lambda function: $func"
        aws lambda delete-function --function-name $func --region $REGION 2>/dev/null || true
    done
    echo "✓ Lambda functions deleted"
else
    echo "No Lambda functions found"
fi

echo ""
echo "Step 10: Deleting NAT Gateways..."
echo "----------------------------------------"
NAT_GWS=$(aws ec2 describe-nat-gateways --region $REGION --filter "Name=state,Values=available" --query 'NatGateways[].NatGatewayId' --output text 2>/dev/null)
if [ ! -z "$NAT_GWS" ]; then
    for nat in $NAT_GWS; do
        echo "Deleting NAT Gateway: $nat"
        aws ec2 delete-nat-gateway --nat-gateway-id $nat --region $REGION
    done
    echo "Waiting for NAT Gateways to delete..."
    sleep 30
    echo "✓ NAT Gateways deleted"
else
    echo "No NAT Gateways found"
fi

echo ""
echo "Step 11: Releasing Elastic IPs..."
echo "----------------------------------------"
EIPS=$(aws ec2 describe-addresses --region $REGION --query 'Addresses[?AssociationId==`null`].AllocationId' --output text 2>/dev/null)
if [ ! -z "$EIPS" ]; then
    for eip in $EIPS; do
        echo "Releasing EIP: $eip"
        aws ec2 release-address --allocation-id $eip --region $REGION 2>/dev/null || echo "Could not release $eip"
    done
    echo "✓ Elastic IPs released"
else
    echo "No unassociated Elastic IPs found"
fi

echo ""
echo "Step 12: Deleting Security Groups..."
echo "----------------------------------------"
echo "Waiting a bit for dependencies to clear..."
sleep 20

SECURITY_GROUPS=$(aws ec2 describe-security-groups --region $REGION --query 'SecurityGroups[?GroupName!=`default`].GroupId' --output text 2>/dev/null)
if [ ! -z "$SECURITY_GROUPS" ]; then
    for sg in $SECURITY_GROUPS; do
        echo "Deleting security group: $sg"
        aws ec2 delete-security-group --group-id $sg --region $REGION 2>/dev/null || echo "Could not delete $sg (may have dependencies)"
    done
    echo "✓ Security groups processed"
else
    echo "No custom security groups found"
fi

echo ""
echo "Step 13: Deleting VPCs and related resources..."
echo "----------------------------------------"
VPCS=$(aws ec2 describe-vpcs --region $REGION --filters "Name=isDefault,Values=false" --query 'Vpcs[].VpcId' --output text 2>/dev/null)
if [ ! -z "$VPCS" ]; then
    for vpc in $VPCS; do
        echo "Processing VPC: $vpc"
        
        # Delete Internet Gateways
        IGWS=$(aws ec2 describe-internet-gateways --region $REGION --filters "Name=attachment.vpc-id,Values=$vpc" --query 'InternetGateways[].InternetGatewayId' --output text)
        for igw in $IGWS; do
            echo "  - Detaching and deleting IGW: $igw"
            aws ec2 detach-internet-gateway --internet-gateway-id $igw --vpc-id $vpc --region $REGION 2>/dev/null || true
            aws ec2 delete-internet-gateway --internet-gateway-id $igw --region $REGION 2>/dev/null || true
        done
        
        # Delete Subnets
        SUBNETS=$(aws ec2 describe-subnets --region $REGION --filters "Name=vpc-id,Values=$vpc" --query 'Subnets[].SubnetId' --output text)
        for subnet in $SUBNETS; do
            echo "  - Deleting subnet: $subnet"
            aws ec2 delete-subnet --subnet-id $subnet --region $REGION 2>/dev/null || echo "    Could not delete $subnet"
        done
        
        # Delete Route Tables
        ROUTE_TABLES=$(aws ec2 describe-route-tables --region $REGION --filters "Name=vpc-id,Values=$vpc" --query 'RouteTables[?Associations[0].Main==`false`].RouteTableId' --output text)
        for rt in $ROUTE_TABLES; do
            echo "  - Deleting route table: $rt"
            aws ec2 delete-route-table --route-table-id $rt --region $REGION 2>/dev/null || echo "    Could not delete $rt"
        done
        
        # Delete VPC
        echo "  - Deleting VPC: $vpc"
        aws ec2 delete-vpc --vpc-id $vpc --region $REGION 2>/dev/null || echo "    Could not delete VPC $vpc (may still have dependencies)"
    done
    echo "✓ VPCs processed"
else
    echo "No custom VPCs found"
fi

echo ""
echo "Step 14: Deleting IAM Roles (created by CDK)..."
echo "----------------------------------------"
IAM_ROLES=$(aws iam list-roles --query 'Roles[?starts_with(RoleName, `AiDemoBuilderStack`) || starts_with(RoleName, `cdk-`)].RoleName' --output text 2>/dev/null)
if [ ! -z "$IAM_ROLES" ]; then
    for role in $IAM_ROLES; do
        echo "Processing IAM role: $role"
        
        # Detach managed policies
        ATTACHED_POLICIES=$(aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null)
        for policy in $ATTACHED_POLICIES; do
            echo "  - Detaching policy: $policy"
            aws iam detach-role-policy --role-name $role --policy-arn $policy 2>/dev/null || true
        done
        
        # Delete inline policies
        INLINE_POLICIES=$(aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null)
        for policy in $INLINE_POLICIES; do
            echo "  - Deleting inline policy: $policy"
            aws iam delete-role-policy --role-name $role --policy-name $policy 2>/dev/null || true
        done
        
        # Delete instance profiles
        INSTANCE_PROFILES=$(aws iam list-instance-profiles-for-role --role-name $role --query 'InstanceProfiles[].InstanceProfileName' --output text 2>/dev/null)
        for profile in $INSTANCE_PROFILES; do
            echo "  - Removing role from instance profile: $profile"
            aws iam remove-role-from-instance-profile --instance-profile-name $profile --role-name $role 2>/dev/null || true
            echo "  - Deleting instance profile: $profile"
            aws iam delete-instance-profile --instance-profile-name $profile 2>/dev/null || true
        done
        
        # Delete the role
        echo "  - Deleting role: $role"
        aws iam delete-role --role-name $role 2>/dev/null || echo "    Could not delete role $role"
    done
    echo "✓ IAM roles processed"
else
    echo "No CDK-related IAM roles found"
fi

echo ""
echo "Step 15: Final CloudFormation Cleanup..."
echo "----------------------------------------"
# Try to delete any remaining stacks including CDKToolkit
ALL_STACKS=$(aws cloudformation list-stacks --region $REGION --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE UPDATE_ROLLBACK_COMPLETE --query 'StackSummaries[].StackName' --output text)
if [ ! -z "$ALL_STACKS" ]; then
    for stack in $ALL_STACKS; do
        echo "Attempting to delete stack: $stack"
        aws cloudformation delete-stack --stack-name $stack --region $REGION 2>/dev/null || echo "Could not delete $stack"
    done
fi

echo ""
echo "========================================"
echo "Cleanup Complete!"
echo "========================================"
echo ""
echo "Note: Some resources may take additional time to fully delete."
echo "You may need to:"
echo "  1. Wait a few minutes and run this script again"
echo "  2. Check the AWS Console for any remaining resources"
echo "  3. Manually delete any resources that couldn't be removed"
echo ""
echo "After cleanup, you can try deploying your CDK stack again with:"
echo "  cdk deploy"
echo ""