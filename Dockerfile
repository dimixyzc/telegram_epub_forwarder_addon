FROM python:3.11-alpine
WORKDIR /app
RUN apk add --no-cache jq libjpeg-turbo zlib
COPY requirements.txt .
RUN apk add --no-cache --virtual .build-deps build-base jpeg-dev zlib-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps
COPY app.py .
COPY run.sh .
RUN chmod +x run.sh
CMD ["/app/run.sh"]
