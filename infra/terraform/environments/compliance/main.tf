# Compliance environment — Glacier Deep Object Lock 10y, separate AWS account.
#
# Apply this *after* the primary composition. Set `writer_principal_arns` to
# the `control_plane_iam_user_arn` output from primary.
#
# Authenticate to the compliance AWS account via AWS_PROFILE or env vars
# before running.

variable "region" {
  description = "AWS region for the compliance bucket."
  type        = string
  default     = "us-east-1"
}

variable "compliance_bucket_name" {
  description = "S3 bucket name for COMPLIANCE (DIAN snapshots). Must match the predicted ARN used in the primary composition."
  type        = string
}

variable "writer_principal_arns" {
  description = "Primary-account IAM principals allowed to write the compliance bucket. Use the control_plane_iam_user_arn output from primary."
  type        = list(string)
}

variable "object_lock_years" {
  description = "Object Lock retention in years. DIAN requires 10."
  type        = number
  default     = 10
}

module "s3_compliance" {
  source                = "../../modules/s3-compliance"
  bucket_name           = var.compliance_bucket_name
  object_lock_years     = var.object_lock_years
  writer_principal_arns = var.writer_principal_arns
  tags = {
    tier = "compliance"
  }
}

# --- Outputs

output "s3_compliance_bucket_name" {
  value = module.s3_compliance.bucket_name
}

output "s3_compliance_bucket_arn" {
  value = module.s3_compliance.bucket_arn
}
