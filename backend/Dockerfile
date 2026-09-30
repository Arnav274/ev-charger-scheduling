FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

# libpq for psycopg2, libexpat for pyosmium (reading the OSM extract).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
