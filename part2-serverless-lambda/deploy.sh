#!/bin/bash

# AWS Lambda Face Recognition Project - Deployment Script
# CSE 546 Cloud Computing

set -e

echo "=========================================="
echo "AWS Lambda Face Recognition Deployment"
echo "=========================================="
echo ""

# Student ID used for AWS resource naming
ASU_ID="${STUDENT_ID:-}"
if [ -z "$ASU_ID" ]; then
    read -p "Enter your student ID (used for AWS resource naming): " ASU_ID
fi

AWS_REGION="${AWS_REGION:-us-east-1}"

echo "Configuration:"
echo "  Student ID : ${ASU_ID}"
echo "  Region     : ${AWS_REGION}"
echo ""

# [1/11] Get AWS Account ID
echo "[1/11] Getting AWS Account ID..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "  Account ID: ${AWS_ACCOUNT_ID}"
echo ""

# [2/11] Create ECR Repository
echo "[2/11] Creating ECR Repository..."
if aws ecr describe-repositories --repository-names lambda-face-recognition --region ${AWS_REGION} 2>/dev/null; then
    echo "  Repository already exists, skipping..."
else
    aws ecr create-repository \
        --repository-name lambda-face-recognition \
        --region ${AWS_REGION}
    echo "  Repository created"
fi
echo ""

# [3/11] Clean up old ECR images
echo "[3/11] Cleaning up old ECR images..."
aws ecr batch-delete-image \
    --repository-name lambda-face-recognition \
    --region ${AWS_REGION} \
    --image-ids imageTag=latest 2>/dev/null && echo "  Old 'latest' tag deleted" || echo "  No 'latest' tag found"
echo ""

# [4/11] Docker Login
echo "[4/11] Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
echo "  Logged in"
echo ""

# [5/11] Build Docker Image
echo "[5/11] Building Docker image (5-15 minutes)..."
echo "      Building for linux/amd64 (AWS Lambda requirement)"
export DOCKER_BUILDKIT=0
docker build --platform linux/amd64 -t lambda-face-recognition .
echo ""
echo "  Image built"
echo ""

# [6/11] Tag and Push
echo "[6/11] Pushing image to ECR..."
docker tag lambda-face-recognition:latest \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/lambda-face-recognition:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/lambda-face-recognition:latest
echo "  Image pushed"
echo ""

# [7/11] Create SQS Queues
echo "[7/11] Creating SQS Queues..."

if aws sqs get-queue-url --queue-name "${ASU_ID}-req-queue" --region ${AWS_REGION} 2>/dev/null; then
    REQ_QUEUE_URL=$(aws sqs get-queue-url --queue-name "${ASU_ID}-req-queue" --region ${AWS_REGION} --query QueueUrl --output text)
    echo "  Request queue already exists"
else
    REQ_QUEUE_URL=$(aws sqs create-queue \
        --queue-name "${ASU_ID}-req-queue" \
        --region ${AWS_REGION} \
        --query QueueUrl --output text)
    echo "  Request queue created"
fi

if aws sqs get-queue-url --queue-name "${ASU_ID}-resp-queue" --region ${AWS_REGION} 2>/dev/null; then
    RESP_QUEUE_URL=$(aws sqs get-queue-url --queue-name "${ASU_ID}-resp-queue" --region ${AWS_REGION} --query QueueUrl --output text)
    echo "  Response queue already exists"
else
    RESP_QUEUE_URL=$(aws sqs create-queue \
        --queue-name "${ASU_ID}-resp-queue" \
        --region ${AWS_REGION} \
        --query QueueUrl --output text)
    echo "  Response queue created"
fi

aws sqs purge-queue --queue-url ${REQ_QUEUE_URL} 2>/dev/null || true
aws sqs purge-queue --queue-url ${RESP_QUEUE_URL} 2>/dev/null || true
echo "  Queues purged"

aws sqs set-queue-attributes \
    --queue-url ${REQ_QUEUE_URL} \
    --attributes VisibilityTimeout=70 \
    --region ${AWS_REGION}
echo "  Request queue visibility timeout set to 70 s"
echo ""

# [8/11] Create IAM Role
echo "[8/11] Creating IAM Role for Lambda..."
if aws iam get-role --role-name lambda-face-recognition-role 2>/dev/null; then
    echo "  Role already exists"
    LAMBDA_ROLE_ARN=$(aws iam get-role --role-name lambda-face-recognition-role --query Role.Arn --output text)
else
    cat > /tmp/trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF
    aws iam create-role \
        --role-name lambda-face-recognition-role \
        --assume-role-policy-document file:///tmp/trust-policy.json

    aws iam attach-role-policy \
        --role-name lambda-face-recognition-role \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole

    aws iam attach-role-policy \
        --role-name lambda-face-recognition-role \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole

    aws iam attach-role-policy \
        --role-name lambda-face-recognition-role \
        --policy-arn arn:aws:iam::aws:policy/AmazonSQSFullAccess

    LAMBDA_ROLE_ARN=$(aws iam get-role --role-name lambda-face-recognition-role --query Role.Arn --output text)
    echo "  Role created, waiting 10 s for propagation..."
    sleep 10
fi
echo ""

# [9/11] Deploy face-detection Lambda
echo "[9/11] Deploying face-detection Lambda..."
if aws lambda get-function --function-name face-detection --region ${AWS_REGION} 2>/dev/null; then
    echo "  Updating existing function..."
    aws lambda update-function-code \
        --function-name face-detection \
        --image-uri ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/lambda-face-recognition:latest \
        --region ${AWS_REGION}
    sleep 5
    aws lambda update-function-configuration \
        --function-name face-detection \
        --timeout 60 \
        --memory-size 3008 \
        --environment Variables="{REQUEST_QUEUE_URL=${REQ_QUEUE_URL},ASU_ID=${ASU_ID}}" \
        --region ${AWS_REGION}
    echo "  Function updated"
else
    aws lambda create-function \
        --function-name face-detection \
        --package-type Image \
        --code ImageUri=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/lambda-face-recognition:latest \
        --role ${LAMBDA_ROLE_ARN} \
        --timeout 60 \
        --memory-size 3008 \
        --environment Variables="{REQUEST_QUEUE_URL=${REQ_QUEUE_URL},ASU_ID=${ASU_ID}}" \
        --region ${AWS_REGION}
    echo "  Function created"
fi

echo "  Waiting for function to be ready..."
aws lambda wait function-active --function-name face-detection --region ${AWS_REGION}
echo ""

# [10/11] Create Function URL
echo "[10/11] Creating Function URL..."
if aws lambda get-function-url-config --function-name face-detection --region ${AWS_REGION} 2>/dev/null; then
    FD_FUNCTION_URL=$(aws lambda get-function-url-config --function-name face-detection --region ${AWS_REGION} --query FunctionUrl --output text)
    echo "  Function URL already exists"
else
    FD_FUNCTION_URL=$(aws lambda create-function-url-config \
        --function-name face-detection \
        --auth-type NONE \
        --region ${AWS_REGION} \
        --query FunctionUrl --output text)

    aws lambda add-permission \
        --function-name face-detection \
        --statement-id FunctionURLAllowPublicAccess \
        --action lambda:InvokeFunctionUrl \
        --principal "*" \
        --function-url-auth-type NONE \
        --region ${AWS_REGION} 2>&1 || true

    echo "  Function URL created"
fi
echo "  URL: ${FD_FUNCTION_URL}"
echo ""

# [11/11] Deploy face-recognition Lambda
echo "[11/11] Deploying face-recognition Lambda..."
if aws lambda get-function --function-name face-recognition --region ${AWS_REGION} 2>/dev/null; then
    echo "  Updating existing function..."
    aws lambda update-function-code \
        --function-name face-recognition \
        --image-uri ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/lambda-face-recognition:latest \
        --region ${AWS_REGION}
    sleep 5
    aws lambda update-function-configuration \
        --function-name face-recognition \
        --timeout 60 \
        --memory-size 3008 \
        --environment Variables="{RESPONSE_QUEUE_URL=${RESP_QUEUE_URL},ASU_ID=${ASU_ID}}" \
        --image-config Command="fr_lambda.handler" \
        --region ${AWS_REGION}
    echo "  Function updated"
else
    aws lambda create-function \
        --function-name face-recognition \
        --package-type Image \
        --code ImageUri=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/lambda-face-recognition:latest \
        --role ${LAMBDA_ROLE_ARN} \
        --timeout 60 \
        --memory-size 3008 \
        --environment Variables="{RESPONSE_QUEUE_URL=${RESP_QUEUE_URL},ASU_ID=${ASU_ID}}" \
        --image-config Command="fr_lambda.handler" \
        --region ${AWS_REGION}
    echo "  Function created"
fi

echo "  Waiting for function to be ready..."
aws lambda wait function-active --function-name face-recognition --region ${AWS_REGION}

REQ_QUEUE_ARN=$(aws sqs get-queue-attributes \
    --queue-url ${REQ_QUEUE_URL} \
    --attribute-names QueueArn \
    --region ${AWS_REGION} \
    --query Attributes.QueueArn --output text)

EXISTING_MAPPING=$(aws lambda list-event-source-mappings \
    --function-name face-recognition \
    --event-source-arn ${REQ_QUEUE_ARN} \
    --region ${AWS_REGION} \
    --query 'EventSourceMappings[0].UUID' --output text 2>/dev/null || echo "None")

if [ "$EXISTING_MAPPING" == "None" ]; then
    aws lambda create-event-source-mapping \
        --function-name face-recognition \
        --event-source-arn ${REQ_QUEUE_ARN} \
        --batch-size 1 \
        --region ${AWS_REGION}
    echo "  SQS trigger created"
else
    echo "  SQS trigger already exists"
fi
echo ""

echo "=========================================="
echo "Deployment Complete"
echo "=========================================="
echo ""
echo "Resources:"
echo "  Face Detection URL : ${FD_FUNCTION_URL}"
echo "  Request Queue      : ${REQ_QUEUE_URL}"
echo "  Response Queue     : ${RESP_QUEUE_URL}"
echo ""
echo "Before testing, purge SQS queues:"
echo "  aws sqs purge-queue --queue-url ${REQ_QUEUE_URL}"
echo "  aws sqs purge-queue --queue-url ${RESP_QUEUE_URL}"
echo "=========================================="
