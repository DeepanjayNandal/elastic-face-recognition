from flask import Flask, request, Response
import boto3
import os
import time

app = Flask(__name__)
student_id = os.environ.get("STUDENT_ID", "your-id")
region = "us-east-1"
s3_client = boto3.client("s3", region_name=region)
sqs_client = boto3.client("sqs", region_name=region)
request_queue_url = sqs_client.get_queue_url(QueueName=f"{student_id}-req-queue")["QueueUrl"]
response_queue_url = sqs_client.get_queue_url(QueueName=f"{student_id}-resp-queue")["QueueUrl"]

@app.post("/")
def process_file():
    try:
        uploaded_file = request.files["inputFile"]
        filename = uploaded_file.filename
        s3_client.upload_fileobj(uploaded_file, f"{student_id}-in-bucket", filename)
        sqs_client.send_message(QueueUrl=request_queue_url, MessageBody=filename)
        image_name = filename.replace('.jpg', '')
        timeout = time.time() + 120

        while time.time() < timeout:
            messages = sqs_client.receive_message(
                QueueUrl=response_queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=1
            )

            if "Messages" in messages:
                for message in messages["Messages"]:
                    body = message["Body"]
                    if body.startswith(image_name + ":"):
                        sqs_client.delete_message(
                            QueueUrl=response_queue_url,
                            ReceiptHandle=message["ReceiptHandle"]
                        )
                        return Response(body, mimetype="text/plain")
                    else:
                        sqs_client.delete_message(
                            QueueUrl=response_queue_url,
                            ReceiptHandle=message["ReceiptHandle"]
                        )
                        sqs_client.send_message(QueueUrl=response_queue_url, MessageBody=body)

        return Response("Timeout", status=504)
    except Exception as e:
        return Response("Error", status=500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
