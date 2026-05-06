# Part 2: Serverless Face Recognition with AWS Lambda

Two Lambda functions deployed as Docker containers handle face detection and recognition independently, connected by SQS queues.

## Architecture

```
Client
  │  POST JSON: { request_id, filename, content (base64 image) }
  ▼
face-detection Lambda  (Function URL, public)
  │  MTCNN detects and crops face
  │  { request_id, filename, face_image (base64 crop) }
  ▼
SQS req-queue  (visibility timeout: 70 s)
  │  triggers face-recognition Lambda (batch size: 1)
  ▼
face-recognition Lambda
  │  FaceNet embedding vs. resnetV1_video_weights.pt
  │  { request_id, result: <name> }
  ▼
SQS resp-queue  ←  caller polls for result
```

## Files

| File | Purpose |
|------|---------|
| `face-detection/fd_lambda.py` | MTCNN detection, sends cropped face to req-queue |
| `face-recognition/fr_lambda.py` | FaceNet recognition, SQS-triggered |
| `Dockerfile` | Single image for both functions (CMD overridden per function) |
| `requirements.txt` | Python dependencies |
| `deploy.sh` | Full end-to-end deployment to ECR + Lambda + SQS |

## Deployment

### Prerequisites

- Docker
- AWS CLI with ECR, Lambda, SQS, IAM permissions
- `resnetV1_video_weights.pt` in this directory (not in repo — add before building)

### Environment

```bash
export STUDENT_ID=your-id
```

### Deploy

```bash
chmod +x deploy.sh
./deploy.sh
```

The script creates:
1. ECR repository + Docker build + push
2. SQS req-queue (visibility timeout 70 s) and resp-queue
3. IAM execution role for Lambda
4. `face-detection` Lambda with a public Function URL
5. `face-recognition` Lambda with SQS trigger (batch size 1)

### Docker Image

One image serves both functions. `face-recognition` overrides CMD at deploy time:

```bash
# face-detection (default)
CMD ["fd_lambda.handler"]

# face-recognition (overridden in Lambda config)
--image-config Command="fr_lambda.handler"
```

## Lambda Configuration

| Setting | Value |
|---------|-------|
| Memory | 3,008 MB |
| Timeout | 60 s |
| Platform | linux/amd64 |
| Python | 3.9 |
| PyTorch | 2.0.1 (CPU) |

## Performance

- Average latency: < 3.0 s per request (actual: ~1.78 s)
- Accuracy: 100% (100/100 correct)
- 100 concurrent requests handled
