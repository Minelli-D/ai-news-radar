output "state_bucket" {
  description = "Remote-state bucket for infra/ (backend key: infra/terraform.tfstate)."
  value       = aws_s3_bucket.state.bucket
}

output "workload_boundary_policy_arn" {
  description = "Permissions boundary that every role created by infra/ must use."
  value       = aws_iam_policy.workload_boundary.arn
}

output "github_actions_variables" {
  description = "Set these as GitHub repository variables (Settings > Secrets and variables > Actions > Variables)."
  value = {
    AWS_REGION          = var.region
    AWS_PLAN_ROLE_ARN   = aws_iam_role.github["plan"].arn
    AWS_DEPLOY_ROLE_ARN = aws_iam_role.github["deploy"].arn
    TF_STATE_BUCKET     = aws_s3_bucket.state.bucket
  }
}
