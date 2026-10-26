# nginx with the site config and the frontend baked in, so production needs no
# bind mounts (Dokploy cleans bind-mounted paths on redeploy).
# Build context is the repository root:
#   docker build -f deploy/nginx/Dockerfile .
# Dockerfile.dockerignore next to this file limits the context to what's copied.
FROM nginx:1.30-alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
# .inc in a separate directory, so nginx's `include conf.d/*.conf` never loads
# them at the http level.
COPY deploy/nginx/proxy_params.inc deploy/nginx/security_headers.inc /etc/nginx/snippets/
COPY frontend/ /usr/share/nginx/html/

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/nginx-health || exit 1
