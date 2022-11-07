# syntax=docker/dockerfile:1

FROM python:3.10-alpine
ENV SERVICE_PORT=8082
ENV VALIDATOR_PORT=8081

# Install curl for healthcheck
USER root
RUN apk add curl
# Install GCC for regex python module
RUN apk add build-base

WORKDIR /app
# Config
ENV FLASK_APP=ABIDE_validation.py
ENV FLASK_RUN_HOST=0.0.0.0
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
EXPOSE ${SERIVCE_PORT}
COPY . .
ENTRYPOINT flask run --host 0.0.0.0 --port ${SERVICE_PORT}
