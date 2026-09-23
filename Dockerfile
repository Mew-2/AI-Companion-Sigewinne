FROM python:3.11-slim

ENV HF_ENDPOINT=https://hf-mirror.com \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN grep -viE '^(torch|nvidia-|triton|cuda-)' requirements.txt > req-docker.txt \
    && pip install --no-cache-dir -r req-docker.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
