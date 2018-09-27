FROM python:3-alpine

ENV PYTHONIOENCODING UTF-8
ENV PYTHONUNBUFFERED 1

RUN apk update && apk --no-cache upgrade && apk --no-cache add shadow python3 python3-dev bash git curl && pip install -U pip

COPY . /app
WORKDIR /app

RUN pip install -e /app
