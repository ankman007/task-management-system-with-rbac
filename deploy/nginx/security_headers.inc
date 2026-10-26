# Security headers for every response. HSTS is left to the TLS terminator
# (Cloudflare/Traefik), because this container only ever speaks plain HTTP.
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
