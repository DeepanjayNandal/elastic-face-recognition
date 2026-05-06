import boto3
import sys
import os
import time
import requests
import torch
from PIL import Image
from facenet_pytorch import MTCNN, InceptionResnetV1

student_id = os.environ.get("STUDENT_ID", "your-id")
region = "us-east-1"
s3 = boto3.client("s3", region_name=region)
sqs = boto3.client("sqs", region_name=region)
ec2 = boto3.client("ec2", region_name=region)
request_queue_url = sqs.get_queue_url(QueueName=f"{student_id}-req-queue")["QueueUrl"]
response_queue_url = sqs.get_queue_url(QueueName=f"{student_id}-resp-queue")["QueueUrl"]
input_bucket = f"{student_id}-in-bucket"
output_bucket = f"{student_id}-out-bucket"
sys.path.insert(0, "/home/ec2-user")

mtcnn = MTCNN(image_size=240, margin=0, min_face_size=20)
resnet = InceptionResnetV1(pretrained="vggface2").eval()

def face_recognition(img_path):
    img = Image.open(img_path)
    face, prob = mtcnn(img, return_prob=True)
    emb = resnet(face.unsqueeze(0)).detach()
    saved_data = torch.load("/home/ec2-user/data.pt")
    embedding_list = saved_data[0]
    name_list = saved_data[1]
    dist_list = []
    for idx, emb_db in enumerate(embedding_list):
        dist = torch.dist(emb, emb_db).item()
        dist_list.append(dist)
    idx_min = dist_list.index(min(dist_list))
    return name_list[idx_min]

def process_request():
    resp = sqs.receive_message(
        QueueUrl=request_queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=5
    )
    if "Messages" not in resp:
        return False
    msg = resp["Messages"][0]
    filename = msg["Body"]
    receipt = msg["ReceiptHandle"]
    local_path = f"/tmp/{filename}"
    s3.download_file(input_bucket, filename, local_path)
    result = face_recognition(local_path)
    image_name = filename.replace(".jpg", "")
    s3.put_object(Bucket=output_bucket, Key=image_name, Body=result)
    sqs.send_message(QueueUrl=response_queue_url, MessageBody=f"{image_name}:{result}")
    sqs.delete_message(QueueUrl=request_queue_url, ReceiptHandle=receipt)
    os.remove(local_path)
    return True

def check_queue_empty():
    attrs = sqs.get_queue_attributes(
        QueueUrl=request_queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
    )
    visible = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
    inflight = int(attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0))
    return (visible + inflight) == 0

def shutdown_instance():
    try:
        token_response = requests.put(
            'http://169.254.169.254/latest/api/token',
            headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'},
            timeout=2
        )
        token = token_response.text

        instance_id_response = requests.get(
            'http://169.254.169.254/latest/meta-data/instance-id',
            headers={'X-aws-ec2-metadata-token': token},
            timeout=2
        )
        instance_id = instance_id_response.text.strip()

        if instance_id:
            ec2.stop_instances(InstanceIds=[instance_id])
    except Exception:
        pass

while True:
    if process_request():
        if check_queue_empty():
            shutdown_instance()
            break
    else:
        if check_queue_empty():
            shutdown_instance()
            break
        time.sleep(2)
