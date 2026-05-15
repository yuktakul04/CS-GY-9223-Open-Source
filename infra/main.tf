terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    render = {
      source  = "render-oss/render"
      version = "~> 1.8"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "render" {}

locals {
  render_non_secret_env_vars = {
    APP_SESSION_TTL_SECONDS = {
      value = tostring(var.app_session_ttl_seconds)
    }
    CHAT_CLIENT_ASSISTANT_PROVIDER = {
      value = var.chat_client_assistant_provider
    }
    CHAT_CLIENT_PROVIDER = {
      value = var.chat_client_provider
    }
    CHAT_CLIENT_STORE_PATH = {
      value = var.chat_client_store_path
    }
    TELEGRAM_POLL_INTERVAL_SECONDS = {
      value = tostring(var.telegram_poll_interval_seconds)
    }
    TELEGRAM_UPDATE_MODE = {
      value = var.telegram_update_mode
    }
  }

  render_optional_secret_env_values = {
    APP_SESSION_SECRET              = var.app_session_secret
    GEMINI_API_KEY                  = var.gemini_api_key
    OPENAI_API_KEY                  = var.openai_api_key
    SLACK_BOT_TOKEN                 = var.slack_bot_token
    TELEGRAM_OIDC_CLIENT_ID         = var.telegram_oidc_client_id
    TELEGRAM_OIDC_CLIENT_SECRET     = var.telegram_oidc_client_secret
    TELEGRAM_WEBHOOK_SECRET         = var.telegram_webhook_secret
    TRELLO_API_KEY                  = var.trello_api_key
    TRELLO_BOARD_ID                 = var.trello_board_id
    TRELLO_TOKEN                    = var.trello_token
  }

  render_secret_env_vars = merge(
    {
      SERVICE_BASE_URL = {
        value = var.service_base_url
      }
      TELEGRAM_BOT_TOKEN = {
        value = var.telegram_bot_token
      }
    },
    {
      for key, value in local.render_optional_secret_env_values : key => {
        value = value
      } if value != null && trimspace(value) != ""
    },
    {
      for key, value in var.render_extra_secret_env_vars : key => {
        value = value
      } if trimspace(value) != ""
    }
  )
}

resource "render_web_service" "chat_client_service" {
  name              = var.render_service_name
  plan              = var.render_service_plan
  region            = var.render_region
  start_command     = var.render_start_command
  health_check_path = var.render_health_check_path

  runtime_source = {
    native_runtime = {
      auto_deploy   = var.render_auto_deploy
      branch        = var.render_repo_branch
      build_command = var.render_build_command
      repo_url      = var.render_repo_url
      runtime       = "python"
    }
  }

  env_vars = merge(
    local.render_non_secret_env_vars,
    local.render_secret_env_vars,
  )

  lifecycle {
    ignore_changes = [
      env_vars,
      log_stream_override,
      max_shutdown_delay_seconds,
      maintenance_mode,
      notification_override,
      num_instances,
      previews,
      root_directory,
      runtime_source.native_runtime.auto_deploy_trigger,
    ]
  }
}

resource "aws_iam_policy" "telemetry_policy" {
  name        = "ChatServiceTelemetryPolicy"
  description = "Allows the chat service to emit logs and metrics to CloudWatch"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Action   = "cloudwatch:PutMetricData"
        Effect   = "Allow"
        Resource = "*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "chat_service_logs" {
  name              = "chat-client-service-logs"
  retention_in_days = 7
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "OSPSD-HW3-ChatService"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            [{ expression = "SEARCH('{OSPSD/HW3, Service, Endpoint} MetricName=\"RequestLatency\" Service=\"chat_client_service\"', 'Average', 60)", label = "$${LABEL} [avg: $${AVG}]", id = "q1", region = var.aws_region }],
          ]
          period = 60
          region = var.aws_region
          title  = "Request Latency (Monitoring Latency)"
          view   = "timeSeries"
          yAxis = {
            left = {
              label     = "Count"
              showUnits = false
            }
          }
          stat = "Average"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            [{ expression = "SEARCH('{OSPSD/HW3, Service, Endpoint} MetricName=\"SuccessRate\" Service=\"chat_client_service\"', 'Sum', 60)", label = "Successes", id = "q1", region = var.aws_region }],
            [{ expression = "SEARCH('{OSPSD/HW3, Service, Endpoint} MetricName=\"FailureRate\" Service=\"chat_client_service\"', 'Sum', 60)", label = "Failures", id = "q2", region = var.aws_region }],
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Service Health: Success vs Failure Rate (Health Monitoring)"
          yAxis = {
            left = {
              label     = "Count"
              showUnits = false
            }
          }
          stat   = "Average"
          period = 300
        }
      },
    ]
  })
}
