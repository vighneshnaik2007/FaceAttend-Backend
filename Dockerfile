FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    python3-dev \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Install pre-built dlib wheel (avoids compiling = no OOM)
RUN pip install --no-cache-dir \
    "https://github.com/z-mahmud22/Dlib_Windows_Python3.x/releases/download/v19.24.2/dlib-19.24.2-cp310-cp310-linux_x86_64.whl"

# Install face_recognition_models
RUN pip install --no-cache-dir \
    git+https://github.com/ageitgey/face_recognition_models

# Install rest of requirements (dlib already installed, will be skipped)
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD gunicorn app:app --bind 0.0.0.0:7860 --workers 1 --timeout 300