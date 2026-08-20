#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

COMPOSE_FILE="${INDUSTRY_COMPOSE_FILE:-compose.production.yaml}"
ENV_FILE="${INDUSTRY_ENV_FILE:-./backend/.env.production}"
export INDUSTRY_ENV_FILE="${ENV_FILE}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or is not on PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "The Docker Compose plugin is required (docker compose)." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing production environment file: ${ENV_FILE}" >&2
  echo "Copy backend/.env.production.example to backend/.env.production and edit it first." >&2
  exit 1
fi

compose=(docker compose -f "${COMPOSE_FILE}")

# Fail before changing running services if the production Compose file is invalid.
"${compose[@]}" config -q

# Build first. A failed build leaves the currently running API untouched.
"${compose[@]}" build --pull api migrate

# PostgreSQL persists in the named volume and is never published to a host port.
"${compose[@]}" up -d postgres

# Migrations are an explicit one-shot gate. If they fail, the new API is not started.
docker compose -f "${COMPOSE_FILE}" --profile maintenance run --rm migrate

# Recreate only the API after a successful build and migration.
"${compose[@]}" up -d --no-deps --force-recreate api

api_id="$("${compose[@]}" ps -q api)"
if [[ -z "${api_id}" ]]; then
  echo "API container was not created." >&2
  exit 1
fi

for _ in $(seq 1 30); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${api_id}")"
  case "${health}" in
    healthy)
      "${compose[@]}" ps
      exit 0
      ;;
    unhealthy)
      echo "API health check failed." >&2
      "${compose[@]}" logs --tail=100 api >&2
      exit 1
      ;;
  esac
  sleep 2
done

echo "API did not become healthy in time." >&2
"${compose[@]}" logs --tail=100 api >&2
exit 1
