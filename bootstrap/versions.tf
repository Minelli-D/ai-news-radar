terraform {
  # use_lockfile (S3-native state locking, used by infra/) is GA since Terraform 1.11.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66"
    }
  }

  # Local state on purpose: this stack creates the remote-state bucket that infra/ uses.
  # Keep bootstrap/terraform.tfstate safe (it is git-ignored), or migrate it into the bucket
  # afterwards (see bootstrap/README.md).
}
