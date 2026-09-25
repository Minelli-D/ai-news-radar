# One partition per source; items sorted by "<publishedAt>#<sha256(url)>".
# The collector only ever Queries one partition (newest first, Limit 20): no Scan, no GSI.
resource "aws_dynamodb_table" "news" {
  name = local.table_name

  # Provisioned 5/5 stays inside the always-free 25 RCU / 25 WCU. No auto scaling on purpose.
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5

  hash_key  = "source"
  range_key = "sk"

  attribute {
    name = "source"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # Items expire 120 days after they were first seen (TTL deletes are free).
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  # PITR is a paid feature; the data can be rebuilt from the sources at any time.
  point_in_time_recovery {
    enabled = false
  }
}
