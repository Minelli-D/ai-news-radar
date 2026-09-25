data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  project    = "ai-news-radar"
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  # These names are what the bootstrap CI roles are scoped to: keep them in sync.
  app           = "${local.project}-app"
  site_bucket   = "${local.project}-site-${local.account_id}"
  table_name    = "ai-news-items"
  function_name = "${local.app}-collector"
  boundary_arn  = "arn:${local.partition}:iam::${local.account_id}:policy/${local.project}-workload-boundary"
}
