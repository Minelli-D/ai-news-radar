# Credentials come from the environment, e.g. `export AWS_PROFILE=minelli-d`.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "ai-news-radar"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}

# Only for the site certificate: CloudFront reads ACM certificates from us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = "ai-news-radar"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}
