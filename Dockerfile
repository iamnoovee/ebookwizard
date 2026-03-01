FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    wget \
    fonts-thai-tlwg \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

WORKDIR /app

# Download Sarabun font from Google Fonts GitHub
RUN mkdir -p fonts && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf" -O fonts/Sarabun-Regular.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Bold.ttf" -O fonts/Sarabun-Bold.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Italic.ttf" -O fonts/Sarabun-Italic.ttf && \
    echo "Sarabun fonts downloaded OK" || \
    (echo "Sarabun failed, copying system Thai fonts" && \
     cp /usr/share/fonts/truetype/tlwg/Sarabun.ttf fonts/Sarabun-Regular.ttf 2>/dev/null || \
     cp /usr/share/fonts/truetype/tlwg/Garuda.ttf fonts/Sarabun-Regular.ttf 2>/dev/null || true && \
     cp /usr/share/fonts/truetype/tlwg/Sarabun-Bold.ttf fonts/Sarabun-Bold.ttf 2>/dev/null || \
     cp /usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf fonts/Sarabun-Bold.ttf 2>/dev/null || \
     cp fonts/Sarabun-Regular.ttf fonts/Sarabun-Bold.ttf 2>/dev/null || true && \
     cp fonts/Sarabun-Regular.ttf fonts/Sarabun-Italic.ttf 2>/dev/null || true)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads outputs

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "180", "app:app"]
