# Collector Errors >= 1 in an hour -> SNS -> email (confirm the subscription email once).
#
# The topic uses no server-side encryption on purpose: CloudWatch alarms cannot publish to a
# topic encrypted with the AWS-managed aws/sns key, and customer-managed KMS keys cost money.

resource "aws_sns_topic" "alerts" {
  name = "${local.app}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "collector_errors" {
  alarm_name        = "${local.app}-collector-errors"
  alarm_description = "The AI News Radar collector failed (infrastructure error or every source failed)."

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.collector.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
