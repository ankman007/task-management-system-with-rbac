# Deploying on Dokploy

This guide deploys the Task Management System at **https://task-mgmt.ankit-poudel.com.np** as one Dokploy **Compose** application built from `docker-compose.dokploy.yml`. It follows the same conventions as the Ecommerce Store deployment on the same server:
- a Compose app on the `main` branch;
- environment set in the Environment tab;
- no host ports, with the domain attached to an nginx service on Dokploy's network;
- named volumes;
- pre-start steps that run in the app container, so failures show in its logs.

## What is done in the repository, and what needs the dashboard

| Done in code (this repository) | Needs access to Dokploy, Cloudflare or the server |
|---|---|
| `docker-compose.dokploy.yml`: `api`, `nginx` and `db` services, healthchecks, restart policies, log rotation, private network, persistent volume | Creating the Compose application and pointing it at the repository |
| `deploy/nginx/`: an nginx image with the dashboard baked in, `/api` proxy, rate limiting and security headers | Filling in the Environment tab with real secrets |
| `Dockerfile`: non-root API image with a healthcheck | Adding the domain in Dokploy |
| Migrations and the idempotent admin seed run on every API start | Cloudflare DNS / Tunnel and SSL settings |
| Startup refuses placeholder secrets, a wildcard host and example admin credentials | Pressing **Deploy** and checking the result |
| `.env.dokploy.example`, this guide, and CI that builds both images | Backups (Dokploy Volume Backups) |

> **Status on 2026-10-26.** `https://task-mgmt.ankit-poudel.com.np` returns **Cloudflare error 522**: Cloudflare can't open a connection to `202.79.47.147`. A direct request to that IP times out too. `https://ecommerce-store.ankit-poudel.com.np`, on the same server, answers normally. That fits the Ecommerce Store guide, which moved to a **Cloudflare Tunnel** because ports 80/443 aren't reachable from the internet. Unless those ports have since been opened, use [Route B (Cloudflare Tunnel)](#route-b-cloudflare-tunnel-likely-the-current-setup) below. The plain proxied `A` record (Route A) will keep returning 522.

## How a request flows

```text
Browser ──HTTPS──> Cloudflare ──(Tunnel, or direct to 202.79.47.147)──> Traefik (Dokploy)
        ──HTTP──> nginx:80 ──┬── /                      dashboard (static files in the image)
                             ├── /api/...               api:8000  (FastAPI, ROOT_PATH=/api)
                             └── /docs, /openapi.json   api:8000  (Swagger UI)
                                         api ──> db:5432 (PostgreSQL, volume postgres_data)
```

- Only `nginx` joins the external `dokploy-network`, which is how Traefik reaches it. `api` and `db` stay on the project's own network and publish no ports.
- The image names (`task-management-api:dokploy`, `task-management-nginx:dokploy`), the network and the volume are all scoped to this project. Nothing in it touches the Ecommerce Store, Job Prep AI or anything else on the server.

## 1. Prerequisites

- The Dokploy server already hosting the other projects.
- The GitHub repository `ankman007/task-management-system-with-rbac`, reachable from Dokploy through the GitHub provider used for the other apps, or a Git URL with a deploy key.
- About 512 MB of free RAM: PostgreSQL, two uvicorn workers and nginx.

## 2. Create the application

1. In Dokploy, open the project you use for personal apps, or create one, then **Create Service → Compose**. Name it e.g. `task-management`.
2. **General → Provider:** GitHub. Repository `task-management-system-with-rbac`, branch **`main`**.
3. **Compose Path:** `./docker-compose.dokploy.yml`
4. Optional: turn on **Autodeploy** so every push to `main` redeploys. This is the same as for the other apps.

Don't add anything under **Advanced → Ports**. Traefik already listens on 80/443.

## 3. Environment

Paste [.env.dokploy.example](../.env.dokploy.example) into **Environment** and replace every `replace-with-...` value. Dokploy writes these to `.env` next to the compose file. `ENVIRONMENT=production`, `ROOT_PATH=/api` and `DATABASE_URL` are set by the compose file itself.

| Variable | Value |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"`. At least 32 characters. Changing it later logs everyone out. |
| `ALLOWED_HOSTS` | `task-mgmt.ankit-poudel.com.np`. Add more hosts comma-separated if you attach more domains. |
| `CORS_ORIGINS` | Leave empty. The dashboard is on the same origin. |
| `DOCS_ENABLED` | `true` to keep Swagger at `/docs`, `false` to hide it. |
| `WEB_CONCURRENCY` | `2` (uvicorn workers). |
| `POSTGRES_USER` / `POSTGRES_DB` | `task_user` / `task_db` (any names). |
| `POSTGRES_PASSWORD` | `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Use only letters, digits, `-` and `_`, because it's embedded in the database URL. |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | Your admin login. The password needs at least 8 characters with a letter and a digit. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |

Safety checks run at startup. If any of them fails, the deploy fails and the API logs say why:
- `SECRET_KEY` still contains `replace-with` / `change-me`, or is shorter than 32 characters.
- `ALLOWED_HOSTS` is `*` or empty, or `CORS_ORIGINS` is `*`.
- `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` are still example values.

## 4. Domain, Cloudflare and TLS

In **Domains → Create Domain**:
- Host: `task-mgmt.ankit-poudel.com.np`
- Service: **`nginx`**, Container Port: **`80`**. Not the API: nginx serves the dashboard and routes `/api`.
- Path: `/`

The HTTPS settings depend on how Cloudflare reaches the server.

### Route A: direct (ports 80/443 open to the internet)

1. **Cloudflare → DNS:** `A` record `task-mgmt` → `202.79.47.147`, **Proxied** (this record already exists).
2. **Cloudflare → SSL/TLS → Overview:** **Full (strict)**, as for the other subdomains.
3. **Dokploy domain:** HTTPS **on**, certificate **Let's Encrypt**.
4. If Cloudflare shows **526** right after this, Let's Encrypt hasn't issued the certificate yet. Set the record to **DNS only** (grey cloud), wait a couple of minutes, then switch it back to **Proxied**.

If you get **522**, the server isn't reachable on 80/443 from the internet. No app setting fixes that: use Route B, or have the network owner open or forward TCP 80/443.

### Route B: Cloudflare Tunnel (likely the current setup)

The Ecommerce Store guide (section 10) sets up one `cloudflared` tunnel for every app on the server. It's deployed as its own Dokploy Compose service from `ecommerce-store/deploy/cloudflared`, and it sends traffic to Traefik. To add this app to it:

1. **Cloudflare → DNS:** delete the existing `A` record for `task-mgmt`. The tunnel creates its own record, and a record with the same name conflicts with it.
2. **Cloudflare → Zero Trust → Networks → Tunnels →** the existing tunnel **→ Public Hostname → Add**:
   - Subdomain `task-mgmt`, domain `ankit-poudel.com.np`
   - Service type **HTTP**, URL **`dokploy-traefik:80`**. Use the same URL as the Ecommerce Store hostname.
3. **Dokploy domain:** HTTPS **off**, Certificate **None**. Cloudflare terminates HTTPS at its edge and the tunnel delivers plain HTTP to Traefik. With HTTPS on, Traefik would redirect in a loop.
4. Visitors still use `https://task-mgmt.ankit-poudel.com.np`. Nothing in the app's environment changes.

In both routes, HTTPS ends at Cloudflare or Traefik. nginx passes `X-Forwarded-Proto` through, and the API trusts it (uvicorn `--proxy-headers`), which is safe because only nginx can reach the API.

## 5. Deploy

Click **Deploy**. Dokploy builds the `api` and `nginx` images and starts the stack in dependency order:

1. **db** starts, and its healthcheck (`pg_isready`) has to pass.
2. **api** starts. Its entrypoint runs `alembic upgrade head`, then `python -m scripts.seed_admin`, then starts uvicorn. Its healthcheck (`GET /health`) passes only once uvicorn is serving, which is after the migrations and the seed succeeded.
3. **nginx** starts only after the API is healthy.

If a migration or the seed fails, the API container exits and restarts and never becomes healthy. nginx isn't started, and the deploy ends with `dependency failed to start: container ...-api-1 is unhealthy`. The previous containers' data is untouched. Read the reason in **Logs → api**.

## 6. Verify the deployment

```bash
curl -s https://task-mgmt.ankit-poudel.com.np/api/health
# {"status":"ok"}

curl -s -o /dev/null -w "%{http_code}\n" https://task-mgmt.ankit-poudel.com.np/
# 200 (dashboard)

curl -s -X POST https://task-mgmt.ankit-poudel.com.np/api/auth/login \
  -d 'username=<FIRST_ADMIN_EMAIL>&password=<FIRST_ADMIN_PASSWORD>'
# {"access_token":"...","token_type":"bearer","expires_in":3600}
```

Then:
- Open `https://task-mgmt.ankit-poudel.com.np`, sign in as the admin, and check the dashboard loads.
- Open `/docs`, click **Authorize** (email as username) and call `GET /users/me`.
- In Dokploy, all three containers show **healthy**, and **Logs → api** shows the migrations and `Created admin account ...` (or `already exists` on later deploys).
- Give your teammates roles from the dashboard's **Users** page, or with `PATCH /api/users/{id}/role`.

## 7. Updating the application

- **Push to `main`.** With Autodeploy on, Dokploy redeploys automatically; otherwise click **Deploy**. Every start applies any new migrations before serving.
- **Data is kept.** It lives in the named volume `postgres_data`. Never use **Delete volumes** or `docker compose down -v` on this app unless you mean to wipe the database.
- **Rolling back code:** redeploy an earlier commit. If the newer release added a migration, check whether the old code works with the new schema before rolling back. Run `alembic downgrade <revision>` from the API container's terminal only after a backup, because downgrades can drop columns.
- **Logs:** Dokploy's **Logs** tab per container. Each container keeps up to 5 × 10 MB of JSON logs.

## 8. Backups and restore

- **Dokploy Volume Backups:** schedule backups of the `postgres_data` volume to S3-compatible storage, as for the other apps' databases.
- **Logical dump** (portable across PostgreSQL versions), from the **db** container's terminal:

  ```bash
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/task_db.dump
  ```

  Copy it off the server (`docker cp <db-container>:/tmp/task_db.dump .`).
- **Restore:**
  1. Stop the **api** service so nothing writes.
  2. Copy the dump into the db container.
  3. Run `pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists /tmp/task_db.dump`.
  4. Start the API again.

  Test a restore once on a scratch stack before you need it.

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Deploy ends with `container ...-api-1 is unhealthy` | Open **Logs → api**. The last lines before the restart give the reason (one of the rows below). |
| `Unsafe production settings: ...` in the api logs | A placeholder `SECRET_KEY`, or `ALLOWED_HOSTS` set to `*` or empty. Fix it in Environment and redeploy. |
| `secret_key ... at least 32 characters` | Generate a longer key (section 3). |
| `FIRST_ADMIN_... is still the example value` | Set a real admin email and password. |
| `password authentication failed for user ...` | PostgreSQL set its password when the volume was **first** created. Changing `POSTGRES_PASSWORD` later doesn't change it. Put the original password back, or change it inside PostgreSQL from the db container's terminal (`psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER USER task_user PASSWORD '<new>';"`), then update the Environment tab. Don't delete the volume if it holds real data. |
| Cloudflare **522** | Cloudflare can't reach the server on 80/443. Use the tunnel (Route B) or open the ports. |
| Cloudflare **526** | Route A only: the certificate isn't issued yet. Grey-cloud the record for a few minutes. |
| **502** from Traefik or the tunnel | nginx isn't running or isn't on `dokploy-network`. Check the nginx container and that the domain points to service `nginx`, port `80`. With a tunnel, check the Traefik container name used in the hostname URL. |
| Too many redirects | Route B with HTTPS turned on in the Dokploy domain. Turn it off (Cloudflare does HTTPS). |
| `Invalid host header` (400) | `ALLOWED_HOSTS` doesn't include the domain being used. |
| `RATE_LIMITED` (429) on login | More than 10 login/register attempts a minute from one client. Wait a minute. |
| Dashboard loads but every API call fails | Check `curl https://<host>/api/health`. If nginx returns 502, the API is down: see its logs. |
| Admin account wasn't created and the log says `already exists with role USER` | Someone registered that email first. The seed deliberately doesn't promote it. Promote it with another admin, or pick a different `FIRST_ADMIN_EMAIL`. |

## 10. Risks and data safety

- **Migrations:** `0001` creates the schema and `0002` inserts the three roles (`ON CONFLICT DO NOTHING`). Both are safe to re-run on an existing database: Alembic skips applied revisions. Neither is destructive.
- **Volumes:** the compose file never removes or renames the database volume. Redeploys reuse `postgres_data`.
- **Secrets** live only in Dokploy's Environment tab. The repository contains templates with obvious placeholders that the app refuses to run with.
