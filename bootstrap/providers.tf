# Credentials come from the environment, e.g. `export AWS_PROFILE=awsnew`.
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
