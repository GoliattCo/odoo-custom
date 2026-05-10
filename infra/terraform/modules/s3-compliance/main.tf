# Compliance archive — DIAN-required snapshots, 10-year Object Lock.
#
# Lives in a separate AWS account so that a root-credential compromise on the
# primary data plane account cannot delete the regulated archive. The bucket
# itself is in compliance-account scope; cross-account write from the
# primary control plane is granted via bucket policy.
#
# Object Lock COMPLIANCE mode means even root cannot shorten the retention
# window inside the 10-year period. MFA Delete is set outside Terraform
# (S3 requires root + MFA at enable time).

variable "bucket_name" {
  description = "S3 bucket name. Must be globally unique."
  type        = string
}

variable "object_lock_years" {
  description = "Object lock retention in years."
  type        = number
  default     = 10
}

variable "writer_principal_arns" {
  description = "Cross-account IAM principals (primary account control plane) allowed to write objects."
  type        = list(string)
}

variable "tags" {
  description = "Tags applied to the bucket."
  type        = map(string)
  default     = {}
}

resource "aws_s3_bucket" "this" {
  bucket              = var.bucket_name
  object_lock_enabled = true
  tags                = var.tags
}

# Versioning is required when Object Lock is enabled.
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Default COMPLIANCE retention applied to every object that doesn't specify
# its own lock parameters. The WDK complianceSnapshotMonthly workflow also
# sets these on PutObject explicitly; this is the safety net.
resource "aws_s3_bucket_object_lock_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = var.object_lock_years
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      # SSE-S3 (AES256). The application encrypts every compliance object
      # with the per-tenant DEK before upload — bucket-level SSE is the
      # second layer of at-rest encryption, not the secrecy boundary.
      # SSE-S3 sidesteps the cross-account KMS grant complexity that
      # SSE-KMS would introduce.
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: drop to Glacier Deep Archive immediately. Note: no expiration
# (Object Lock would block expiration anyway, but explicit absence of an
# expiration rule documents the intent).
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "to-glacier-deep"
    status = "Enabled"
    filter {}

    transition {
      days          = 0
      storage_class = "DEEP_ARCHIVE"
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 14
    }
  }
}

# Cross-account write: only allow PutObject if the request includes the
# COMPLIANCE lock parameters. Prevents accidental writes that bypass the
# retention guarantee.
resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCrossAccountComplianceWrites"
        Effect = "Allow"
        Principal = {
          AWS = var.writer_principal_arns
        }
        Action   = ["s3:PutObject", "s3:PutObjectLegalHold"]
        Resource = "${aws_s3_bucket.this.arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-object-lock-mode" = "COMPLIANCE"
          }
          NumericGreaterThan = {
            "s3:x-amz-object-lock-retain-until-date" = "${var.object_lock_years * 365 * 86400}"
          }
        }
      },
      {
        Sid    = "AllowCrossAccountListAndRead"
        Effect = "Allow"
        Principal = {
          AWS = var.writer_principal_arns
        }
        Action = [
          "s3:GetObject", "s3:GetObjectVersion",
          "s3:ListBucket", "s3:GetBucketVersioning"
        ]
        Resource = [
          aws_s3_bucket.this.arn,
          "${aws_s3_bucket.this.arn}/*"
        ]
      }
    ]
  })
}

output "bucket_name" {
  value = aws_s3_bucket.this.id
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}
