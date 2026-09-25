# EventBridge Scheduler (hourly) -> Lambda "collector": Python 3.12, arm64, 256 MB, 60 s,
# no VPC (no NAT Gateway, no public IPv4 charges), no reserved or provisioned concurrency.

resource "aws_cloudwatch_log_group" "collector" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "collector" {
  name                 = local.function_name
  description          = "AI News Radar collector Lambda"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = local.boundary_arn
}

# Least privilege: its table, the three kinds of objects it publishes, and its own log group.
data "aws_iam_policy_document" "collector" {
  statement {
    sid       = "NewsTable"
    actions   = ["dynamodb:PutItem", "dynamodb:Query"]
    resources = [aws_dynamodb_table.news.arn]
  }

  statement {
    sid     = "PublishDataFiles"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.site.arn}/news.json",
      "${aws_s3_bucket.site.arn}/feed.xml",
      "${aws_s3_bucket.site.arn}/latest/*",
    ]
  }

  statement {
    sid       = "ReadPreviousSnapshot"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/news.json"]
  }

  # Without ListBucket, a missing news.json (first run) is reported as 403 instead of 404.
  statement {
    sid       = "DetectFirstRun"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.site.arn]
  }

  statement {
    sid       = "OwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.collector.arn}:*"]
  }
}

resource "aws_iam_role_policy" "collector" {
  name   = "collector"
  role   = aws_iam_role.collector.id
  policy = data.aws_iam_policy_document.collector.json
}

resource "aws_lambda_function" "collector" {
  function_name    = local.function_name
  description      = "Collects AI news and publishes news.json, feed.xml and latest/*"
  role             = aws_iam_role.collector.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "collector.handler.lambda_handler"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  memory_size      = 256
  timeout          = 60

  environment {
    variables = {
      TABLE_NAME  = aws_dynamodb_table.news.name
      BUCKET_NAME = aws_s3_bucket.site.bucket
      SITE_URL    = "https://${aws_cloudfront_distribution.site.domain_name}"
      REPO_URL    = "https://github.com/${var.github_repository}"
    }
  }

  # One structured JSON line per run is easy to query in CloudWatch Logs Insights.
  logging_config {
    log_format            = "JSON"
    log_group             = aws_cloudwatch_log_group.collector.name
    application_log_level = "INFO"
    system_log_level      = "WARN"
  }

  depends_on = [aws_iam_role_policy.collector]
}

# A failed run is not retried by Lambda: a retry would hit every source again. The next
# hourly run picks everything up.
resource "aws_lambda_function_event_invoke_config" "collector" {
  function_name                = aws_lambda_function.collector.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600
}

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name                 = "${local.app}-scheduler"
  description          = "Lets EventBridge Scheduler invoke the collector"
  assume_role_policy   = data.aws_iam_policy_document.scheduler_trust.json
  permissions_boundary = local.boundary_arn
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.collector.arn, "${aws_lambda_function.collector.arn}:*"]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invoke-collector"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "collector" {
  name                = "${local.app}-hourly"
  group_name          = "default"
  description         = "Runs the AI News Radar collector"
  schedule_expression = var.schedule_expression

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.collector.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}
