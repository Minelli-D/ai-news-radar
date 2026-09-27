# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI News Radar: a public portfolio project that aggregates AI news (Anthropic, OpenAI, DeepSeek,
Google, AWS, AI News Hub) on a serverless AWS stack that must cost €0/month. GitHub repo:
`Minelli-D/ai-news-radar` (the local folder is named `aws-ai-news`). AWS CLI profile: `minelli-d`.

## Owner's hard rules

- **Never** run `terraform apply`, create AWS resources, or `git push` without asking first.
  Before any apply, show the plan summary and the expected monthly cost.
- Cost: if anything is not clearly inside the free tier, stop and ask with the expected cost.
  Banned: NAT Gateway, Lambda in a VPC, EC2, Elastic IPs/public IPv4, ECS/Fargate/EKS, RDS, ALB,
  API Gateway, ElastiCache, DAX, Route 53 hosted zones, customer-managed KMS keys, Secrets
  Manager, DynamoDB on-demand or PITR, provisioned concurrency, paid WAF, Bedrock. Total
  provisioned DynamoDB in the account ≤ 25 RCU / 25 WCU. No access keys anywhere (OIDC only).
- Content: store and publish only title, link, date and a description ≤ 200 chars. Never article
  bodies, including in test fixtures (they are trimmed; see `tests/fixtures/README.md`).
- Politeness: descriptive User-Agent with the repo URL, robots.txt (RFC 9309) for every host,
  10 s timeouts, one request per feed/page per run, plus at most 3 `og:description` fetches per
  source per run, only for new items without a description.
- DynamoDB is read with a Query per source, never a Scan. The collector never creates
  CloudFront invalidations; only the deploy pipeline may create one `/*` per deploy.
- Work in phases (collector → bootstrap → infra → site → CI/CD → README), one commit each.

## AWS account (profile `minelli-d`)

A dedicated account on the Paid plan (with credits), signed in with `aws login`; everything
lives in eu-north-1. It has no AWS-managed SCPs, so the GitHub OIDC provider could be created.
`bootstrap/` was applied on 2026-09-27; its state is local (`bootstrap/terraform.tfstate`,
git-ignored). The first account, `awsnew`, is no longer used: its SCPs denied `iam:*Provider*`
and every Region except eu-north-1. Verify with read-only calls before assuming anything changed.

## Commands

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/pytest                                              # all tests (offline, fixtures only)
.venv/bin/pytest tests/sources/test_aws.py::test_is_ai_related -q   # a single test
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy   # lint, format, strict types
.venv/bin/python scripts/run_local.py --out build/site-data   # one LIVE run, no AWS: real HTTP, files on disk
```

`tests/conftest.py` blocks every non-loopback socket, so a test that touches the network fails.

Site (`site/`): vanilla HTML/CSS/ES modules, no build step, no cookies, trackers or storage.

```bash
node --test tests/site/*.test.mjs                             # unit tests for site/assets/lib.mjs
.venv/bin/python scripts/run_local.py --out build/preview --serve 8000   # live data + site, S3-like MIME types
```

- `lib.mjs` holds the pure logic (tested); `app.mjs` does DOM wiring only, and all data goes
  through `textContent` / `safeHttpUrl`, never `innerHTML`. Each page sets a strict CSP `<meta>`
  (no inline script or style), because CloudFront only adds the managed security headers.
- Filters and `/latest/*` shortcuts are generated from `news.json` → `sources`, so a new source
  needs no frontend change except a `.badge--<slug>` colour (white text must stay ≥ 4.5:1).
- `?v=dev` on asset URLs (including the `lib.mjs` import) is replaced with the git SHA at deploy
  time, so long-cached assets refresh.

Terraform 1.16.4 lives in `.tools/terraform` (git-ignored, verified against HashiCorp's GPG
signature). Local checks without credentials:

```bash
.tools/terraform -chdir=bootstrap fmt -check -recursive
.tools/terraform -chdir=bootstrap init -backend=false && .tools/terraform -chdir=bootstrap validate
```

### Terraform stacks

- `bootstrap/` (local state, run once by the owner): state bucket, GitHub OIDC provider, CI
  roles, permissions boundary, $5 budget (credits excluded), account-level S3 Block Public Access.
- The CI roles are scoped to fixed names, and `infra/` must use them: table `ai-news-items`,
  bucket `ai-news-radar-site-<account id>`, state key prefix `infra/`, and every function, role,
  log group (`/aws/lambda/…`), schedule, SNS topic and alarm prefixed `ai-news-radar-app-`. Every
  IAM role in `infra/` must set `permissions_boundary` to `ai-news-radar-workload-boundary`, or
  the deploy role cannot create it.
- `infra/` (S3 backend, key `infra/terraform.tfstate`, `use_lockfile = true`; the bucket and
  Region are passed with `-backend-config` because the bucket name contains the account ID):
  DynamoDB provisioned 5/5 + TTL, private site bucket + CloudFront with OAC (AWS-managed
  cache and header policies only, so it stays compatible with the flat-rate Free plan), Lambda
  (`build/collector.zip` from `scripts/build_lambda.py`, JSON logging, async retries 0),
  EventBridge Scheduler (hourly), SNS email + Errors alarm.
- The collector's IAM policy allows `s3:PutObject` only on `news.json`, `feed.xml` and
  `latest/*`, and `s3:ListBucket` so that a missing `news.json` (first run) returns 404 instead of 403.

```bash
.venv/bin/python scripts/build_lambda.py        # reproducible zip (same sha256 for the same inputs)
AWS_PROFILE=minelli-d .tools/terraform -chdir=infra init -backend-config="bucket=<state_bucket>" -backend-config="region=eu-north-1"
AWS_PROFILE=minelli-d .tools/terraform -chdir=infra plan   # read-only; never apply without the owner's OK
```

## Architecture

EventBridge Scheduler (hourly) → Lambda `collector.handler.lambda_handler` → DynamoDB + S3 →
CloudFront. `collector/pipeline.py::run` is one run:

1. `repo.latest(slug, 20)` for every source: a DynamoDB Query, newest first (`storage.py`).
2. Every source is fetched in parallel threads, one `HttpClient` per source (the client is not
   thread-safe). An adapter exception becomes that source's `error` and never affects the other
   sources. A source still running at the deadline is reported as "timed out".
3. Items whose URL is not HTTPS on the source's `allowed_hosts` (or a subdomain) are dropped,
   so a compromised feed cannot turn `/latest/<slug>` into a redirect elsewhere.
   `dedup.select_new` compares canonical-URL SHA-256 hashes, so re-dated or tracking-param URL
   variants are not new. `enrich.py` (best-effort, `<head>` only) fills missing descriptions
   for new items.
4. `repo.put_new` is a conditional PutItem (`attribute_not_exists`). Keys are
   PK `source`, SK `<publishedAt ISO>#<sha256(canonical URL)>`, TTL `expiresAt` = first seen + 120 days.
5. `publish.py` writes `news.json` every run (its `generatedAt` drives "updated X min ago"), and
   `feed.xml` / `latest/<slug>` only when their content changed versus the previous `news.json`,
   to keep S3 PUTs low. `news.json` is written LAST: it is the baseline the next run compares
   against, so a failed upload of the other files is retried instead of forgotten.
   `RENDER_VERSION` is a hash of `publish.py` itself, so editing a template rewrites every object
   once. Feed `<description>`s are HTML-escaped, because RSS readers render them as HTML.

Text contract: `models.make_item` takes PLAIN text. `text.html_to_text` is only for HTML
fragments (`base.parse_feed` picks it per field from feedparser's `*_detail.type`), so
"Why <thinking> tags…" stays intact. Both helpers drop characters that XML or UTF-8 cannot carry.
`models.is_web_url` never raises: malformed URLs, bad ports, whitespace and URLs over 2048 chars
are rejected.

Known behaviour: slow sources (DeepSeek, AI News Hub) keep old posts in their newest 20. When TTL
removes those posts after 120 days they are re-inserted as "new", which is harmless and shows up
as a spike in the `new` count.

Failure semantics: a source failure only shows in the run's log line (`RunReport.summary()`)
and in `news.json` → `sources[].ok/error/lastSuccessAt`. The invocation fails (and the CloudWatch
alarm fires) only on storage/S3 errors or when every source failed.

`collector/http.py`: HTTPS only, robots.txt via `protego` (Python's stdlib parser ignores
wildcards, which AWS's robots.txt uses), matched on the product token `AINewsRadar` (RFC 9309).
429 or 5xx on robots.txt means the host is skipped for the run. Every redirect hop is
re-validated. Gzip decoding has a size cap. `read1` keeps the 10 s total timeout even against
servers that trickle bytes. IRIs are percent-encoded, and any protocol error becomes a
`FetchError`. At most 1 request/s per host. Adapters depend on the `Fetcher` protocol, so tests
pass `tests/fakes.FakeHttp`.

### Sources (`collector/sources/`)

Each module exposes `fetch(client) -> list[NewsItem]` and a `SOURCE` registered in
`sources/__init__.py`. Slugs are public URLs (`/latest/<slug>`, site filters): do not rename them.

- `anthropic`: no RSS. Parses the CMS JSON embedded in `self.__next_f.push` scripts on /news
  (title, ISO date, summary); falls back to the visible list. CSS module class hashes change, so
  match on `__title`, never on full class names.
- `openai`, `ainewshub`: RSS (AI News Hub's /latest-a-i-news page has no dates, so use its blog feed).
- `google`: two RSS feeds (Keyword AI section + DeepMind) as one source. `base.parse_feed` strips
  `<media:description>` because feedparser would otherwise use the image caption as the summary.
- `aws`: What's New RSS, kept if AWS tags it AI (`marchitecture/artificial-intelligence`,
  `products/aiml`, Bedrock/SageMaker/Q/Nova product tags) or the title matches case-sensitive
  keywords. Bare "agent" is excluded (Amazon Connect false positives).
- `deepseek`: no feed. sitemap.xml → newest `/news/newsYYMMDD` page → its Docusaurus sidebar
  (`a.menu__link`, "Title YYYY/MM/DD") lists every announcement. Date-only sources are stored at
  12:00 UTC so the day renders the same in every time zone.

Adding a source: new module with `SOURCE(..., allowed_hosts=...)` + trimmed real fixture in
`tests/fixtures/` (record provenance in its README) + adapter test (including the
allowed-hosts check) + registry entry + a `.badge--<slug>` colour in `site/assets/style.css`.

## CI/CD (`.github/workflows/`)

- `checks.yml` (reusable, no AWS): ruff/mypy/pytest, `node --test`, terraform fmt/validate,
  TFLint, Trivy IaC scan (every severity; exceptions are `#trivy:ignore:AWS-xxxx` comments with
  the reason next to the resource) and a Trivy dependency scan of both requirements files.
  Trivy and TFLint are installed from release archives verified against SHA-256 values pinned in
  the workflow, not through setup actions. Every third-party action is pinned to a commit SHA.
- `ci.yml` (pull_request): checks + `terraform plan -lock=false` with the read-only plan role,
  posted and updated as one PR comment with the account ID redacted. Fork PRs skip the plan.
- `deploy.yml` (push to main, concurrency group `deploy-production`): checks → build zip →
  apply → `scripts/deploy_site.sh` → `scripts/invoke_collector.sh` → one `/*` invalidation →
  `scripts/smoke_test.sh`. The deploy job must not use a GitHub environment (it would change the
  OIDC `sub` the deploy role trusts).
- GitHub issues immutable OIDC subjects for this repo
  (`repo:Minelli-D@<owner id>/ai-news-radar@<repo id>:…`); bootstrap's `github_oidc_subject_prefix`
  must match `gh api repos/Minelli-D/ai-news-radar/actions/oidc/customization/sub`.
- Repository settings needed: variables `AWS_REGION`, `AWS_PLAN_ROLE_ARN`,
  `AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET` (from `terraform -chdir=bootstrap output`) and the
  secret `ALERT_EMAIL`.

Local equivalents (tools in `.tools/`, verified the same way):

```bash
.tools/trivy config --exit-code 1 --skip-dirs .tools --skip-dirs .venv --skip-dirs build .
.tools/tflint --init --config "$PWD/.tflint.hcl" && .tools/tflint --chdir=infra --config "$PWD/.tflint.hcl"
.tools/actionlint                                   # workflows
uvx --from shellcheck-py shellcheck scripts/*.sh    # shell scripts
```
