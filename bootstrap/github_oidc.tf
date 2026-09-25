# GitHub Actions authenticates with short-lived OIDC tokens: no AWS access keys anywhere.

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1

  url = "https://token.actions.githubusercontent.com"
}

# Trust: the "plan" role only for pull_request workflows of this repository, the "deploy"
# role only for workflows running on refs/heads/main. (A job that uses a GitHub
# "environment" presents a different `sub`, so deploy.yml must not declare one.)
data "aws_iam_policy_document" "trust_github" {
  for_each = {
    plan   = "repo:${var.github_repository}:pull_request"
    deploy = "repo:${var.github_repository}:ref:refs/heads/main"
  }

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.arn.github_oidc]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}

resource "aws_iam_role" "github" {
  for_each = data.aws_iam_policy_document.trust_github

  name                 = "${local.project}-github-${each.key}"
  description          = "GitHub Actions ${each.key} role for ${var.github_repository}"
  assume_role_policy   = each.value.json
  max_session_duration = 3600
}
