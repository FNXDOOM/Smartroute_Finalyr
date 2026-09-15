# Production deploy — Docker Hub + EC2 + Secrets Manager (EC2 is GIT-FREE)

Dev workflow is unchanged: `docker compose up --build` still uses
`docker-compose.yml` + `backend/.env` + `frontend/.env`.

Production uses **separate** files and never builds on EC2.
EC2 holds NO git repo. Each deploy ships a 2-file bundle via SCP:

- `docker-compose.prod.yml` → `$EC2_DEPLOY_DIR/docker-compose.prod.yml`
- `deploy/deploy.sh`         → `$EC2_DEPLOY_DIR/deploy/deploy.sh`
- `.github/workflows/ci-cd.yml` — lint/test/build, push, SCP bundle, SSH deploy

## 1. GitHub configuration

Actions → Settings → Secrets and variables → Actions.

**Secrets** (never logged, never baked except where noted):

| Name | Used for |
|---|---|
| `DOCKERHUB_USERNAME` | `docker/login-action` |
| `DOCKERHUB_TOKEN` | Docker Hub PAT (not password) for login/push |
| `EC2_HOST` | SSH target (IP or DNS, no `ssh://`) |
| `EC2_USER` | SSH user (e.g. `ubuntu`) |
| `EC2_SSH_KEY` | Private OpenSSH key for `EC2_USER` |
| `VITE_CLERK_PUBLISHABLE_KEY` | Frontend `docker build --build-arg` (public `pk_*`, ends up in browser bundle by design) |

**Variables** (non-secret config):

| Name | Example placeholder | Used for |
|---|---|---|
| `DOCKERHUB_NAMESPACE` | `myorg` | Image prefix for both repos |
| `VITE_API_BASE_URL` | `https://api.example.com` | Frontend build-arg (public API origin) |
| `AWS_REGION` | `ap-south-1` | Passed to `deploy.sh` (else auto-detected on EC2) |
| `BACKEND_SECRET_ID` | `smartroute/production/backend` | Secrets Manager ID (default if unset) |
| `EC2_DEPLOY_DIR` | `/opt/smartroute` | Absolute bundle dir on EC2 (default if unset). Must be absolute; `~` values are rejected. Replaces the old `EC2_PROJECT_DIR`. |

Backend runtime secrets are **not** in GitHub. EC2 reads them from Secrets Manager.

Also create the `production` Environment (for approval rules, optional) because
the `deploy-prod` job references `environment: production`.

## 2. EC2 configuration (one-time)

1. Ubuntu 22.04/24.04, Docker Engine + Compose plugin, AWS CLI v2, `python3`. `git` is NOT needed.
2. Attach an **IAM instance profile** with only:
   `secretsmanager:GetSecretValue` on the backend secret (see §3).
   No long-lived AWS keys on EC2.
3. Create the deploy dir (CI creates it too, but set ownership once):
   `sudo mkdir -p /opt/smartroute/deploy && sudo chown -R ubuntu:ubuntu /opt/smartroute`.
4. Security Groups: open `80/443` (NPM), restrict `22` (SSH) and `81` (NPM admin)
   to admin IPs. Do **not** open `8000` or DB ports publicly.
5. First run: `docker login` is **not** needed for public repos; for private
   Docker Hub repos run once: `docker login -u <NAMESPACE>` (PAT), or configure
   credential helper. Images are public-or-private at your discretion.
6. Configure Nginx Proxy Manager once via `:81`:
   app host → `frontend:80`, api host → `api:8000`, WebSockets ON,
   Let's Encrypt + force SSL, raise proxy timeouts for WS.
   Rotate default `admin@example.com / changeme` immediately.

## 3. Secrets Manager

Single JSON secret (recommended ID: `smartroute/production/backend`).
Keys = env var names read by `backend/config.py`:

Required (deploy aborts if missing/empty):

```json
{
  "DATABASE_URL": "postgresql://USER:PASSWORD@HOST:5432/DBNAME",
  "CLERK_JWKS_URL": "https://<clerk-domain>/.well-known/jwks.json",
  "CLERK_ISSUER": "https://<clerk-domain>",
  "CLERK_SECRET_KEY": "sk_live_...",
  "STADIA_API_KEY": "<stadia-key>",
  "LOCAL_JWT_SECRET": "<64+ random chars>",
  "ALLOWED_ORIGINS": "https://app.example.com",
  "CLERK_AUTHORIZED_PARTIES": "https://app.example.com",
  "RAZORPAY_KEY_ID": "rzp_live_...",
  "RAZORPAY_KEY_SECRET": "<razorpay-key-secret>",
  "RAZORPAY_WEBHOOK_SECRET": "<razorpay-webhook-secret>"
}
```

Razorpay keys are backend-only: the deploy validation fails if they are
missing, and they must never be added to frontend build args (`VITE_*`). Use
`rzp_test_*` credentials for staging and `rzp_live_*` for production — see
[`docs/payments.md`](../docs/payments.md) for setup, webhooks, and test-mode
payment flow.

Optional (defaults in `deploy.sh` if absent):
`APP_ENV` (forced to `production`), `AUTH_PROVIDER`, `CLERK_AUDIENCE`,
`CLERK_ALLOW_NATIVE_CLIENTS`, `LOCAL_JWT_EXPIRES_MINUTES`, `LOG_LEVEL`,
`ENABLE_BACKGROUND_JOBS_IN_API`, `STADIA_GEOCODER_URL`, `STADIA_ROUTER_URL`,
`STADIA_MATRIX_URL`, `STADIA_NEAREST_ROADS_URL`, `STADIA_MAP_MATCH_URL`,
`STADIA_ROUTING_COSTING`, `STADIA_TILES_URL`, `STADIA_MAP_STYLE_PATH`.

Rules enforced by `deploy.sh`: `LOCAL_JWT_SECRET` must not be empty/placeholder;
`ALLOWED_ORIGINS`/`CLERK_AUTHORIZED_PARTIES` must be `https://` and not localhost.
`VITE_*` vars are **not** in this secret (frontend build args in CI).

Create with (placeholders only):

```bash
aws secretsmanager create-secret \
  --name smartroute/production/backend \
  --secret-string file://backend-secret.json \
  --region <AWS_REGION>
```

## 4. What happens after `git push origin main`

1. `backend-tests` (pytest, sqlite + dummy JWT secret) and `frontend-ci`
   (`npm ci`, `lint`, `build` check) run. Any failure stops the pipeline.
2. `docker-push`: Buildx builds backend (`./backend/Dockerfile`) and frontend
   (`./frontend/Dockerfile` + prod `VITE_*` args), pushes
   `: <short-sha>` and `:latest`, then smoke-tests the pushed backend image
   (`docker run ... python -c "import main"` with dummy CI env) so a missing
   runtime dependency fails the pipeline before EC2 is touched.
   Deploy uses the SHA only.
3. `deploy-prod` (env `production`, concurrency `production`): SCP
   `docker-compose.prod.yml` + `deploy/deploy.sh` from THAT commit to
   `$EC2_DEPLOY_DIR`, then SSH `./deploy/deploy.sh <short-sha>`:
   pull exact images → fetch secret JSON → write `deploy/.env.prod` (0600) →
   `docker run --rm ... alembic upgrade head` (new image) →
   `docker compose -f docker-compose.prod.yml up -d` →
   poll `frontend /health`, `api /health/live`, `api /health/ready` (180s).
   The frontend probe must use `http://127.0.0.1/health`, NOT `localhost`:
   inside the nginx:alpine container `localhost` resolves to IPv6 (`::1`)
   while `nginx.conf` listens IPv4-only (`listen 80`), so a `localhost`
   probe fails with "Connection refused". Do not "simplify" it back.
4. Success: record SHA in `deploy/.last-good-tag`, prune images keeping newest 3
   per repo. Failure: automatic rollback (see §5), workflow marked failed.

## 5. Rollback

- Before pulling, `deploy.sh` records the previous SHA from
  `deploy/.last-good-tag` (fallback: running `api` image tag).
- Migrations are **forward-only**. `alembic downgrade` is never run.
  On healthcheck failure the script restarts the **previous images**
  (pulled, never rebuilt) and re-checks health. The DB stays migrated;
  old code is expected to tolerate additive columns (the repo's pattern).
  Destructive migrations need a manual, tested backward plan — do not auto-deploy those.
- Manual rollback: `DOCKERHUB_NAMESPACE=<ns> IMAGE_TAG=<prev-sha> /opt/smartroute/deploy/deploy.sh <prev-sha>`
  or `DOCKERHUB_NAMESPACE=<ns> IMAGE_TAG=<prev-sha> docker compose -f /opt/smartroute/docker-compose.prod.yml up -d`.

## 5b. Abuse protection / rate limiting (production)

Three layers, each with a distinct job (application limits do NOT stop DDoS):

1. **API app (FastAPI, `utils/rate_limit.py`)** — per-IP sliding-window limits
   + 1 MiB body cap (413) on every route; stricter per-endpoint budgets for
   `/auth/login` (15/5min), `/auth/register` (5/h), `/predict`, `/cluster/*`,
   `/route/optimize`, `/routing`, `/geocode`, `/maps/stadia`, `/rides/*` batch,
   `/jobs/run`; additional per-USER caps on `/payments/create-order` (15/10min)
   and `/payments/verify` (30/10min). `/payments/webhook`, `/health/*` and CORS
   preflight are exempt; webhook auth = X-Razorpay-Signature. 429s are
   project-shape (`{"detail": ...}`) with `Retry-After` and `X-RateLimit-*`
   headers. Tune via `RATE_LIMIT_ENABLED`, `RATE_LIMIT_DEFAULT_PER_MINUTE`,
   `MAX_BODY_BYTES` (deploy/.env.prod or Secrets Manager).
2. **Nginx Proxy Manager (edge proxy)** — only published ports; owns TLS and
   connection exposure. Paste-ready per-host configs live in `deploy/nginx/`
   (deliberately zoneless — see below):
   - `npm-api-host-advanced.conf` → paste into the api proxy host's
     Advanced tab: 1 MiB body cap, body/header/keepalive/send timeouts.
   - `npm-frontend-host-advanced.conf` → paste into the frontend host's
     Advanced tab: same timeouts.
   These are timeouts and body caps only. Edge-level request-rate limiting
   (`limit_req`/`limit_conn`) needs http-level zones that NPM's Advanced tab
   cannot define (they'd require a custom http_top include via docker exec);
   this deployment relies on the FastAPI limiter (layer 1) for request
   budgets instead. If floods ever become a problem, add `limit_req_zone` +
   `limit_req` at that point — rejected clients should get 429 via
   `limit_req_status 429;`.
3. **EC2 security group** — allows 80/443 + SSH only. It is access control,
   NOT DDoS mitigation. Volumetric attacks must be handled by a cloud WAF/
   CDN (e.g. Cloudflare) or AWS Shield Standard in front of EC2; add one if
   the deployment becomes a target. App- and proxy-level limits cannot stop
   traffic that saturates the instance's network.

Note: per-IP limits live in the api container's memory. The stack ships
exactly one `api` replica (worker is a separate non-HTTP process), so state
is correct today. If `api` is ever scaled to N replicas, effective limits
multiply by N — move the store to a shared backend (Redis) first.

## 6. First production deployment (safe order)

```bash
# 1. Create Secrets Manager JSON secret, Docker Hub repos, GitHub secrets/vars above.
# 2. Run the EC2 one-time setup: deploy dir + IAM check (no git clone).
#    sudo mkdir -p /opt/smartroute/deploy && sudo chown -R ubuntu:ubuntu /opt/smartroute
# 3. Merge to main (current dev branch is `features`):
git checkout main && git merge features && git push origin main
# 4. Watch Actions → CI/CD → docker-push → deploy-prod.
# 5. Configure NPM hosts, verify https app + api docs, then leave CI to handle the rest.
# 6. If ~/Smartroute exists from the old flow, remove it after the first green
#    Git-free deploy: rm -rf ~/Smartroute (nothing reads it anymore).
```
