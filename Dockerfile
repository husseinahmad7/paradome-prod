FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt requirements-production.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-production.txt

FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=paradome.settings.production

RUN apt-get update \
    && apt-get install --no-install-recommends -y libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system paradome \
    && useradd --system --gid paradome --home-dir /app --shell /usr/sbin/nologin paradome

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY . /app
RUN mkdir -p /app/static_files /app/media /app/private_media \
    && chown -R paradome:paradome /app \
    && chmod 0755 /app/docker-entrypoint.sh

USER paradome
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/health/', headers={'X-Forwarded-Proto':'https'}); raise SystemExit(0 if urllib.request.urlopen(r, timeout=3).status == 200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--config", "python:paradome.gunicorn", "paradome.wsgi:application"]
