import time
import json
import base64
import io
import os
import traceback
import boto3
import awsiot.greengrasscoreipc
import awsiot.greengrasscoreipc.client as client
from awsiot.greengrasscoreipc.model import SubscribeToIoTCoreRequest, QOS, IoTCoreMessage
from PIL import Image
from facenet_pytorch import MTCNN

STUDENT_ID = os.environ.get("STUDENT_ID", "your-student-id")
TARGET_ACCOUNT = os.environ.get("AWS_ACCOUNT_ID", "your-account-id")

REGION = "us-east-1"
q_req = f"https://sqs.{REGION}.amazonaws.com/{TARGET_ACCOUNT}/{STUDENT_ID}-req-queue"
q_resp = f"https://sqs.{REGION}.amazonaws.com/{TARGET_ACCOUNT}/{STUDENT_ID}-resp-queue"
topic = f"clients/{STUDENT_ID}-IoTThing"

sqs = boto3.client("sqs", region_name=REGION)

detector = MTCNN(keep_all=True, device='cpu')

def send_sqs(url, payload):
    try:
        sqs.send_message(QueueUrl=url, MessageBody=json.dumps(payload))
        print(f"Sent to {url.split('/')[-1]}")
    except Exception as e:
        print(f"SQS Error: {e}")

class Handler(client.SubscribeToIoTCoreStreamHandler):
    def __init__(self): super().__init__()

    def on_stream_event(self, event: IoTCoreMessage):
        try:
            msg = str(event.message.payload, "utf-8")
            data = json.loads(msg)
            rid = data.get("request_id")
            fname = data.get("filename")
            encoded = data.get("encoded")

            if not encoded: return

            print(f"Processing: {rid}")
            img = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
            boxes, _ = detector.detect(img)

            if boxes is None or len(boxes) == 0:
                print("Result: No Face")
                send_sqs(q_resp, {"request_id": rid, "result": "No-Face"})

            else:
                print("Result: Face Found")
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box)
                    crop = img.crop((x1, y1, x2, y2))

                    buf = io.BytesIO()
                    crop.save(buf, format="JPEG")
                    b64 = base64.b64encode(buf.getvalue()).decode()

                    req = {
                        "request_id": rid,
                        "filename": fname,
                        "face": b64,
                        "face_image": b64,
                        "input": b64,
                        "encoded": b64,
                        "image": b64
                    }
                    send_sqs(q_req, req)

        except Exception: traceback.print_exc()

    def on_stream_error(self, e): return True
    def on_stream_closed(self): pass

ipc = awsiot.greengrasscoreipc.connect()
req = SubscribeToIoTCoreRequest()
req.topic_name = topic
req.qos = QOS.AT_LEAST_ONCE
op = ipc.new_subscribe_to_iot_core(Handler())
op.activate(req).result(10)

print(f"Listening on {topic}")
while True: time.sleep(10)
