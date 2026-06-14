FROM python:3.11-slim

# yt-dlp 오디오 추출 + ffprobe(곡 길이)에 ffmpeg 필요
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces 권장: 비루트 사용자(1000)로 실행
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    DATA_DIR=/home/user/app/data \
    TMP_DIR=/home/user/app/tmp \
    COOKIE_SECURE=1 \
    PORT=7860

WORKDIR /home/user/app

# 의존성 먼저 설치(레이어 캐시)
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 앱 소스
COPY --chown=user backend ./backend
COPY --chown=user frontend ./frontend

EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
