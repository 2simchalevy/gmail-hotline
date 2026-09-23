FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects $PORT; gunicorn binds to it.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 30 server:app
