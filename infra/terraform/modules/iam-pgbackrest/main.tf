# pgBackRest principals — one per data plane platform.
#
# Each platform gets its own IAM user so credentials can be rotated per
# platform without disturbing the other. The plan's risk register calls this
# out explicitly: "Wire IAM roles for Vercel egress + both Railway and Fly
# egress (separate IAM principals so credentials can be rotated per platform)."
#
# Both principals have identical permissions today: write/read WAL segments
# in the HOT bucket. If the bucket structures diverge later (e.g., one
# platform uses a different prefix), policies can fork without touching the
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

variable "hot_bucket_arn" {
  description = "ARN of the HOT bucket the principals write WAL to."
  type        = string
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
    sid       = "ListBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.hot_bucket_arn]
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
    resources = ["${var.hot_bucket_arn}/*"]
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
