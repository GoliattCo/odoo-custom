# pgBackRest / backup-runner principals — one per data plane platform.
#
# Each platform gets its own IAM user so credentials can be rotated per
# platform without disturbing the other. The plan's risk register calls this
# out explicitly: "Wire IAM roles for Vercel egress + both Railway and Fly
# egress (separate IAM principals so credentials can be rotated per platform)."
#
# These principals are used by TWO data-plane services on each platform:
#   - The Postgres service runs pgBackRest, writing WAL segments to the HOT
#     bucket.
#   - The backup-runner service writes daily dump artifacts to the WARM
#     bucket.
# Hence the policy grants list + read/write objects across all
# `bucket_arns` passed in (HOT + WARM today). If the bucket structures
# diverge later, the policy can fork per platform without touching the
# other.

variable "name_prefix" {
  description = "Prefix for the IAM user names (e.g., 'pgbackrest')."
  type        = string
  default     = "pgbackrest"
}

variable "platforms" {
  description = "Platform identifiers; one IAM user is created per platform."
  type        = list(string)
  default     = ["railway", "fly"]
}

variable "bucket_arns" {
  description = "S3 bucket ARNs these principals may list + read/write objects in. Pass HOT (WAL archive) and WARM (backup-runner dump uploads)."
  type        = list(string)
}

variable "kms_key_arn" {
  description = "KMS CMK ARN. Principals need Encrypt/Decrypt for SSE-KMS."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}

resource "aws_iam_user" "this" {
  for_each = toset(var.platforms)
  name     = "${var.name_prefix}-${each.value}"
  tags     = var.tags
}

resource "aws_iam_access_key" "this" {
  for_each = toset(var.platforms)
  user     = aws_iam_user.this[each.value].name
}

data "aws_iam_policy_document" "this" {
  statement {
    sid       = "ListBuckets"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = var.bucket_arns
  }

  statement {
    sid    = "ReadWriteObjects"
    effect = "Allow"
    actions = [
      "s3:PutObject", "s3:PutObjectAcl",
      "s3:GetObject", "s3:GetObjectVersion",
      "s3:DeleteObject", "s3:DeleteObjectVersion",
      "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"
    ]
    resources = [for arn in var.bucket_arns : "${arn}/*"]
  }

  statement {
    sid    = "KmsEncryptDecrypt"
    effect = "Allow"
    actions = [
      "kms:Encrypt", "kms:Decrypt",
      "kms:GenerateDataKey", "kms:GenerateDataKeyWithoutPlaintext",
      "kms:DescribeKey", "kms:ReEncrypt*"
    ]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_user_policy" "this" {
  for_each = toset(var.platforms)
  name     = "${var.name_prefix}-${each.value}-s3-kms"
  user     = aws_iam_user.this[each.value].name
  policy   = data.aws_iam_policy_document.this.json
}

output "user_arns" {
  description = "Map of platform → IAM user ARN."
  value       = { for k, u in aws_iam_user.this : k => u.arn }
}

output "access_key_ids" {
  description = "Map of platform → AWS access key ID."
  value       = { for k, ak in aws_iam_access_key.this : k => ak.id }
}

output "secret_access_keys" {
  description = "Map of platform → AWS secret access key. SENSITIVE."
  value       = { for k, ak in aws_iam_access_key.this : k => ak.secret }
  sensitive   = true
}
