FROM python:3.10-slim

# Prevent interactive prompts / smaller image
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# install system deps (needed for psycopg2 + torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# install Python deps
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# copy backend code
COPY . .

EXPOSE 8000

# use uvicorn without reload (stable in docker)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
