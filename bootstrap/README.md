# bootstrap

One-time setup, run locally with your own AWS credentials. It creates:

- the remote-state bucket for `infra/` (versioned, SSE-S3, private, TLS-only; locking uses S3
  lock files, so there is no DynamoDB lock table);
- the GitHub Actions OIDC identity provider (no AWS access keys anywhere);
- `ai-news-radar-github-plan`: read-only, assumable only by `pull_request` workflows of the repo;
- `ai-news-radar-github-deploy`: assumable only by workflows on `refs/heads/main`, scoped to
  the exact resources `infra/` manages;
- `ai-news-radar-workload-boundary`: the permissions boundary every role created by the deploy
  pipeline must carry (so CI cannot mint an over-privileged role);
- a monthly AWS Budget (default $5, credits excluded) with email alerts at 50% and 100%;
- account-level S3 Block Public Access (the site is only reachable through CloudFront + OAC).

## Run

```bash
cd bootstrap
cp terraform.tfvars.example terraform.tfvars   # set alert_email (file is git-ignored)
export AWS_PROFILE=awsnew
terraform init
terraform plan -out tfplan
terraform apply tfplan
terraform output github_actions_variables     # copy into GitHub: Settings > Secrets and variables > Actions > Variables
```

Everything here is free: IAM, OIDC providers and budgets without actions cost nothing, and the
state bucket holds a few KB.

## Afterwards

- `terraform.tfstate` for this stack stays local (git-ignored). Back it up, or move it into the
  state bucket: add `backend "s3" { bucket = "<state_bucket>", key = "bootstrap/terraform.tfstate",
  region = "<region>", use_lockfile = true }` to `versions.tf` and run `terraform init -migrate-state`.
  The CI roles can only read/write the `infra/` prefix, so this state stays admin-only.
- If the account already has a GitHub OIDC provider, set `create_github_oidc_provider = false`.

## Accounts from AWS's new sign-up flow

Accounts created with the new "Sign up for AWS" experience (like `awsnew`) run under
AWS-managed SCPs that deny `iam:*Provider*` and restrict regional services to one Region,
on both the Free and the Paid plan. The OIDC provider can only be created after upgrading to the
Paid plan, choosing "Activate advanced features" and removing that SCP.
