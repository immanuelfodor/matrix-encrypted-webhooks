FROM python:3-alpine

WORKDIR /app

COPY requirements.txt ./

# build dependencies
RUN set -x \
    && apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev olm-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# runtime dependeincies
RUN set -x \
    && apk add --no-cache olm

ENV PYTHONUNBUFFERED=1
ENV LOGIN_STORE_PATH=/config
ENV MATRIX_SERVER=https://matrix.example.org
ENV MATRIX_SSLVERIFY=True
ENV MATRIX_USERID=@myhook:matrix.example.org
ENV MATRIX_PASSWORD=mypassword
ENV MATRIX_ROOMID=!myroomid:matrix.example.org
ENV MATRIX_DEVICE=any-device-name
ENV MESSAGE_FORMAT=yaml
ENV USE_MARKDOWN=False
ENV ALLOW_UNICODE=True

# run as a non-root user, @see: https://busybox.net/downloads/BusyBox.html#adduser
RUN set -x \
    && adduser -D -H -g '' -u 1000 matrix \
    && mkdir -p "${LOGIN_STORE_PATH}" \
    && chown -R matrix. "${LOGIN_STORE_PATH}"

COPY docker-entrypoint.sh ./

ENTRYPOINT [ "./docker-entrypoint.sh" ]
EXPOSE 8000

COPY src/ ./src/

USER matrix
