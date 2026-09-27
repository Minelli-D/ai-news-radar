variable "region" {
  description = "AWS Region (must match bootstrap)."
  type        = string
  default     = "eu-north-1"
}

variable "alert_email" {
  description = "Email subscribed to the collector error alarm (confirm the SNS email once)."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "github_repository" {
  description = "owner/name of the GitHub repository (used in the collector's User-Agent)."
  type        = string
  default     = "Minelli-D/ai-news-radar"
}

variable "lambda_zip_path" {
  description = "Path to the collector package built by scripts/build_lambda.py."
  type        = string
  default     = "../build/collector.zip"
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression for the collector."
  type        = string
  default     = "rate(1 hour)"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the collector."
  type        = number
  default     = 7
}
