variable "region" {
  description = "AWS Region for the project."
  type        = string
  default     = "eu-north-1"
}

variable "github_repository" {
  description = "GitHub repository (owner/name) whose workflows may assume the CI roles."
  type        = string
  default     = "Minelli-D/ai-news-radar"

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "Use the owner/name form, e.g. Minelli-D/ai-news-radar."
  }
}

variable "alert_email" {
  description = "Email address for AWS Budgets alerts (keep it in terraform.tfvars, which is git-ignored)."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD for the whole account; alerts at 50% and 100%."
  type        = number
  default     = 5
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set to false if the account already has one for token.actions.githubusercontent.com (only one per URL is allowed)."
  type        = bool
  default     = true
}
