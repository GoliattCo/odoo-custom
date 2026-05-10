# Control plane principal — credentials live in Vercel project env.
#
# This single principal:
#   - Reads/writes WARM bucket (daily dumps + filestore)
#   - Reads HOT bucket (for PITR restore drills)
#   - Encrypts/decrypts per-tenant DEKs via the primary KMS CMK
#   - Writes COMPLIANCE bucket cross-account (only with the lock parameters
#     baked into every PutObject — enforced by the compliance bucket policy)
#
# Vercel doesn't natively support OIDC into AWS today, so we issue a static
# access key. Rotate quarterly via `terraform taint aws_iam_access_key.control_plane`
# followed by `terraform apply`.

variable "name" {
  description = "IAM user name."
  type        = string
  default     = "control-plane"
}

variable "hot_bucket_arn" {
  description = "ARN of the HOT (WAL) bucket — control plane reads for restores."
  type        = string
}

variable "warm_bucket_arn" {
  description = "ARN of the WARM (dumps) bucket — control plane writes daily."
  type        = string
}

variable "compliance_bucket_arn" {
  description = "ARN of the COMPLIANCE bucket (in the OTHER AWS account)."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS CMK ARN for DEK wrap/unwrap."
  type        = string
}

variable "tags" {
  description = "Tags applied to the IAM user."
  type        = map(string)
  default     = {}
}

resource "aws_iam_user" "control_plane" {
  name = var.name
  tags = var.tags
}

resource "aws_iam_access_key" "control_plane" {
  user = aws_iam_user.control_plane.name
}

data "aws_iam_policy_document" "control_plane" {
  statement {
    sid       = "HotBucketRead"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.hot_bucket_arn]
  }

  statement {
    sid    = "HotBucketReadObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject", "s3:GetObjectVersion"
    ]
    resources = ["${var.hot_bucket_arn}/*"]
  }

  statement {
    sid       = "WarmBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.warm_bucket_arn]
  }

  statement {
    sid    = "WarmBucketReadWrite"
    effect = "Allow"
    actions = [
      "s3:PutObject", "s3:PutObjectAcl",
      "s3:GetObject", "s3:GetObjectVersion",
      "s3:DeleteObject", "s3:DeleteObjectVersion",
      "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"
    ]
    resources = ["${var.warm_bucket_arn}/*"]
  }

  statement {
    sid       = "ComplianceBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketVersioning"]
    resources = [var.compliance_bucket_arn]
  }

  statement {
    sid    = "ComplianceBucketWrite"
    effect = "Allow"
    actions = [
      "s3:PutObject", "s3:PutObjectLegalHold",
      "s3:GetObject", "s3:GetObjectVersion"
    ]
    resources = ["${var.compliance_bucket_arn}/*"]
  }

  statement {
    sid    = "KmsForDekWrapping"
    effect = "Allow"
    actions = [
      "kms:Encrypt", "kms:Decrypt",
      "kms:GenerateDataKey", "kms:GenerateDataKeyWithoutPlaintext",
      "kms:DescribeKey", "kms:ReEncrypt*"
    ]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_user_policy" "control_plane" {
  name   = "${var.name}-policy"
  user   = aws_iam_user.control_plane.name
  policy = data.aws_iam_policy_document.control_plane.json
}

output "user_arn" {
  value = aws_iam_user.control_plane.arn
}

output "access_key_id" {
  value = aws_iam_access_key.control_plane.id
}

output "secret_access_key" {
  value     = aws_iam_access_key.control_plane.secret
  sensitive = true
}
