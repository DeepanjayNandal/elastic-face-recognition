# Elastic Face Recognition System

![Python](https://img.shields.io/badge/Python-3.9-3776AB?logo=python&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-EC2%20·%20Lambda%20·%20SQS%20·%20S3%20·%20Greengrass-FF9900?logo=amazonaws&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-linux%2Famd64-2496ED?logo=docker&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-2.0.1-EE4C2C?logo=pytorch&logoColor=white)

End-to-end face recognition system implemented across three AWS architectures. Built for **CSE 546 Cloud Computing** at Arizona State University (Fall 2025).

## Results

| Part | Architecture | Avg Latency | Accuracy |
|------|-------------|-------------|----------|
| 1 — IaaS Autoscaling | Custom EC2 autoscaler | **< 1.2 s** | **100/100** |
| 2 — Serverless Lambda | AWS Lambda + ECR | **~1.78 s** | **100/100** |
| 3 — Edge-Cloud Hybrid | IoT Greengrass + Lambda | **~0.776 s** | **100/100** |

All three parts graded at **100/100**.

## How It Works

Each part solves the same problem — identify a person from a face image — using a different AWS architecture:

1. **MTCNN** detects and crops the face from the input image
2. **FaceNet (InceptionResnetV1)** converts the crop to a 512-d embedding
3. Nearest-neighbour search against pre-computed embeddings returns the person's name

---

## Part 1 — IaaS Auto-Scaling

Custom autoscaler monitors SQS queue depth and starts/stops EC2 workers. No AWS Auto Scaling Groups.

```
┌─────────────┐   POST /    ┌──────────────────────┐
│   Client    │ ──────────► │  Web Tier (Flask)    │
└─────────────┘             │  EC2 · port 8000     │
                            └──────────┬───────────┘
                                       │ upload + enqueue
                            ┌──────────▼───────────┐
                            │  S3 in-bucket         │
                            │  SQS req-queue        │◄── controller.py
                            └──────────┬───────────┘    (depth poll 2s,
                                       │                 start/stop EC2)
                ┌──────────────────────▼─────────────────────────┐
                │              App Tier  (EC2 × 1–15)            │
                │   MTCNN detect → FaceNet identify               │
                │   result → S3 out-bucket + SQS resp-queue      │
                │   self-terminates when queue drains             │
                └─────────────────────────────────────────────────┘
```

**Scale:** 0 → 15 instances on demand · Scale-in < 2 s after queue drains · 100 concurrent requests

---

## Part 2 — Serverless Lambda

Two Lambda functions in one Docker image, connected by SQS. Zero infrastructure to manage.

```
┌─────────────┐  POST JSON  ┌──────────────────────────────┐
│   Client    │ ──────────► │  face-detection Lambda        │
└─────────────┘             │  Function URL (public)        │
                            │  MTCNN → crop → base64        │
                            └──────────────┬───────────────┘
                                           │
                                ┌──────────▼──────────┐
                                │   SQS req-queue      │
                                │   visibility: 70 s   │
                                └──────────┬──────────┘
                                           │ trigger (batch=1)
                            ┌──────────────▼──────────────┐
                            │  face-recognition Lambda     │
                            │  FaceNet → nearest match     │
                            └──────────────┬──────────────┘
                                           │
                                ┌──────────▼──────────┐
                                │   SQS resp-queue     │
                                └─────────────────────┘
```

**Deploy:** single Docker image pushed to ECR · CMD overridden per function · `./deploy.sh` automates all 11 steps

---

## Part 3 — Edge-Cloud Hybrid (IoT Greengrass)

Face detection runs at the edge — no cloud round-trip for MTCNN. No-face handled entirely at edge without invoking Lambda.

```
┌─────────────┐  MQTT publish  ┌────────────────────────┐
│   Client    │ ─────────────► │   AWS IoT Core         │
└─────────────┘                └──────────┬─────────────┘
                                          │
                               ┌──────────▼─────────────┐
                               │  Greengrass Edge (EC2) │
                               │  fd_component.py        │
                               │  MTCNN runs at edge     │
                               └────┬──────────┬────────┘
                          face      │           │  no face
                          found     │           │
                ┌──────────▼──────┐            ┌───────▼──────────────┐
                │  SQS req-queue  │            │  SQS resp-queue      │
                └──────────┬──────┘            │  result: "No-Face"   │
                           │                   │  (edge only)         │
              ┌────────────▼──────────┐        └──────────────────────┘
              │  face-recognition     │
              │  Lambda (FaceNet)     │
              └────────────┬──────────┘
                           │
                ┌──────────▼──────┐
                │  SQS resp-queue │
                └─────────────────┘
```

**Bonus:** No-face images short-circuit at edge — Lambda never invoked.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Face detection | MTCNN — facenet-pytorch |
| Face recognition | InceptionResnetV1 — pretrained VGGFace2 |
| IaaS compute | EC2 (web tier + app tier × 15) |
| Serverless compute | AWS Lambda — Docker image, 3 GB RAM |
| Container registry | Amazon ECR |
| Edge runtime | AWS IoT Greengrass v2, Greengrass IPC |
| Messaging | SQS (request/response queues), MQTT (IoT Core) |
| Storage | Amazon S3 |
| ML runtime | PyTorch 2.0.1 (CPU), facenet-pytorch 2.5.3 |
| Containerization | Docker (linux/amd64), Python 3.9-slim |

## Repository Structure

```
elastic-face-recognition/
├── part1-iaas-autoscaling/
│   ├── web-tier/          # Flask server + custom autoscaler
│   └── app-tier/          # EC2 worker: MTCNN + FaceNet + self-terminate
├── part2-serverless-lambda/
│   ├── face-detection/    # Lambda: MTCNN → SQS
│   ├── face-recognition/  # Lambda: FaceNet ← SQS
│   ├── Dockerfile         # Single image, CMD overridden per function
│   └── deploy.sh          # 11-step automated deployment
└── part3-edge-cloud-greengrass/
    ├── edge/              # Greengrass component: MTCNN at edge
    └── cloud/             # Lambda: FaceNet in cloud
```

## Prerequisites

- Python 3.9+, AWS CLI, Docker
- AWS account (us-east-1)
- `STUDENT_ID` env var set to your resource-naming identifier
- `resnetV1_video_weights.pt` model weights (not included — add before Docker build)

---

*CSE 546 Cloud Computing · Arizona State University · Fall 2025*
