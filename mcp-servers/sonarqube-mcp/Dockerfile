FROM python:3.11-slim

WORKDIR /app

# Install required packages for HTTP requests
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV PYTHONUNBUFFERED=1

# Run the server directly
CMD ["python", "server.py"]