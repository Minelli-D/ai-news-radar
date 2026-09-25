# Default *.cloudfront.net domain (no custom domain, Route 53 or ACM), PriceClass_100,
# pay-as-you-go: our traffic is ~1% of the always-free 1 TB / 10M requests.
#
# Only AWS-managed cache/header policies, no logging and a single behavior, so the
# distribution also qualifies for the CloudFront flat-rate Free plan if it is ever enabled
# (see README). The collector never invalidates; the deploy pipeline does one "/*" per deploy.

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${local.project}-site"
  description                       = "CloudFront -> private S3 site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Honors each object's Cache-Control (data files: max-age=300; static assets: longer),
# gzip/brotli compression, query strings excluded from the cache key.
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

# HSTS, nosniff, frame-options, referrer-policy + CORS "*" so news.json and feed.xml can be
# used from other sites (they are public data). The CSP is set per page with a <meta> tag.
data "aws_cloudfront_response_headers_policy" "cors_and_security" {
  name = "Managed-CORS-and-SecurityHeadersPolicy"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "AI News Radar"
  default_root_object = "index.html"
  http_version        = "http2and3"
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100"

  origin {
    origin_id                = "site-bucket"
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id           = "site-bucket"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.cors_and_security.id
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
