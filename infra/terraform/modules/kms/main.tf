# KMS — Customer Managed Key for SaaS data plane.
#
# Two uses:
#   1. Server-side encryption of the HOT and WARM S3 buckets.
#   2. Wrapping per-tenant DEKs that the control plane stores in Neon's
#      tenant_dek table.
#
# Access control model: the key policy grants root admin, which delegates
# authorization to IAM. Principals get Encrypt/Decrypt/GenerateDataKey grants
# via their own IAM policies (see modules/iam-pgbackrest and
# modules/iam-control-plane). This avoids a circular dependency between the
# KMS module and the IAM modules — KMS only references admins; IAM
# references the KMS key ARN.

variable "alias" {
  description = "KMS key alias (without the alias/ prefix)."
  type        = string
}

variable "key_admin_arns" {
  description = "IAM principals that may administer the key (rotate, schedule deletion). Operators only."
  type        = list(string)
}

variable "tags" {
  description = "Tags applied to the key."
  type        = map(string)
  default     = {}
}

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "this" {
  description              = "SaaS data plane — tenant DEK wrap + bucket SSE"
  key_usage                = "ENCRYPT_DECRYPT"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  deletion_window_in_days  = 30
  enable_key_rotation      = true
  multi_region             = false

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid       = "EnableRootAdmin"
          Effect    = "Allow"
          Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
          Action    = "kms:*"
          Resource  = "*"
        },
      ],
      length(var.key_admin_arns) > 0 ? [
        {
          Sid    = "KeyAdmins"
          Effect = "Allow"
          Principal = {
            AWS = var.key_admin_arns
          }
          Action = [
            "kms:Create*", "kms:Describe*", "kms:Enable*", "kms:List*", "kms:Put*",
            "kms:Update*", "kms:Revoke*", "kms:Disable*", "kms:Get*", "kms:Delete*",
            "kms:TagResource", "kms:UntagResource", "kms:ScheduleKeyDeletion",
            "kms:CancelKeyDeletion", "kms:RotateKeyOnDemand"
          ]
          Resource = "*"
        }
      ] : []
    )
  })

  tags = var.tags
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.alias}"
  target_key_id = aws_kms_key.this.key_id
}

output "key_id" {
  value = aws_kms_key.this.key_id
}

output "key_arn" {
  value = aws_kms_key.this.arn
}

output "key_alias" {
  value = aws_kms_alias.this.name
}
