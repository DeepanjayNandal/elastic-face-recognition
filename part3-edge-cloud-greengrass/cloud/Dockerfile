FROM --platform=linux/amd64 python:3.9-slim
WORKDIR /var/task

RUN apt-get update && apt-get install -y \
    cmake \
    ca-certificates \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install torch==2.0.1+cpu torchvision==0.15.2+cpu -f https://download.pytorch.org/whl/torch_stable.html

COPY requirements.txt /var/task
RUN python3 -m pip install -r requirements.txt

RUN mkdir -p /tmp/.cache
ENV TORCH_HOME=/tmp/.cache/torch
ENV XDG_CACHE_HOME=/tmp/.cache/torch

COPY resnetV1_video_weights.pt /var/task
COPY fr_lambda.py /var/task

ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]
CMD ["fr_lambda.handler"]
