#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/v1/healthz}"
MAX_HEALTH_RETRIES="${MAX_HEALTH_RETRIES:-30}"
HEALTH_SLEEP_SECONDS="${HEALTH_SLEEP_SECONDS:-2}"
ROLLBACK_FILE=".last_successful_tag"

cleanup() {
  docker logout ghcr.io >/dev/null 2>&1 || true
}
trap cleanup EXIT

require_env() {
  local var_name="$1"
  if [[ -z "${!var_name:-}" ]]; then
    echo "ERROR: Required environment variable '$var_name' is not set."
    exit 1
  fi
}

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    echo "ERROR: Required file '$file_path' does not exist."
    exit 1
  fi
}

wait_for_health() {
  local label="$1"
  echo "==> Waiting for health ($label): $HEALTH_URL"
  for ((i=1; i<=MAX_HEALTH_RETRIES; i++)); do
    if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
      echo "Health check passed ($label)."
      return 0
    fi
    echo "Attempt $i/$MAX_HEALTH_RETRIES failed. Retrying in ${HEALTH_SLEEP_SECONDS}s..."
    sleep "$HEALTH_SLEEP_SECONDS"
  done
  return 1
}

rollback() {
  if [[ ! -f "$ROLLBACK_FILE" ]]; then
    echo "ERROR: No previous successful tag found. Cannot rollback."
    echo "==> API is DOWN. Manual intervention required."
    return 1
  fi

  local prev_tag
  prev_tag=$(cat "$ROLLBACK_FILE")
  echo "==> ROLLING BACK to previous tag: $prev_tag"

  export IMAGE_TAG="$prev_tag"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull api
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps api

  if wait_for_health "rollback"; then
    echo "==> Rollback succeeded. API is running on $prev_tag"
    return 0
  else
    echo "ERROR: Rollback ALSO failed. API is DOWN. Manual intervention required."
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=50 api || true
    return 1
  fi
}

# ── Validation ──

echo "==> Validating environment"
require_env DEPLOY_PATH
require_env IMAGE_NAME
require_env IMAGE_TAG
require_env GHCR_USERNAME
require_env GHCR_PULL_TOKEN

cd "$DEPLOY_PATH/infra"

# Prevent inherited shell/session env vars from overriding .env values
unset DATABASE_URL

require_file "$COMPOSE_FILE"
require_file "$ENV_FILE"

require_file "$COMPOSE_FILE"
require_file "$ENV_FILE"

echo "==> Deploying image ${IMAGE_NAME}:${IMAGE_TAG}"

# ── GHCR login ──

echo "==> Logging in to GHCR"
printf '%s' "$GHCR_PULL_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin

export IMAGE_NAME
export IMAGE_TAG

# ── Pull ──

echo "==> Pulling target image"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull api

# ── Redis ──

echo "==> Ensuring Redis is running"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d redis

# ── Migrations ──

echo "==> Running Alembic migrations"
if ! docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm api alembic upgrade head; then
  echo "ERROR: Alembic migration failed. Aborting deploy (no container change)."
  echo "==> Current API container is still running on previous version."
  exit 1
fi

# ── Deploy ──

echo "==> Restarting API container"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps api

# ── Health check ──

if wait_for_health "new deploy"; then
  echo "==> Deploy succeeded."

  # Spara lyckad tag for framtida rollback
  echo "$IMAGE_TAG" > "$ROLLBACK_FILE"
  echo "==> Saved $IMAGE_TAG as last successful tag."

  echo "==> Container status"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps || true

  echo "==> Cleaning up unused Docker images"
  docker image prune -f || true

  exit 0
fi

# ── Health check failed -- rollback ──

echo "ERROR: Health check failed after $MAX_HEALTH_RETRIES attempts."
echo "==> Recent logs from failed container:"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=50 api || true

rollback
ROLLBACK_EXIT=$?

# Visa slutstatus oavsett
echo "==> Container status"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps || true

if [[ $ROLLBACK_EXIT -eq 0 ]]; then
  # Rollback lyckades -- API ar uppe men pa gamla versionen.
  # Exit 1 sa att GitHub Actions visar rott (deployen misslyckades).
  echo "==> Deploy FAILED but rollback succeeded. API is running on previous version."
  exit 1
else
  echo "==> Deploy FAILED and rollback FAILED. API may be DOWN."
  exit 2
fi