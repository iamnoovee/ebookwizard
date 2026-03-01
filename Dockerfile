FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc wget unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN mkdir -p fonts && \
    wget -q "https://fonts.gstatic.com/s/sarabun/v15/DtVmJx26TKEr37c9YOZqulw.ttf" -O fonts/Sarabun-Regular.ttf && \
    wget -q "https://fonts.gstatic.com/s/sarabun/v15/DtVhJx26TKEr37c9WBJDnlQIdk1C.ttf" -O fonts/Sarabun-Bold.ttf && \
    wget -q "https://fonts.gstatic.com/s/sarabun/v15/DtVjJx26TKEr37c9YNpoulwm6gDXvwE.ttf" -O fonts/Sarabun-Italic.ttf || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads outputs

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "180", "app:app"]
