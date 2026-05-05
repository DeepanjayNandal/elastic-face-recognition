import boto3
import os
import time

student_id = os.environ.get("STUDENT_ID", "your-id")
region = "us-east-1"
ec2 = boto3.client("ec2", region_name=region)
sqs = boto3.client("sqs", region_name=region)
request_queue_url = sqs.get_queue_url(QueueName=f"{student_id}-req-queue")["QueueUrl"]

def get_running_count():
    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["app-tier-instance-*"]},
            {"Name": "instance-state-name", "Values": ["running", "pending"]},
        ]
    )
    return sum(len(r["Instances"]) for r in resp["Reservations"])

def get_stopped_instances():
    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["app-tier-instance-*"]},
            {"Name": "instance-state-name", "Values": ["stopped"]},
        ]
    )
    stopped = []
    for r in resp["Reservations"]:
        for i in r["Instances"]:
            stopped.append(i["InstanceId"])
    return stopped

def get_running_instances():
    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["app-tier-instance-*"]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    running = []
    for r in resp["Reservations"]:
        for i in r["Instances"]:
            running.append(i["InstanceId"])
    return running

def get_queue_size():
    attrs = sqs.get_queue_attributes(
        QueueUrl=request_queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )
    visible = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
    inflight = int(attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0))
    return visible + inflight

def scale_out(needed):
    running = get_running_count()
    to_start = min(needed - running, 15 - running)
    if to_start <= 0:
        return
    stopped = get_stopped_instances()
    for i in range(min(to_start, len(stopped))):
        ec2.start_instances(InstanceIds=[stopped[i]])

def scale_in():
    running = get_running_instances()
    if running:
        ec2.stop_instances(InstanceIds=running)

while True:
    try:
        queue_size = get_queue_size()
        running = get_running_count()
        needed = min(queue_size, 15)
        if needed > running:
            scale_out(needed)
        elif queue_size == 0 and running > 0:
            scale_in()
        time.sleep(2)
    except:
        time.sleep(5)
