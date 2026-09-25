# Least-privilege permissions for the two GitHub Actions roles.
#
# plan   -> read-only, scoped to this project's resource names (PR plans run with -lock=false).
# deploy -> the same reads + writes on exactly the resources infra/ manages.
#
# Privilege-escalation guard: the deploy role may only create/modify IAM roles named
# "ai-news-radar-app-*" that carry the workload permissions boundary below, and may only pass
# them to Lambda and EventBridge Scheduler. It cannot touch its own role, its policies or the
# boundary itself.

data "aws_iam_policy_document" "workload_boundary" {
  statement {
    sid       = "NewsTable"
    actions   = ["dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"]
    resources = [local.arn.table]
  }

  statement {
    sid       = "SiteObjects"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${local.arn.site_bucket}/*"]
  }

  statement {
    sid       = "SiteList"
    actions   = ["s3:ListBucket"]
    resources = [local.arn.site_bucket]
  }

  statement {
    sid       = "OwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.arn.log_groups}:*"]
  }

  statement {
    sid       = "InvokeCollector"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.arn.functions, "${local.arn.functions}:*"]
  }
}

resource "aws_iam_policy" "workload_boundary" {
  name        = "${local.project}-workload-boundary"
  description = "Upper bound for every role the deploy pipeline creates (collector, scheduler)."
  policy      = data.aws_iam_policy_document.workload_boundary.json
}

# --- plan (read-only) ---------------------------------------------------------------------

data "aws_iam_policy_document" "github_read" {
  statement {
    sid       = "ReadInfraState"
    actions   = ["s3:GetObject"]
    resources = ["${local.arn.state_bucket}/${local.state_prefix}*"]
  }

  statement {
    sid       = "ListStateBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.arn.state_bucket]
  }

  statement {
    sid = "DescribeSiteBucket"
    actions = [
      "s3:GetAccelerateConfiguration",
      "s3:GetBucket*",
      "s3:GetEncryptionConfiguration",
      "s3:GetLifecycleConfiguration",
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
    ]
    resources = [local.arn.site_bucket]
  }

  statement {
    sid       = "DescribeTable"
    actions   = ["dynamodb:Describe*", "dynamodb:ListTagsOfResource"]
    resources = [local.arn.table]
  }

  statement {
    sid       = "DescribeFunctions"
    actions   = ["lambda:Get*", "lambda:List*"]
    resources = [local.arn.functions]
  }

  statement {
    sid = "DescribeAppRoles"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
    ]
    resources = [local.arn.app_roles]
  }

  statement {
    sid       = "DescribeSchedules"
    actions   = ["scheduler:GetSchedule"]
    resources = [local.arn.schedules]
  }

  statement {
    sid = "DescribeObservability"
    actions = [
      "cloudwatch:ListTagsForResource",
      "logs:ListTagsForResource",
      "logs:ListTagsLogGroup",
      "sns:GetSubscriptionAttributes",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:ListTagsForResource",
    ]
    resources = [local.arn.alarms, local.arn.log_groups, local.arn.topics]
  }

  statement {
    sid = "DescribeWithoutResourceLevelSupport"
    actions = [
      "cloudfront:Get*",
      "cloudfront:List*",
      "cloudwatch:DescribeAlarms",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "github_read" {
  name        = "${local.project}-github-read"
  description = "Read-only access for terraform plan of infra/ (GitHub Actions)."
  policy      = data.aws_iam_policy_document.github_read.json
}

# --- deploy (writes) ------------------------------------------------------------------------

data "aws_iam_policy_document" "github_deploy_storage" {
  statement {
    sid       = "WriteInfraStateAndLock"
    actions   = ["s3:DeleteObject", "s3:PutObject"]
    resources = ["${local.arn.state_bucket}/${local.state_prefix}*"]
  }

  statement {
    sid       = "ManageSiteBucket"
    actions   = ["s3:*"]
    resources = [local.arn.site_bucket, "${local.arn.site_bucket}/*"]
  }

  statement {
    sid = "ManageNewsTable"
    actions = [
      "dynamodb:CreateTable",
      "dynamodb:DeleteTable",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:UpdateContinuousBackups",
      "dynamodb:UpdateTable",
      "dynamodb:UpdateTimeToLive",
    ]
    resources = [local.arn.table]
  }
}

data "aws_iam_policy_document" "github_deploy_compute" {
  statement {
    sid = "ManageCollectorFunction"
    actions = [
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:DeleteFunctionEventInvokeConfig",
      "lambda:InvokeFunction",
      "lambda:PublishVersion",
      "lambda:PutFunctionEventInvokeConfig",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:UpdateFunctionEventInvokeConfig",
    ]
    resources = [local.arn.functions]
  }

  statement {
    sid       = "ManageSchedules"
    actions   = ["scheduler:CreateSchedule", "scheduler:DeleteSchedule", "scheduler:UpdateSchedule"]
    resources = [local.arn.schedules]
  }

  statement {
    sid = "ManageAppRolesWithinBoundary"
    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePermissionsBoundary",
      "iam:PutRolePolicy",
    ]
    resources = [local.arn.app_roles]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [local.arn.boundary]
    }
  }

  statement {
    sid = "ManageAppRoles"
    actions = [
      "iam:DeleteRole",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRole",
      "iam:UpdateRoleDescription",
    ]
    resources = [local.arn.app_roles]
  }

  statement {
    sid       = "PassAppRolesToLambdaAndScheduler"
    actions   = ["iam:PassRole"]
    resources = [local.arn.app_roles]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "scheduler.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "github_deploy_edge" {
  statement {
    sid = "ManageCloudFront"
    actions = [
      "cloudfront:CreateDistribution",
      "cloudfront:CreateInvalidation",
      "cloudfront:CreateOriginAccessControl",
      "cloudfront:DeleteDistribution",
      "cloudfront:DeleteOriginAccessControl",
      "cloudfront:TagResource",
      "cloudfront:UntagResource",
      "cloudfront:UpdateDistribution",
      "cloudfront:UpdateOriginAccessControl",
    ]
    resources = ["*"] # CloudFront create/list APIs do not support resource-level scoping
  }

  statement {
    sid = "ManageLogGroup"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DeleteRetentionPolicy",
      "logs:PutRetentionPolicy",
      "logs:TagLogGroup",
      "logs:TagResource",
      "logs:UntagLogGroup",
      "logs:UntagResource",
    ]
    resources = [local.arn.log_groups]
  }

  statement {
    sid = "ManageAlertsTopic"
    actions = [
      "sns:CreateTopic",
      "sns:DeleteTopic",
      "sns:SetSubscriptionAttributes",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:TagResource",
      "sns:Unsubscribe",
      "sns:UntagResource",
    ]
    resources = [local.arn.topics]
  }

  statement {
    sid = "ManageAlarms"
    actions = [
      "cloudwatch:DeleteAlarms",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]
    resources = [local.arn.alarms]
  }
}

locals {
  github_deploy_policies = {
    storage = data.aws_iam_policy_document.github_deploy_storage.json
    compute = data.aws_iam_policy_document.github_deploy_compute.json
    edge    = data.aws_iam_policy_document.github_deploy_edge.json
  }
}

resource "aws_iam_policy" "github_deploy" {
  for_each = local.github_deploy_policies

  name        = "${local.project}-github-deploy-${each.key}"
  description = "Write access for the GitHub Actions deploy role (${each.key})."
  policy      = each.value
}

resource "aws_iam_role_policy_attachment" "github_read" {
  for_each = aws_iam_role.github

  role       = each.value.name
  policy_arn = aws_iam_policy.github_read.arn
}

resource "aws_iam_role_policy_attachment" "github_deploy" {
  for_each = aws_iam_policy.github_deploy

  role       = aws_iam_role.github["deploy"].name
  policy_arn = each.value.arn
}
