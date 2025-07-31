# Dockerfile

FROM python:3.9-slim-buster

WORKDIR /app

# Don't write .pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# Don't buffer stdout/stderr
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . /app/