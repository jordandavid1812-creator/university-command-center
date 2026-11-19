# The website image: Python 3.12, the hashed Django lock file, the server code and collected
# static files. No secrets, tests or student data are ever copied in (see /.dockerignore).
FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UCC_STATIC_ROOT=/app/static PYTHONPATH=/app

RUN groupadd --system --gid 10001 ucc \
 && useradd --system --uid 10001 --gid ucc --home-dir /app --no-create-home --shell /usr/sbin/nologin ucc

WORKDIR /app
COPY requirements-django-lock.txt ./
RUN pip install --require-hashes --only-binary=:all: -r requirements-django-lock.txt

COPY academic_logic.py ./
COPY server ./server
COPY deploy/start-web.sh deploy/provision.sh ./deploy/
RUN chmod 0555 deploy/start-web.sh deploy/provision.sh

# Collect CSS/JS once at build time. These placeholder values exist only for this one command;
# the running container gets its real values from its private environment file.
RUN cd server && env DJANGO_SECRET_KEY=build-only PGDATABASE=build PGUSER=build \
      UCC_CONTEXT_SIGNING_KEY=00 UCC_RUNTIME_ROLE=build UCC_AUTH_ROLE=build UCC_AUTH_PASSWORD=build \
      UCC_SITE_HOST=build.example.com UCC_TRUSTED_PROXY=172.30.0.10/32 \
      UCC_EMAIL_ADDRESS=build.only@gmail.com UCC_EMAIL_APP_PASSWORD=buildonlybuildon \
      python manage.py collectstatic --noinput -v 0 --settings=config.settings.web_production

USER ucc
WORKDIR /app/server
ENV DJANGO_SETTINGS_MODULE=config.settings.web_production
EXPOSE 8000
CMD ["/app/deploy/start-web.sh"]
