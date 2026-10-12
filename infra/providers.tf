provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "ai-news-radar"
      ManagedBy = "terraform"
      Stack     = "infra"
    }
  }
}

# Only to look up the site certificate: CloudFront reads ACM certificates from us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
