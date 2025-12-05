FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for libvirt-python
RUN apt-get update && apt-get install -y \
    pkg-config \
    libvirt-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]