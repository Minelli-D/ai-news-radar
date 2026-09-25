output "site_url" {
  description = "Public URL of the site."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "Used by the deploy pipeline for its single /* invalidation."
  value       = aws_cloudfront_distribution.site.id
}

output "site_bucket" {
  description = "Private S3 bucket that CloudFront serves from."
  value       = aws_s3_bucket.site.bucket
}

output "collector_function_name" {
  description = "Lambda function invoked by the smoke test."
  value       = aws_lambda_function.collector.function_name
}
