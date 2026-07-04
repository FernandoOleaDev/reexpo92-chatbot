# reexpo92-chatbot — imagen para Railway
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    TRANSFORMERS_OFFLINE=0 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /srv

# dependencias del sistema mínimas (sentence-transformers trae torch CPU)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Precarga del modelo e5-base en la imagen (arranque rápido, sin descarga en runtime)
ARG EMBED_MODEL=intfloat/multilingual-e5-base
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"

COPY . .

# Railway inyecta $PORT
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
