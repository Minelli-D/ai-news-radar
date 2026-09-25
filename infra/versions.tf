terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66"
    }
  }

  # Partial configuration: pass the bucket (it contains the account ID) and the Region at init:
  #   terraform init -backend-config="bucket=<bootstrap state_bucket>" -backend-config="region=eu-north-1"
  # use_lockfile = S3-native state locking (no DynamoDB lock table).
  backend "s3" {
    key          = "infra/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
