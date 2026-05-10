# Primary environment — KMS, HOT, WARM, IAM (one AWS account).
#
# Apply this composition before the compliance composition. After apply,
# `terraform output control_plane_iam_user_arn` gives you the cross-account
# principal to plug into compliance/terraform.tfvars.

variable "region" {
  description = "AWS region for the primary data plane."
  type        = string
  default     = "us-east-1"
}

variable "kms_key_alias" {
  description = "KMS key alias (without the alias/ prefix)."
  type        = string
  default     = "odoo-saas/data-plane"
}

variable "hot_bucket_name" {
  description = "S3 bucket name for HOT (WAL archive). Must be globally unique."
  type        = string
}

variable "warm_bucket_name" {
  description = "S3 bucket name for WARM (daily dumps). Must be globally unique."
  type        = string
}

variable "compliance_bucket_arn" {
  description = "ARN of the compliance bucket (predicted; it lives in the other account)."
  type        = string
}

variable "key_admin_arns" {
  description = "IAM principals that may administer the KMS key (your ops users)."
  type        = list(string)
}

data "aws_caller_identity" "current" {}

module "kms" {
  source         = "../../modules/kms"
  alias          = var.kms_key_alias
  key_admin_arns = var.key_admin_arns
}

module "s3_hot" {
  source          = "../../modules/s3-tenant-backup"
  bucket_name     = var.hot_bucket_name
  kms_key_arn     = module.kms.key_arn
  storage_class   = "STANDARD"
  expiration_days = 30
  tags = {
    tier = "hot"
  }
}

module "s3_warm" {
  source          = "../../modules/s3-tenant-backup"
  bucket_name     = var.warm_bucket_name
  kms_key_arn     = module.kms.key_arn
  storage_class   = "STANDARD_IA"
  expiration_days = 400
  tags = {
    tier = "warm"
  }
}

module "iam_pgbackrest" {
  source         = "../../modules/iam-pgbackrest"
  name_prefix    = "pgbackrest"
  platforms      = ["railway", "fly"]
  hot_bucket_arn = module.s3_hot.bucket_arn
  kms_key_arn    = module.kms.key_arn
}

module "iam_control_plane" {
  source                = "../../modules/iam-control-plane"
  name                  = "control-plane"
  hot_bucket_arn        = module.s3_hot.bucket_arn
  warm_bucket_arn       = module.s3_warm.bucket_arn
  compliance_bucket_arn = var.compliance_bucket_arn
  kms_key_arn           = module.kms.key_arn
}

# --- Outputs to feed into deploy environments and the compliance composition.

output "kms_cmk_arn" {
  value = module.kms.key_arn
}

output "kms_cmk_alias" {
  value = module.kms.key_alias
}

output "s3_hot_bucket_name" {
  value = module.s3_hot.bucket_name
}

output "s3_warm_bucket_name" {
  value = module.s3_warm.bucket_name
}

output "pgbackrest_user_arns" {
  value = module.iam_pgbackrest.user_arns
}

output "pgbackrest_railway_access_key_id" {
  value = module.iam_pgbackrest.access_key_ids["railway"]
}

output "pgbackrest_railway_secret_access_key" {
  value     = module.iam_pgbackrest.secret_access_keys["railway"]
  sensitive = true
}

output "pgbackrest_fly_access_key_id" {
  value = module.iam_pgbackrest.access_key_ids["fly"]
}

output "pgbackrest_fly_secret_access_key" {
  value     = module.iam_pgbackrest.secret_access_keys["fly"]
  sensitive = true
}

output "control_plane_iam_user_arn" {
  description = "Feed this into infra/terraform/environments/compliance/terraform.tfvars as writer_principal_arns."
  value       = module.iam_control_plane.user_arn
}

output "control_plane_access_key_id" {
  value = module.iam_control_plane.access_key_id
}

output "control_plane_secret_access_key" {
  value     = module.iam_control_plane.secret_access_key
  sensitive = true
}
