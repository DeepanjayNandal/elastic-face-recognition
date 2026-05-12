import json
import boto3
import base64
import torch
from io import BytesIO
from PIL import Image
from facenet_pytorch import InceptionResnetV1
import os
import traceback

resnet = InceptionResnetV1(pretrained='vggface2').eval()
sqs = boto3.client('sqs', region_name='us-east-1')
EMBEDDINGS_DATA = None

def load_embeddings():
    global EMBEDDINGS_DATA

    if EMBEDDINGS_DATA is not None:
        return EMBEDDINGS_DATA

    embeddings_path = '/var/task/resnetV1_video_weights.pt'

    if not os.path.exists(embeddings_path):
        EMBEDDINGS_DATA = {}
        return EMBEDDINGS_DATA

    try:
        raw = torch.load(embeddings_path, map_location='cpu')
        emb_dict = {}

        if isinstance(raw, list) and len(raw) == 2 and isinstance(raw[0], list) and isinstance(raw[1], list):
            emb_list, name_list = raw
            from collections import defaultdict
            sums = defaultdict(lambda: torch.zeros_like(emb_list[0]))
            counts = defaultdict(int)

            for emb, name in zip(emb_list, name_list):
                if isinstance(emb, torch.Tensor) and emb.ndim == 2 and emb.shape[0] == 1:
                    emb = emb.squeeze(0)
                sums[name] += emb
                counts[name] += 1

            emb_dict = {name: (sums[name] / counts[name]) for name in sums.keys()}

        elif isinstance(raw, dict):
            for name, emb in raw.items():
                if isinstance(emb, torch.Tensor) and emb.ndim == 2 and emb.shape[0] == 1:
                    emb = emb.squeeze(0)
                emb_dict[name] = emb

        else:
            emb_dict = {}

        EMBEDDINGS_DATA = emb_dict
        return EMBEDDINGS_DATA

    except Exception:
        traceback.print_exc()
        EMBEDDINGS_DATA = {}
        return EMBEDDINGS_DATA

def get_face_embedding(face_image):
    try:
        if face_image.mode != 'RGB':
            face_image = face_image.convert('RGB')

        face_image = face_image.resize((160, 160))

        import numpy as np
        img_array = np.array(face_image)

        face_tensor = torch.from_numpy(img_array).float()
        face_tensor = face_tensor.permute(2, 0, 1)
        face_tensor = face_tensor.unsqueeze(0)
        face_tensor = (face_tensor - 127.5) / 128.0

        with torch.no_grad():
            embedding = resnet(face_tensor)

        return embedding

    except Exception:
        traceback.print_exc()
        raise

def recognize_face(face_embedding, embeddings_dict):
    if not embeddings_dict:
        return 'unknown'

    if isinstance(face_embedding, torch.Tensor) and face_embedding.ndim == 2 and face_embedding.shape[0] == 1:
        face_embedding = face_embedding.squeeze(0)

    min_distance = float('inf')
    recognized_name = 'unknown'

    for name, known_embedding in embeddings_dict.items():
        emb = known_embedding
        if isinstance(emb, torch.Tensor) and emb.ndim == 2 and emb.shape[0] == 1:
            emb = emb.squeeze(0)

        distance = torch.dist(face_embedding, emb).item()

        if distance < min_distance:
            min_distance = distance
            recognized_name = name

    return recognized_name

def handler(event, context):
    embeddings_dict = load_embeddings()

    for record in event['Records']:
        try:
            message_body = json.loads(record['body'])

            request_id = message_body.get('request_id')
            filename = message_body.get('filename')
            face_base64 = message_body.get('face_image')

            if not face_base64 or not request_id:
                continue

            try:
                face_data = base64.b64decode(face_base64)
                face_image = Image.open(BytesIO(face_data))
            except Exception:
                traceback.print_exc()
                continue

            try:
                face_embedding = get_face_embedding(face_image)
            except Exception:
                traceback.print_exc()
                continue

            try:
                result = recognize_face(face_embedding, embeddings_dict)
            except Exception:
                traceback.print_exc()
                result = 'unknown'

            response_message = {
                'request_id': request_id,
                'result': result
            }

            queue_url = os.environ.get('RESPONSE_QUEUE_URL')

            if not queue_url:
                asu_id = os.environ.get('ASU_ID')
                if asu_id:
                    queue_name = f"{asu_id}-resp-queue"
                    try:
                        response = sqs.list_queues(QueueNamePrefix=queue_name)
                        if 'QueueUrls' in response and len(response['QueueUrls']) > 0:
                            queue_url = response['QueueUrls'][0]
                        else:
                            continue
                    except Exception:
                        traceback.print_exc()
                        continue
                else:
                    continue

            try:
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(response_message)
                )
            except Exception:
                traceback.print_exc()
                continue

        except Exception:
            traceback.print_exc()
            continue

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Recognition completed'})
    }
