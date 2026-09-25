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
