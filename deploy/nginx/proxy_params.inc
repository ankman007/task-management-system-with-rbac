# Shared settings for every location proxied to the API.
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $forwarded_proto;
proxy_set_header X-Forwarded-Host $host;

proxy_connect_timeout 5s;
proxy_read_timeout 30s;

# A location with its own add_header drops the server-level ones, so every
# location includes the headers explicitly.
include /etc/nginx/snippets/security_headers.inc;
