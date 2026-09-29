FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app
COPY requirements.txt .

# Bước 1: upgrade pip (fix hash verification bugs trong pip 25.x)
RUN pip install --upgrade pip --no-cache-dir

# Bước 2: force torch CPU-only từ PyTorch index TRƯỚC KHI cài docling
# Lý do: docling phụ thuộc torch nhưng không chỉ định CPU/GPU → pip hay pull
# CUDA wheels (nvidia_nvjitlink, cudnn...) từ PyPI gây hash mismatch
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple/ \
    "torch==2.12.1+cpu" "torchvision==0.27.1+cpu"

# Bước 3: cài các dependency còn lại (docling sẽ reuse torch CPU ở trên).
# deepdoc-lib kéo theo datrie, cần compiler để build wheel trên Python 3.12.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir --retries 3 -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libreoffice \
    tesseract-ocr tesseract-ocr-vie \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
