import json
import boto3
import base64
from io import BytesIO
from PIL import Image
from facenet_pytorch import MTCNN
import os
import traceback

mtcnn = MTCNN(
    keep_all=False,
    device='cpu',
    min_face_size=20,
    thresholds=[0.6, 0.7, 0.7]
)

sqs = boto3.client('sqs', region_name='us-east-1')

def handler(event, context):
    try:
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event

        content = body.get('content')
        request_id = body.get('request_id')
        filename = body.get('filename')

        if not content:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Missing content parameter'})}
        if not request_id:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Missing request_id parameter'})}
        if not filename:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Missing filename parameter'})}

        try:
            image_data = base64.b64decode(content)
        except Exception as e:
            return {'statusCode': 400, 'body': json.dumps({'error': f'Invalid base64 content: {str(e)}'})}

        try:
            image = Image.open(BytesIO(image_data))
        except Exception as e:
            return {'statusCode': 400, 'body': json.dumps({'error': f'Invalid image data: {str(e)}'})}

        if image.mode != 'RGB':
            image = image.convert('RGB')

        boxes, probs = mtcnn.detect(image)

        if boxes is None or len(boxes) == 0:
            return {
                'statusCode': 200,
                'body': json.dumps({'request_id': request_id, 'filename': filename, 'message': 'No face detected'})
            }

        box = boxes[0]
        width, height = image.size
        x1 = max(0, int(box[0]))
        y1 = max(0, int(box[1]))
        x2 = min(width, int(box[2]))
        y2 = min(height, int(box[3]))

        face = image.crop((x1, y1, x2, y2))
        buffer = BytesIO()
        face.save(buffer, format='JPEG', quality=95)
        face_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        message_body = {'request_id': request_id, 'filename': filename, 'face_image': face_base64}

        queue_url = os.environ.get('REQUEST_QUEUE_URL')
        if not queue_url:
            asu_id = os.environ.get('ASU_ID')
            if asu_id:
                queue_name = f"{asu_id}-req-queue"
                try:
                    response = sqs.list_queues(QueueNamePrefix=queue_name)
                    if 'QueueUrls' in response and len(response['QueueUrls']) > 0:
                        queue_url = response['QueueUrls'][0]
                    else:
                        return {'statusCode': 500, 'body': json.dumps({'error': f'Request queue {queue_name} not found'})}
                except Exception as e:
                    return {'statusCode': 500, 'body': json.dumps({'error': f'Failed to find request queue: {str(e)}'})}
            else:
                return {'statusCode': 500, 'body': json.dumps({'error': 'REQUEST_QUEUE_URL and ASU_ID not configured'})}

        try:
            sqs_response = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message_body))
        except Exception as e:
            traceback.print_exc()
            return {'statusCode': 500, 'body': json.dumps({'error': f'Failed to send message to SQS: {str(e)}'})}

        return {
            'statusCode': 200,
            'body': json.dumps({
                'request_id': request_id,
                'filename': filename,
                'message': 'Face detected and sent for recognition',
                'sqs_message_id': sqs_response['MessageId']
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f"Unexpected error in face detection: {str(e)}",
                'request_id': request_id if 'request_id' in locals() else 'unknown'
            })
        }
