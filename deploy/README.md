# Production deploy — Docker Hub + EC2 + Secrets Manager

Dev workflow is unchanged: `docker compose up --build` still uses
`docker-compose.yml` + `backend/.env` + `frontend/.env`.

Production uses **separate** files and never builds on EC2:

- `docker-compose.prod.yml` — pulls immutable
  `<NAMESPACE>/smartroute-api:<SHA>` and `<NAMESPACE>/smartroute-frontend:<SHA>`
- `deploy/deploy.sh` — pull → secrets → migrate → up → healthcheck → rollback
- `.github/workflows/ci-cd.yml` — lint/test/build, push, SSH deploy

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
| `EC2_PROJECT_DIR` | `~/Smartroute` | Repo checkout path on EC2 (default if unset) |

Backend runtime secrets are **not** in GitHub. EC2 reads them from Secrets Manager.

Also create the `production` Environment (for approval rules, optional) because
the `deploy-prod` job references `environment: production`.

## 2. EC2 configuration (one-time)

1. Ubuntu 22.04/24.04, Docker Engine + Compose plugin, AWS CLI v2, `git`, `python3`.
2. Attach an **IAM instance profile** with only:
   `secretsmanager:GetSecretValue` on the backend secret (see §3).
   No long-lived AWS keys on EC2.
3. Clone the repo to `$EC2_PROJECT_DIR`, checkout `main`, ensure
   `docker-compose.prod.yml` + `deploy/deploy.sh` exist.
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
  "CLERK_AUTHORIZED_PARTIES": "https://app.example.com"
}
```

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
   `: <short-sha>` and `:latest`. Deploy uses the SHA only.
3. `deploy-prod` (env `production`, concurrency `production`): SSH to EC2,
   `git fetch/pull main`, `./deploy/deploy.sh <short-sha>`:
   pull exact images → fetch secret JSON → write `deploy/.env.prod` (0600) →
   `docker run --rm ... alembic upgrade head` (new image) →
   `docker compose -f docker-compose.prod.yml up -d` →
   poll `frontend /health`, `api /health/live`, `api /health/ready` (180s).
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
- Manual rollback: `DOCKERHUB_NAMESPACE=<ns> IMAGE_TAG=<prev-sha> ./deploy/deploy.sh <prev-sha>`
  or `DOCKERHUB_NAMESPACE=<ns> IMAGE_TAG=<prev-sha> docker compose -f docker-compose.prod.yml up -d`.

## 6. First production deployment (safe order)

```bash
# 1. Create Secrets Manager JSON secret, Docker Hub repos, GitHub secrets/vars above.
# 2. Merge to main (current dev branch is `features`):
git checkout main && git merge features && git push origin main
# 3. Watch Actions → CI/CD → docker-push → deploy-prod.
# 4. On EC2 (if SSH deploy not yet wired), run manually once:
cd ~/Smartroute && git pull --ff-only origin main
export DOCKERHUB_NAMESPACE=<ns> AWS_REGION=<region>
./deploy/deploy.sh <short-sha-from-CI>
# 5. Configure NPM hosts, verify https app + api docs, then leave CI to handle the rest.
```
