# Part 3: Edge-Cloud Hybrid with AWS IoT Greengrass

Face detection runs at the edge on an EC2 instance hosting AWS IoT Greengrass Core. Face recognition runs in a cloud Lambda. The edge component handles no-face images locally without a cloud round-trip (bonus).

## Architecture

```
Client publishes base64 image via MQTT to AWS IoT Core
  │
  ▼
Greengrass Edge (EC2 with Greengrass Core v2)
fd_component.py  ─  subscribes to: clients/{STUDENT_ID}-IoTThing
  │
  ├── Face detected → crop → SQS req-queue
  │                               │
  │                      face-recognition Lambda (SQS trigger)
  │                               │ FaceNet → name
  │                      SQS resp-queue  { request_id, result: <name> }
  │
  └── No face → SQS resp-queue  { request_id, result: "No-Face" }
               (resolved at edge — no Lambda invocation)
```

## Files

| File | Purpose |
|------|---------|
| `edge/fd_component.py` | Greengrass component: MTCNN detection, Greengrass IPC subscriber |
| `cloud/fr_lambda.py` | FaceNet recognition Lambda (SQS-triggered) |
| `cloud/Dockerfile` | Docker image for face-recognition Lambda |
| `cloud/requirements.txt` | Lambda dependencies |

## Edge Component Setup

### Prerequisites

- EC2 instance with AWS IoT Greengrass Core v2 installed and running
- IoT Thing created and associated with the Greengrass core device
- `facenet-pytorch` and `Pillow` installed in the Python environment used by Greengrass

### Environment Variables (set in Greengrass component recipe)

```yaml
STUDENT_ID: your-id
AWS_ACCOUNT_ID: your-aws-account-id
```

### Greengrass Component Recipe (key settings)

```yaml
ComponentName: com.example.FaceDetection
ComponentVersion: 1.0.0
ComponentConfiguration:
  DefaultConfiguration:
    STUDENT_ID: ""
    AWS_ACCOUNT_ID: ""
Manifests:
  - Lifecycle:
      Run: "python3 {artifacts:path}/fd_component.py"
    Artifacts:
      - URI: "s3://your-bucket/fd_component.py"
  - ComponentIpcAccessControl:
      aws.greengrass.ipc.mqttproxy:
        accessControl:
          aws.greengrass#SubscribeToIoTCore:
            policyDescription: "Subscribe to face detection topic"
            resources:
              - "clients/{STUDENT_ID}-IoTThing"
```

## Cloud Lambda Setup

### Prerequisites

- Docker
- AWS CLI with ECR, Lambda, SQS permissions
- `resnetV1_video_weights.pt` in `cloud/` directory (not in repo)

### Deploy

```bash
cd cloud
export STUDENT_ID=your-id
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1

# Build and push
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

docker build --platform linux/amd64 -t face-recognition-edge .
docker tag face-recognition-edge:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/face-recognition-edge:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/face-recognition-edge:latest

# Create Lambda
aws lambda create-function \
  --function-name face-recognition \
  --package-type Image \
  --code ImageUri=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/face-recognition-edge:latest \
  --role <lambda-role-arn> \
  --timeout 60 \
  --memory-size 3008 \
  --environment Variables="{RESPONSE_QUEUE_URL=https://sqs.${AWS_REGION}.amazonaws.com/${AWS_ACCOUNT_ID}/${STUDENT_ID}-resp-queue}"

# Add SQS trigger
aws lambda create-event-source-mapping \
  --function-name face-recognition \
  --event-source-arn arn:aws:sqs:${AWS_REGION}:${AWS_ACCOUNT_ID}:${STUDENT_ID}-req-queue \
  --batch-size 1
```

## Performance

- Average latency: < 1.5 s per request (actual: ~0.776 s)
- Accuracy: 100% (100/100 correct)
- Bonus: No-face responses resolved at the edge without Lambda invocation
