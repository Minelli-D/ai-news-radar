# Custom domain: the TLS certificate is issued here, once, by the owner. The CI roles only read
# it and manage the site's own alias records (see github_permissions.tf), so the pipeline never
# needs permission to request certificates or to write any other name in the zone.

# The hosted zone already exists in the account and is only looked up: this project never
# creates one (a zone is $0.50 a month, whether or not the site uses it).
data "aws_route53_zone" "site" {
  name         = var.dns_zone
  private_zone = false
}

# CloudFront only accepts ACM certificates from us-east-1. Public certificates are free, and
# ACM renews this one by itself for as long as the validation record below exists.
resource "aws_acm_certificate" "site" {
  provider = aws.us_east_1

  domain_name       = var.site_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "site_certificate_validation" {
  for_each = {
    for option in aws_acm_certificate.site.domain_validation_options : option.domain_name => option
  }

  zone_id = data.aws_route53_zone.site.zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  ttl     = 300
  records = [each.value.resource_record_value]
}

# Waits until ACM has seen the record and issued the certificate (usually a few minutes), so
# that infra/ finds it in the ISSUED state.
resource "aws_acm_certificate_validation" "site" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for record in aws_route53_record.site_certificate_validation : record.fqdn]
}
