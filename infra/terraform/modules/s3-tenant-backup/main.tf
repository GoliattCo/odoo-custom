# Generic backup bucket module — used for HOT (WAL) and WARM (dumps).
#
# Differences between HOT and WARM are expressed as input variables:
#   - storage_class    "STANDARD" for HOT, "STANDARD_IA" for WARM
#   - expiration_days  30 for HOT (WAL window), 400 for WARM (13-month catch-all)
#
# Per-tenant retention (7 daily / 4 weekly / 12 monthly) is enforced at the
# application level by the WDK tenantBackupDaily workflow's `expire` step
# against the tenant_backups catalog. The bucket lifecycle here is a safety
# net, not the primary retention mechanism.

variable "bucket_name" {
  description = "S3 bucket name. Must be globally unique."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS CMK ARN for SSE-KMS."
  type        = string
}

variable "storage_class" {
  description = "Storage class for newly written objects (STANDARD or STANDARD_IA)."
  type        = string
  default     = "STANDARD"
}

variable "expiration_days" {
  description = "Safety-net expiration (days). Tenant-level retention is in the application."
  type        = number
  default     = 30
}

variable "noncurrent_version_expiration_days" {
  description = "How long to keep noncurrent versions after delete-marker."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Tags applied to the bucket."
  type        = map(string)
  default     = {}
}

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "transition-to-target-class"
    status = "Enabled"
    filter {}

    # S3 forbids transitioning to STANDARD_IA before day 30. So WARM-tier
    # objects spend their first 30 days in STANDARD (where the most likely
    # restores happen — recent dailies) and then move to the cheaper
    # STANDARD_IA for the rest of their retention window. If you need
    # objects in STANDARD_IA from day 0, write them with an explicit
    # StorageClass=STANDARD_IA at PutObject time instead of via lifecycle.
    dynamic "transition" {
      for_each = var.storage_class == "STANDARD_IA" ? [1] : []
      content {
        days          = 30
        storage_class = "STANDARD_IA"
      }
    }

    expiration {
      days = var.expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

output "bucket_name" {
  value = aws_s3_bucket.this.id
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}
