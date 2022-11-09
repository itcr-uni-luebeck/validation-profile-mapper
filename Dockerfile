# syntax=docker/dockerfile:1
FROM python:3.10-alpine

ENV SERVICE_PORT 8092
ENV VALIDATOR_URL "http://localhost:8091"

RUN apk add build-base

VOLUME ["/app/maps"]

WORKDIR /app
# Config
ENV FLASK_APP=ABIDE_validation.py
ENV FLASK_RUN_HOST=0.0.0.0
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
EXPOSE ${SERIVCE_PORT}
COPY . .

ENTRYPOINT flask run --host 0.0.0.0 --port ${SERVICE_PORT}
