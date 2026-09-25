data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  project    = "ai-news-radar"
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = var.region

  # Names that infra/ uses. The CI roles below are scoped to exactly these.
  state_bucket = "${local.project}-tfstate-${local.account_id}"
  state_prefix = "infra/"
  site_bucket  = "${local.project}-site-${local.account_id}"
  table_name   = "ai-news-items"
  # Roles/functions created by the deploy pipeline must use this prefix, which the CI roles
  # themselves ("ai-news-radar-github-*") do not match.
  app_prefix = "${local.project}-app"

  arn = {
    state_bucket = "arn:${local.partition}:s3:::${local.state_bucket}"
    site_bucket  = "arn:${local.partition}:s3:::${local.site_bucket}"
    table        = "arn:${local.partition}:dynamodb:${local.region}:${local.account_id}:table/${local.table_name}"
    functions    = "arn:${local.partition}:lambda:${local.region}:${local.account_id}:function:${local.app_prefix}-*"
    app_roles    = "arn:${local.partition}:iam::${local.account_id}:role/${local.app_prefix}-*"
    log_groups   = "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.app_prefix}-*"
    schedules    = "arn:${local.partition}:scheduler:${local.region}:${local.account_id}:schedule/default/${local.app_prefix}-*"
    topics       = "arn:${local.partition}:sns:${local.region}:${local.account_id}:${local.app_prefix}-*"
    alarms       = "arn:${local.partition}:cloudwatch:${local.region}:${local.account_id}:alarm:${local.app_prefix}-*"
    boundary     = "arn:${local.partition}:iam::${local.account_id}:policy/${local.project}-workload-boundary"
    github_oidc  = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
  }
}
