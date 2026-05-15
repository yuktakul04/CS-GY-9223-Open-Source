output "render_service_id" {
  description = "Render service identifier."
  value       = render_web_service.chat_client_service.id
}

output "render_service_slug" {
  description = "Render service slug."
  value       = render_web_service.chat_client_service.slug
}

output "render_service_url" {
  description = "Render service URL."
  value       = render_web_service.chat_client_service.url
}

output "cloudwatch_dashboard_name" {
  description = "CloudWatch dashboard name for the deployed service."
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}
