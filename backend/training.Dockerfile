# training.Dockerfile
FROM python:3.9-slim

WORKDIR /train

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "train_model.py"]
