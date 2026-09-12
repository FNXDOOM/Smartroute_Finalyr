#!/usr/bin/env bash
#
# SmartRouteAI — EC2 production deploy script.
#
# Called by GitHub Actions AFTER images are pushed to Docker Hub:
#   ./deploy/deploy.sh <IMAGE_TAG>
#
# What it does:
#   1. Pulls exact immutable images (never :latest):
#        $DOCKERHUB_NAMESPACE/smartroute-api:$IMAGE_TAG
#        $DOCKERHUB_NAMESPACE/smartroute-frontend:$IMAGE_TAG
#   2. Fetches backend runtime secrets from AWS Secrets Manager using the
#      EC2 instance IAM role (no AWS keys on EC2, no secrets in git/CI/images).
#   3. Writes deploy/.env.prod with mode 0600 (no secret values in logs).
#   4. Runs `alembic upgrade head` in a one-off container from the NEW image.
#   5. Starts api + worker + frontend with docker-compose.prod.yml.
#   6. Health-checks frontend /health, api /health/live, api /health/ready.
#   7. On failure: restores previous IMAGE_TAG and brings it back up.
#
# Database rollback policy (deliberate):
#   - Migrations run FORWARD ONLY (`upgrade head`). Never `downgrade`.
#   - If the new image fails healthchecks AFTER a successful migration,
#     we roll back the CONTAINERS to the previous image but LEAVE the DB
#     migrated forward, because down-migrations are not tested and can
#     destroy data. Old code is expected to tolerate new nullable columns
#     (the pattern used in this repo). If a migration is destructive
#     (drop/rename/not-null), do NOT auto-deploy — run it manually with a
#     tested backward plan.
#
# Required on EC2:
#   - Docker Engine + Compose plugin, AWS CLI v2, jq NOT required (python3 used).
#   - IAM instance profile with secretsmanager:GetSecretValue on the secret.
#   - This repo checked out at the production branch (compose file read here).
#   - Env: DOCKERHUB_NAMESPACE, IMAGE_TAG (arg or env).
#     Optional: BACKEND_SECRET_ID (default smartroute/production/backend),
#               AWS_REGION (auto-detected via IMDSv2 if unset).
#
# Secrets Manager layout (single JSON secret — atomic, one fetch):
#   Secret ID: $BACKEND_SECRET_ID (default: smartroute/production/backend)
#   SecretString (JSON object, keys = env var names). Required keys:
#     DATABASE_URL, CLERK_JWKS_URL, CLERK_ISSUER, CLERK_SECRET_KEY,
#     STADIA_API_KEY, LOCAL_JWT_SECRET, ALLOWED_ORIGINS, CLERK_AUTHORIZED_PARTIES
#   Optional keys (sane prod defaults applied if absent):
#     APP_ENV, AUTH_PROVIDER, CLERK_AUDIENCE, CLERK_ALLOW_NATIVE_CLIENTS,
#     LOCAL_JWT_EXPIRES_MINUTES, LOG_LEVEL, ENABLE_BACKGROUND_JOBS_IN_API,
#     STADIA_GEOCODER_URL, STADIA_ROUTER_URL, STADIA_MATRIX_URL,
#     STADIA_NEAREST_ROADS_URL, STADIA_MAP_MATCH_URL,
#     STADIA_ROUTING_COSTING, STADIA_TILES_URL, STADIA_MAP_STYLE_PATH
#   See backend/config.py for the authoritative list. Frontend VITE_* vars are
#   NOT in this secret — they are baked at `docker build` time in CI.
#
set -euo pipefail
# Never enable `set -x`: it would leak secrets if any command expanded them.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-deploy/.env.prod}"
STATE_FILE="${STATE_FILE:-deploy/.last-good-tag}"
BACKEND_SECRET_ID="${BACKEND_SECRET_ID:-smartroute/production/backend}"

IMAGE_TAG="${1:-${IMAGE_TAG:-}}"
DOCKERHUB_NAMESPACE="${DOCKERHUB_NAMESPACE:-}"

if [[ -z "${IMAGE_TAG}" ]]; then
  echo "ERROR: IMAGE_TAG is required. Usage: ./deploy/deploy.sh <short-git-sha>" >&2
  exit 2
fi
if [[ "${IMAGE_TAG}" == "latest" ]]; then
  echo "ERROR: refusing to deploy ':latest'. Use an immutable git SHA tag." >&2
  exit 2
fi
if [[ -z "${DOCKERHUB_NAMESPACE}" ]]; then
  echo "ERROR: DOCKERHUB_NAMESPACE is required (e.g. export DOCKERHUB_NAMESPACE=myorg)." >&2
  exit 2
fi

API_IMAGE="${DOCKERHUB_NAMESPACE}/smartroute-api:${IMAGE_TAG}"
FRONTEND_IMAGE="${DOCKERHUB_NAMESPACE}/smartroute-frontend:${IMAGE_TAG}"

# Resolve AWS region without requiring long-lived keys.
if [[ -z "${AWS_REGION:-}" ]]; then
  AWS_REGION="$(aws configure get region 2>/dev/null || true)"
fi
if [[ -z "${AWS_REGION:-}" ]]; then
  # IMDSv2 for EC2 region.
  IMDS_TOKEN="$(curl -sS -m 3 -X PUT 'http://169.254.169.254/latest/api/token' -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' || true)"
  if [[ -n "${IMDS_TOKEN}" ]]; then
    AZ="$(curl -sS -m 3 -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" http://169.254.169.254/latest/meta-data/placement/availability-zone || true)"
    AWS_REGION="${AZ%[a-z]}"
  fi
fi
if [[ -z "${AWS_REGION:-}" ]]; then
  echo "ERROR: AWS_REGION is not set and could not be auto-detected. Export AWS_REGION." >&2
  exit 2
fi
export AWS_REGION

echo "Deploying IMAGE_TAG=${IMAGE_TAG} from namespace=${DOCKERHUB_NAMESPACE} (region=${AWS_REGION})"

# --- Record previous tag for rollback (before pulling anything new). ---
PREV_TAG=""
if [[ -f "${STATE_FILE}" ]]; then
  PREV_TAG="$(tr -d ' \t\r\n' < "${STATE_FILE}" || true)"
fi
if [[ -z "${PREV_TAG}" ]]; then
  # Fall back to the currently running api image tag, if any.
  PREV_TAG="$(docker inspect --format '{{.Config.Image}}' "$(docker compose -f "${COMPOSE_FILE}" ps -q api 2>/dev/null || true)" 2>/dev/null | rev | cut -d: -f1 | rev || true)"
  if [[ "${PREV_TAG}" == "latest" || "${PREV_TAG}" == *"{{"* ]]; then
    PREV_TAG=""
  fi
fi
if [[ -n "${PREV_TAG}" ]]; then
  echo "Previous tag for rollback: ${PREV_TAG}"
else
  echo "No previous tag found (first deployment). Rollback will be skipped if this fails."
fi

compose() {
  DOCKERHUB_NAMESPACE="${DOCKERHUB_NAMESPACE}" IMAGE_TAG="${IMAGE_TAG}" \
    docker compose -f "${COMPOSE_FILE}" "$@"
}

compose_with_tag() {
  local tag="$1"; shift
  DOCKERHUB_NAMESPACE="${DOCKERHUB_NAMESPACE}" IMAGE_TAG="${tag}" \
    docker compose -f "${COMPOSE_FILE}" "$@"
}

rollback() {
  local failed_tag="$1"
  echo "Deployment of ${failed_tag} FAILED — starting rollback." >&2
  if [[ -z "${PREV_TAG}" ]]; then
    echo "No previous tag recorded; leaving failed containers for inspection. DB migrations (if any) are LEFT applied (forward-only policy)." >&2
    return 1
  fi
  if [[ "${PREV_TAG}" == "${failed_tag}" ]]; then
    echo "Previous tag equals failed tag; nothing to roll back to." >&2
    return 1
  fi
  echo "Restoring previous tag: ${PREV_TAG}"
  # Previous images are kept on EC2 (see prune step); pull as fallback in case
  # the local copy was pruned, but never rebuild.
  docker pull "${DOCKERHUB_NAMESPACE}/smartroute-api:${PREV_TAG}" || true
  docker pull "${DOCKERHUB_NAMESPACE}/smartroute-frontend:${PREV_TAG}" || true
  if compose_with_tag "${PREV_TAG}" up -d; then
    echo "Previous containers restarted. Re-checking health on ${PREV_TAG}..."
    if healthcheck_all; then
      echo "Rollback to ${PREV_TAG} succeeded. DB stays on forward migration (no downgrade)."
      return 0
    fi
    echo "Rollback containers also unhealthy — needs manual intervention." >&2
  fi
  return 1
}

# --- Health checks (container-internal, no host ports needed). ---
# api/frontend expose ports internally only; NPM owns host 80/443.
check_frontend_health() {
  compose exec -T frontend wget -qO- http://localhost/health 2>/dev/null | grep -q "ok"
}

check_api_live() {
  compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/live', timeout=5).read().decode())" 2>/dev/null | grep -q '"status"'
}

check_api_ready() {
  # /health/ready hits the DB (SELECT 1). 503 => DB unreachable.
  compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready', timeout=10).read().decode())" 2>/dev/null | grep -q '"database"'
}

healthcheck_all() {
  local timeout_s="${1:-180}" elapsed=0
  echo "Waiting for services to become healthy (up to ${timeout_s}s)..."
  while [[ "${elapsed}" -lt "${timeout_s}" ]]; do
    if check_frontend_health && check_api_live && check_api_ready; then
      echo "Healthy: frontend /health OK, api /health/live OK, api /health/ready OK."
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  echo "Health checks did not pass within ${timeout_s}s." >&2
  echo "--- compose ps ---" >&2
  compose ps >&2 || true
  echo "--- api logs (tail) ---" >&2
  compose logs --tail=50 api >&2 || true
  return 1
}

prune_old_images() {
  # Keep at least the current + previous 2 images per repo; never fail deploy.
  echo "Pruning Docker images older than the 3 most recent per repo..."
  for repo in "${DOCKERHUB_NAMESPACE}/smartroute-api" "${DOCKERHUB_NAMESPACE}/smartroute-frontend"; do
    ids_to_remove="$(docker images --format '{{.Repository}} {{.Tag}} {{.ID}} {{.CreatedAt}}' \
      | grep "^${repo} " | grep -v " latest$" | sort -rk4 | awk 'NR>3 {print $3}' || true)"
    if [[ -n "${ids_to_remove}" ]]; then
      echo "${ids_to_remove}" | xargs -r docker rmi || true
    fi
  done
  docker image prune -f || true
}

# --- 1. Pull exact images. ---
echo "Pulling ${API_IMAGE}"
docker pull "${API_IMAGE}"
echo "Pulling ${FRONTEND_IMAGE}"
docker pull "${FRONTEND_IMAGE}"

# --- 2-3. Fetch secrets + write env file (0600, no values in logs). ---
echo "Fetching production secrets from Secrets Manager: ${BACKEND_SECRET_ID}"
umask 077
TMP_SECRET="$(mktemp)"
TMP_ENV="$(mktemp)"
trap 'rm -f "${TMP_SECRET}" "${TMP_ENV}"' EXIT

if ! aws secretsmanager get-secret-value \
    --secret-id "${BACKEND_SECRET_ID}" \
    --query SecretString --output text > "${TMP_SECRET}" 2>"${TMP_ENV}.awserr"; then
  echo "ERROR: failed to fetch secret ${BACKEND_SECRET_ID}. Check IAM instance profile (secretsmanager:GetSecretValue) and region." >&2
  cat "${TMP_ENV}.awserr" >&2 || true
  rm -f "${TMP_ENV}.awserr"
  exit 1
fi
rm -f "${TMP_ENV}.awserr"

# Validate + render env file with python (avoids jq dependency, safe quoting).
if ! python3 - "${TMP_SECRET}" "${TMP_ENV}" <<'PYEOF'
import json, sys

required = [
    "DATABASE_URL",
    "CLERK_JWKS_URL",
    "CLERK_ISSUER",
    "CLERK_SECRET_KEY",
    "STADIA_API_KEY",
    "LOCAL_JWT_SECRET",
    "ALLOWED_ORIGINS",
    "CLERK_AUTHORIZED_PARTIES",
]
defaults = {
    "APP_ENV": "production",
    "AUTH_PROVIDER": "clerk",
    "CLERK_ALLOW_NATIVE_CLIENTS": "false",
    "LOCAL_JWT_EXPIRES_MINUTES": "10080",
    "LOG_LEVEL": "INFO",
    "ENABLE_BACKGROUND_JOBS_IN_API": "false",
    "STADIA_GEOCODER_URL": "https://api.stadiamaps.com/geocoding/v1",
    "STADIA_ROUTER_URL": "https://api.stadiamaps.com/route/v1",
    "STADIA_MATRIX_URL": "https://api.stadiamaps.com/matrix/v1",
    "STADIA_NEAREST_ROADS_URL": "https://api.stadiamaps.com/nearest_roads/v1",
    "STADIA_MAP_MATCH_URL": "https://api.stadiamaps.com/map_match/v1",
    "STADIA_ROUTING_COSTING": "auto",
    "STADIA_TILES_URL": "https://tiles.stadiamaps.com",
    "STADIA_MAP_STYLE_PATH": "styles/alidade_smooth.json",
}

src, dst = sys.argv[1], sys.argv[2]
with open(src, encoding="utf-8") as fh:
    raw = fh.read().strip()
try:
    data = json.loads(raw)
    if isinstance(data, str):  # secret stored as JSON-encoded string
        data = json.loads(data)
except json.JSONDecodeError as exc:
    print(f"ERROR: secret is not valid JSON: {exc}", file=sys.stderr)
    sys.exit(1)
if not isinstance(data, dict):
    print("ERROR: secret JSON must be an object of KEY: value.", file=sys.stderr)
    sys.exit(1)

missing = [k for k in required if not str(data.get(k, "")).strip()]
if missing:
    print(f"ERROR: secret {sys.argv[0]} missing required keys: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)
if str(data.get("LOCAL_JWT_SECRET", "")).strip() in ("", "dev-only-change-me-in-production"):
    print("ERROR: LOCAL_JWT_SECRET is missing or still the dev placeholder.", file=sys.stderr)
    sys.exit(1)
for key in ("ALLOWED_ORIGINS", "CLERK_AUTHORIZED_PARTIES"):
    val = str(data.get(key, ""))
    if "localhost" in val or "127.0.0.1" in val:
        print(f"ERROR: {key} must be the public https domain, not localhost.", file=sys.stderr)
        sys.exit(1)
    if "https://" not in val:
        print(f"ERROR: {key} must contain an https:// origin in production.", file=sys.stderr)
        sys.exit(1)

merged = {**defaults, **{k: str(v) for k, v in data.items() if v is not None}}
merged["APP_ENV"] = "production"  # enforce; compose also sets it
# PROCESS_ROLE / ENABLE_TRACKING_BROADCAST are set per-service in compose.

def clean(v: str) -> str:
    return v.replace("\r\n", "\n").strip().replace("\n", " ")

with open(dst, "w", encoding="utf-8", newline="\n") as fh:
    for key in sorted(merged):
        fh.write(f"{key}={clean(merged[key])}\n")
PYEOF
then
  echo "ERROR: secret validation failed (see message above). Aborting before migrations." >&2
  exit 1
fi

mkdir -p "$(dirname "${ENV_FILE}")"
chmod 600 "${TMP_ENV}"
mv "${TMP_ENV}" "${ENV_FILE}"
chmod 600 "${ENV_FILE}"
trap - EXIT
rm -f "${TMP_SECRET}"
echo "Wrote ${ENV_FILE} (mode 0600)."

# --- 4. Migrations with the NEW image, before switching traffic. ---
echo "Running alembic upgrade head with ${API_IMAGE}..."
if ! docker run --rm --env-file "${ENV_FILE}" "${API_IMAGE}" alembic upgrade head; then
  echo "ERROR: migrations failed. Aborting without restarting containers." >&2
  exit 1
fi
echo "Migrations complete."

# --- 5. Start/update containers. ---
echo "Starting containers with IMAGE_TAG=${IMAGE_TAG}..."
if ! compose up -d; then
  echo "ERROR: docker compose up failed." >&2
  rollback "${IMAGE_TAG}" || exit 1
  exit 1
fi

# --- 6. Health checks; rollback containers (not DB) on failure. ---
if ! healthcheck_all 180; then
  rollback "${IMAGE_TAG}" || exit 1
  # rollback() succeeded but the new version failed: still exit non-zero so CI is red.
  echo "Rolled back to ${PREV_TAG}; new version ${IMAGE_TAG} did not pass health checks." >&2
  exit 1
fi

# --- 7. Record success + retain images for future rollback. ---
echo -n "${IMAGE_TAG}" > "${STATE_FILE}"
chmod 600 "${STATE_FILE}" || true
prune_old_images
echo "Deployment successful: ${IMAGE_TAG}"
