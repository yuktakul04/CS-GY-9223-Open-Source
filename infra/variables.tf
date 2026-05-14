variable "aws_region" {
  description = "AWS region for CloudWatch telemetry resources."
  type        = string
  default     = "us-east-1"
}

variable "render_service_name" {
  description = "Render web service name."
  type        = string
  default     = "chat-client-service"
}

variable "render_service_plan" {
  description = "Render web service instance type. Set this explicitly for your workspace before apply."
  type        = string
}

variable "render_region" {
  description = "Render region for the web service."
  type        = string
  default     = "virginia"
}

variable "render_repo_url" {
  description = "Git repository URL Render should build from."
  type        = string
  default     = "https://github.com/yuktakul04/CS-GY-9223-Open-Source"
}

variable "render_repo_branch" {
  description = "Git branch Render should deploy."
  type        = string
  default     = "main"
}

variable "render_auto_deploy" {
  description = "Whether Render automatically redeploys on branch pushes and service config changes."
  type        = bool
  default     = true
}

variable "render_build_command" {
  description = "Build command for the Render web service."
  type        = string
  default     = "python -m pip install --upgrade pip && python -m pip install -r requirements-render.txt"
}

variable "render_start_command" {
  description = "Start command for the Render web service."
  type        = string
  default     = "python -m uvicorn chat_client_service.app:app --host 0.0.0.0 --port $PORT"
}

variable "render_health_check_path" {
  description = "Health check path monitored by Render."
  type        = string
  default     = "/health"
}

variable "chat_client_assistant_provider" {
  description = "Configured AI assistant provider when explicitly pinned."
  type        = string
  default     = "gemini"
}

variable "chat_client_provider" {
  description = "Configured chat provider for the shared ChatClient API."
  type        = string
  default     = "telegram"
}

variable "chat_client_store_path" {
  description = "Writable path for the local SQLite store on Render."
  type        = string
  default     = "/tmp/chat_client.sqlite3"
}

variable "telegram_update_mode" {
  description = "Telegram update mode."
  type        = string
  default     = "polling"
}

variable "telegram_poll_interval_seconds" {
  description = "Telegram polling interval in seconds."
  type        = number
  default     = 3
}

variable "app_session_ttl_seconds" {
  description = "Local session TTL in seconds."
  type        = number
  default     = 3600
}

variable "telegram_bot_token" {
  description = "Telegram bot token pushed to Render at apply time."
  type        = string
  sensitive   = true
}

variable "service_base_url" {
  description = "Public base URL for the deployed service."
  type        = string
  sensitive   = true
}

variable "app_session_secret" {
  description = "Optional override for local session signing secret."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "gemini_api_key" {
  description = "Optional Gemini API key."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "openai_api_key" {
  description = "Optional OpenAI API key."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "slack_bot_token" {
  description = "Optional Slack bot token for the Slack ChatClient provider."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "chat_client_allowed_channel_ids" {
  description = "Optional comma-separated allowlist for provider-neutral /chat channel access."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "trello_api_key" {
  description = "Optional Trello API key."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "trello_token" {
  description = "Optional Trello token."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "trello_board_id" {
  description = "Optional Trello board id."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "telegram_oidc_client_id" {
  description = "Optional Telegram OIDC client id override."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "telegram_oidc_client_secret" {
  description = "Optional Telegram OIDC client secret."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "telegram_webhook_secret" {
  description = "Optional Telegram webhook secret."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "render_extra_secret_env_vars" {
  description = "Additional secret environment variables to push to Render at apply time."
  type        = map(string)
  sensitive   = true
  default     = {}
}
