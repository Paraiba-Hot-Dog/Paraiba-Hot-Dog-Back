#!/usr/bin/env bash
set -euo pipefail

KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://localhost:8080}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-paraiba-hotdog}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-paraiba-hotdog-api}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
KEYCLOAK_TEST_USERNAME="${KEYCLOAK_TEST_USERNAME:-integration-test}"
KEYCLOAK_TEST_PASSWORD="${KEYCLOAK_TEST_PASSWORD:-integration-test}"
KEYCLOAK_TEST_EMAIL="${KEYCLOAK_TEST_EMAIL:-integration-test@example.com}"
KEYCLOAK_TEST_ROLE="${KEYCLOAK_TEST_ROLE:-administrador}"
KEYCLOAK_ACCESS_TOKEN_LIFESPAN="${KEYCLOAK_ACCESS_TOKEN_LIFESPAN:-28800}"

json_field() {
  local field="$1"
  ${PYTHON_BIN} -c "import json, sys; print(json.load(sys.stdin)[\"${field}\"])"
}

json_first_id() {
  ${PYTHON_BIN} -c 'import json, sys; data = json.load(sys.stdin); print(data[0]["id"] if data else "")'
}

admin_token() {
  curl -fsS -X POST \
    "${KEYCLOAK_BASE_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=admin-cli" \
    -d "username=${KEYCLOAK_ADMIN}" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
    -d "grant_type=password" | json_field access_token
}

ensure_realm() {
  local token="$1"
  if curl -fsS "${KEYCLOAK_BASE_URL}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration" >/dev/null 2>&1; then
    return
  fi

  local status
  status="$(
    curl -sS -o /dev/null -w "%{http_code}" -X POST \
      "${KEYCLOAK_BASE_URL}/admin/realms" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "{\"realm\":\"${KEYCLOAK_REALM}\",\"enabled\":true}"
  )"

  if [[ "${status}" != "201" && "${status}" != "409" ]]; then
    echo "Falha ao criar realm ${KEYCLOAK_REALM}. HTTP ${status}" >&2
    exit 1
  fi
}

ensure_role() {
  local token="$1"
  if curl -fsS \
    "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/roles/${KEYCLOAK_TEST_ROLE}" \
    -H "Authorization: Bearer ${token}" >/dev/null 2>&1; then
    return
  fi

  local status
  status="$(
    curl -sS -o /dev/null -w "%{http_code}" -X POST \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/roles" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "{\"name\":\"${KEYCLOAK_TEST_ROLE}\",\"description\":\"Role de teste da API\"}"
  )"

  if [[ "${status}" != "201" && "${status}" != "409" ]]; then
    echo "Falha ao criar role ${KEYCLOAK_TEST_ROLE}. HTTP ${status}" >&2
    exit 1
  fi
}

ensure_token_lifespan() {
  local token="$1"
  curl -fsS -X PUT \
    "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    -d "{\"accessTokenLifespan\":${KEYCLOAK_ACCESS_TOKEN_LIFESPAN}}" >/dev/null
}

ensure_client() {
  local token="$1"
  local client_id
  client_id="$(
    curl -fsS \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients?clientId=${KEYCLOAK_CLIENT_ID}" \
      -H "Authorization: Bearer ${token}" | json_first_id
  )"

  if [[ -n "${client_id}" ]]; then
    return
  fi

  local status
  status="$(
    curl -sS -o /dev/null -w "%{http_code}" -X POST \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "{\"clientId\":\"${KEYCLOAK_CLIENT_ID}\",\"name\":\"${KEYCLOAK_CLIENT_ID}\",\"enabled\":true,\"protocol\":\"openid-connect\",\"publicClient\":true,\"standardFlowEnabled\":true,\"directAccessGrantsEnabled\":true,\"implicitFlowEnabled\":false,\"serviceAccountsEnabled\":false,\"redirectUris\":[\"*\"],\"webOrigins\":[\"*\"]}"
  )"

  if [[ "${status}" != "201" && "${status}" != "409" ]]; then
    echo "Falha ao criar client ${KEYCLOAK_CLIENT_ID}. HTTP ${status}" >&2
    exit 1
  fi
}

ensure_user() {
  local token="$1"
  local user_id
  user_id="$(
    curl -fsS \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/users?username=${KEYCLOAK_TEST_USERNAME}&exact=true" \
      -H "Authorization: Bearer ${token}" | json_first_id
  )"

  if [[ -z "${user_id}" ]]; then
    local status
    status="$(
      curl -sS -o /dev/null -w "%{http_code}" -X POST \
        "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/users" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"${KEYCLOAK_TEST_USERNAME}\",\"email\":\"${KEYCLOAK_TEST_EMAIL}\",\"emailVerified\":true,\"enabled\":true}"
    )"

    if [[ "${status}" != "201" && "${status}" != "409" ]]; then
      echo "Falha ao criar usuario ${KEYCLOAK_TEST_USERNAME}. HTTP ${status}" >&2
      exit 1
    fi

    user_id="$(
      curl -fsS \
        "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/users?username=${KEYCLOAK_TEST_USERNAME}&exact=true" \
        -H "Authorization: Bearer ${token}" | json_first_id
    )"
  fi

  curl -fsS -X PUT \
    "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/users/${user_id}/reset-password" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"password\",\"value\":\"${KEYCLOAK_TEST_PASSWORD}\",\"temporary\":false}" >/dev/null

  local role
  role="$(
    curl -fsS \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/roles/${KEYCLOAK_TEST_ROLE}" \
      -H "Authorization: Bearer ${token}"
  )"

  curl -fsS -X POST \
    "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/users/${user_id}/role-mappings/realm" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    -d "[${role}]" >/dev/null
}

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 nao encontrado no PATH" >&2
  exit 1
fi

docker compose up -d keycloak >/dev/null

for _ in {1..60}; do
  if curl -fsS "${KEYCLOAK_BASE_URL}/realms/master/.well-known/openid-configuration" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -fsS "${KEYCLOAK_BASE_URL}/realms/master/.well-known/openid-configuration" >/dev/null 2>&1; then
  echo "Keycloak nao ficou disponivel em ${KEYCLOAK_BASE_URL}" >&2
  exit 1
fi

token="$(admin_token)"
ensure_realm "${token}"
ensure_token_lifespan "${token}"
ensure_role "${token}"
ensure_client "${token}"
ensure_user "${token}"

response="$(
  curl -fsS -X POST \
    "${KEYCLOAK_BASE_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=${KEYCLOAK_CLIENT_ID}" \
    -d "username=${KEYCLOAK_TEST_USERNAME}" \
    -d "password=${KEYCLOAK_TEST_PASSWORD}" \
    -d "grant_type=password"
)"

json_field access_token <<< "${response}"
