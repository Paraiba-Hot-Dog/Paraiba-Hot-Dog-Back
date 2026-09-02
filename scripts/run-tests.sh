#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://localhost:8080}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-paraiba-hotdog}"

wait_for_url() {
  local name="$1"
  local url="$2"

  for _ in {1..60}; do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done

  echo "${name} nao ficou disponivel em ${url}" >&2
  exit 1
}

docker compose up -d --build paraiba-hotdog-back keycloak

wait_for_url "API" "${API_BASE_URL}/"
wait_for_url \
  "Keycloak" \
  "${KEYCLOAK_BASE_URL}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"

export API_AUTH_TOKEN
API_AUTH_TOKEN="$(scripts/keycloak-token.sh)"

API_BASE_URL="${API_BASE_URL}" poetry run pytest --cov=src --cov-report=term-missing "$@"
