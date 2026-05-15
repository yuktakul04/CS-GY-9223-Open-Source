#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${ENV_FILE:-$repo_root/.env}"

if [[ ! -f "$env_file" ]]; then
  echo "Environment file not found: $env_file" >&2
  exit 1
fi

set -a
source "$env_file"
set +a

map_tf_var() {
  local tf_name="$1"
  local simple_name="$2"
  local current_tf_name="TF_VAR_${tf_name}"
  local simple_value="${!simple_name:-}"
  local tf_value="${!current_tf_name:-}"

  if [[ -n "$tf_value" || -z "$simple_value" ]]; then
    return
  fi

  export "${current_tf_name}=$simple_value"
}

map_tf_var "render_service_plan" "RENDER_SERVICE_PLAN"
map_tf_var "render_repo_url" "RENDER_REPO_URL"
map_tf_var "render_repo_branch" "RENDER_REPO_BRANCH"
map_tf_var "telegram_bot_token" "TELEGRAM_BOT_TOKEN"
map_tf_var "service_base_url" "SERVICE_BASE_URL"
map_tf_var "gemini_api_key" "GEMINI_API_KEY"
map_tf_var "openai_api_key" "OPENAI_API_KEY"
map_tf_var "app_session_secret" "APP_SESSION_SECRET"
map_tf_var "telegram_oidc_client_id" "TELEGRAM_OIDC_CLIENT_ID"
map_tf_var "telegram_oidc_client_secret" "TELEGRAM_OIDC_CLIENT_SECRET"
map_tf_var "telegram_webhook_secret" "TELEGRAM_WEBHOOK_SECRET"
map_tf_var "trello_api_key" "TRELLO_API_KEY"
map_tf_var "trello_token" "TRELLO_TOKEN"
map_tf_var "trello_board_id" "TRELLO_BOARD_ID"
map_tf_var "chat_client_assistant_provider" "CHAT_CLIENT_ASSISTANT_PROVIDER"
map_tf_var "chat_client_store_path" "CHAT_CLIENT_STORE_PATH"
map_tf_var "telegram_update_mode" "TELEGRAM_UPDATE_MODE"
map_tf_var "telegram_poll_interval_seconds" "TELEGRAM_POLL_INTERVAL_SECONDS"
map_tf_var "app_session_ttl_seconds" "APP_SESSION_TTL_SECONDS"

missing=()

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
}

require_var "RENDER_API_KEY"
require_var "RENDER_OWNER_ID"
require_var "TF_VAR_render_service_plan"
require_var "TF_VAR_telegram_bot_token"
require_var "TF_VAR_service_base_url"

if [[ -z "${TF_VAR_gemini_api_key:-}" && -z "${TF_VAR_openai_api_key:-}" ]]; then
  missing+=("TF_VAR_gemini_api_key or TF_VAR_openai_api_key")
fi

if (( ${#missing[@]} > 0 )); then
  printf 'Missing required environment values:\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

if (( $# == 0 )); then
  echo "Usage: scripts/terraform-with-env.sh <terraform args>" >&2
  exit 1
fi

terraform -chdir="$repo_root/infra" "$@"
