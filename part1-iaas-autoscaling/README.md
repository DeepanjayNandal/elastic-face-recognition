# Part 1: IaaS Auto-Scaling

Custom auto-scaling face recognition on EC2. A Python controller monitors SQS queue depth and starts/stops app-tier EC2 instances manually — no AWS Auto Scaling Groups.

## Architecture

**Web Tier** (`web-tier/server.py`)
- Flask server, EC2, port 8000
- Accepts `POST /` with `inputFile` (JPEG image)
- Uploads image to S3 input bucket, sends filename to SQS req-queue
- Polls SQS resp-queue (120 s timeout), returns `<filename>:<name>`

**Custom Autoscaler** (`web-tier/controller.py`)
- Runs on the web-tier EC2 alongside Flask
- Polls SQS req-queue depth every 2 seconds (visible + in-flight messages)
- Scale out: starts stopped EC2 instances tagged `app-tier-instance-*`, max 15
- Scale in: stops all running app-tier instances when queue reaches zero

**App Tier** (`app-tier/backend.py`)
- Up to 15 parallel EC2 workers
- Pulls image filename from SQS, downloads from S3
- Runs MTCNN detection + FaceNet recognition against `data.pt` embeddings
- Writes result to S3 output bucket and SQS resp-queue as `<filename>:<name>`
- Self-terminates via EC2 IMDS when queue drains

## AWS Resources

| Resource | Name |
|----------|------|
| S3 input bucket | `{STUDENT_ID}-in-bucket` |
| S3 output bucket | `{STUDENT_ID}-out-bucket` |
| SQS request queue | `{STUDENT_ID}-req-queue` |
| SQS response queue | `{STUDENT_ID}-resp-queue` |
| EC2 app-tier instances | Tagged `app-tier-instance-*` |

## Setup

### Prerequisites

- EC2 instances pre-configured with PyTorch, facenet-pytorch
- `data.pt` model embeddings at `/home/ec2-user/data.pt` on each app-tier instance
- IAM role on EC2 with S3 and SQS full access
- S3 buckets and SQS queues created

### Environment

```bash
export STUDENT_ID=your-id
```

### Web Tier

```bash
cd web-tier
pip install flask boto3
python controller.py &   # autoscaler runs in background
python server.py         # Flask on port 8000
```

### App Tier (on each EC2 instance at startup)

```bash
cd app-tier
pip install boto3 torch facenet-pytorch Pillow requests
python backend.py        # exits automatically when queue is empty
```

## Performance

- Average latency: < 1.2 s (100 concurrent requests)
- Accuracy: 100% (100/100 correct)
- Max scale: 15 EC2 instances
- Scale-in delay: < 2 s after queue drains
