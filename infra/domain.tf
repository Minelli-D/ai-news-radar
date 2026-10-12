# Custom domain. bootstrap/domain.tf issues the certificate; this stack attaches it to the
# distribution (cdn.tf) and points the name at it. The hosted zone already exists in the
# account: it is looked up, never created.

data "aws_route53_zone" "site" {
  name         = var.dns_zone
  private_zone = false
}

# CloudFront only accepts ACM certificates from us-east-1.
data "aws_acm_certificate" "site" {
  provider = aws.us_east_1

  domain      = var.site_domain
  statuses    = ["ISSUED"]
  most_recent = true
}

# Alias records instead of a CNAME: Route 53 does not charge for alias queries to CloudFront.
# AAAA as well because the distribution has IPv6 enabled.
resource "aws_route53_record" "site" {
  for_each = toset(["A", "AAAA"])

  zone_id = data.aws_route53_zone.site.zone_id
  name    = var.site_domain
  type    = each.value

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
