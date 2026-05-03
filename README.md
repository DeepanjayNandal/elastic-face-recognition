# Elastic Face Recognition System

A three-part cloud computing project implementing face recognition at scale using AWS, built for **CSE 546 Cloud Computing** at Arizona State University (Fall 2025).

## System Overview

Clients send images to the system. The system detects and identifies the face in each image and returns the person's name. Three implementations explore progressively more sophisticated cloud architectures.

## Architecture Variants

### Part 1: IaaS Auto-Scaling (EC2)

```
Client ──POST /──► Web Tier (Flask, EC2, port 8000)
                        │ upload image
                   S3 in-bucket
                   SQS req-queue ◄── controller.py (autoscaler, 2s poll)
                        │                 │ start/stop EC2 instances
                   App Tier (EC2 × 1–15) ◄┘
                   MTCNN + FaceNet
                        │
                   SQS resp-queue ──► Web Tier ──► Client
                   S3 out-bucket
```

### Part 2: Serverless Lambda

```
Client ──POST──► face-detection Lambda (Function URL)
                      │ MTCNN crops face
                 SQS req-queue
                      │ (SQS trigger, batch size 1)
                 face-recognition Lambda
                      │ FaceNet → name
                 SQS resp-queue
```

### Part 3: Edge-Cloud Hybrid (IoT Greengrass)

```
Client ──MQTT──► AWS IoT Core ──► Greengrass Edge (EC2)
                                       fd_component.py
                                       MTCNN at edge
                                       ├── face found → SQS req-queue → Lambda → resp-queue
                                       └── no face   → SQS resp-queue  (edge only, no Lambda)
```

## Performance

| Part | Architecture | Avg Latency | Accuracy | Scale |
|------|-------------|-------------|----------|-------|
| 1 | IaaS + custom autoscaler | < 1.2 s | 100% | 1–15 EC2 instances |
| 2 | Serverless Lambda | < 3.0 s (actual ~1.78 s) | 100% | Automatic |
| 3 | Edge-cloud + Greengrass | < 1.5 s (actual ~0.776 s) | 100% | Edge + Lambda |

All three parts received full marks (100/100) in graded evaluation.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Face detection | MTCNN (facenet-pytorch) |
| Face recognition | InceptionResnetV1 — pretrained VGGFace2 |
| Web tier | Flask, EC2 |
| Auto-scaling | Custom Python controller, SQS-depth-driven |
| Serverless compute | AWS Lambda (Docker image, 3 GB RAM) |
| Container registry | Amazon ECR |
| Edge runtime | AWS IoT Greengrass v2, Greengrass IPC |
| Messaging | SQS (request/response), MQTT (IoT Core) |
| Storage | Amazon S3 |
| ML runtime | PyTorch 2.0.1 (CPU), facenet-pytorch 2.5.3 |

## Repository Structure

```
elastic-face-recognition/
├── part1-iaas-autoscaling/      # Custom EC2 auto-scaling
│   ├── web-tier/                # Flask server + autoscaler controller
│   └── app-tier/                # EC2 worker: MTCNN + FaceNet
├── part2-serverless-lambda/     # Fully serverless face pipeline
│   ├── face-detection/          # Lambda: MTCNN → SQS
│   ├── face-recognition/        # Lambda: FaceNet ← SQS
│   ├── Dockerfile               # Single image for both functions
│   ├── requirements.txt
│   └── deploy.sh                # End-to-end AWS deployment script
└── part3-edge-cloud-greengrass/ # Edge detection + cloud recognition
    ├── edge/                    # Greengrass component (MTCNN at edge)
    └── cloud/                   # Lambda (FaceNet in cloud)
```

## Prerequisites

- Python 3.9+
- AWS CLI configured (`us-east-1`)
- Docker (Parts 2 and 3)
- `STUDENT_ID` environment variable set to your resource-naming identifier
- `resnetV1_video_weights.pt` model weights (not included — add to image at build time)

## Quick Start

- [Part 1 — IaaS Autoscaling](part1-iaas-autoscaling/README.md)
- [Part 2 — Serverless Lambda](part2-serverless-lambda/README.md)
- [Part 3 — Edge-Cloud Greengrass](part3-edge-cloud-greengrass/README.md)

---

*CSE 546 Cloud Computing, Arizona State University, Fall 2025.*
