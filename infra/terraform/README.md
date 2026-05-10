# Terraform — Step 8: AWS Provisioning

Provisions the AWS resources the SaaS data plane needs before pilot:

| Tier | Resource | Account | Encryption at rest |
|---|---|---|---|
| KMS | One Customer Managed Key for tenant DEK wrapping + bucket SSE | Primary | n/a |
| HOT | S3 bucket for pgBackRest WAL archive (Standard, 30-day rolling window) | Primary | SSE-KMS (primary CMK) |
| WARM | S3 bucket for daily dumps + filestore tarballs (Standard-IA, 13-month retention) | Primary | SSE-KMS (primary CMK) |
| COMPLIANCE | S3 bucket for DIAN-only snapshots (Glacier Deep + Object Lock COMPLIANCE 10y) | **Separate** | SSE-S3 (AES256) — secrecy is provided by per-tenant DEK encryption *before* upload; SSE-S3 avoids the cross-account KMS grant complexity |
| IAM | Two pgBackRest principals (railway + fly) + one control-plane principal | Primary | n/a |

The compliance bucket lives in a second AWS account so that a compromise of the
primary account's root credentials cannot delete the 10-year regulated archive
(plan risk register: "AWS account exposure for compliance lock").

## Prerequisites

1. **Two AWS accounts**, both managed in the same AWS Organization.
   - Primary: the data plane's normal account (`AWS_ACCOUNT_ID_PRIMARY`).
   - Compliance: an isolated account that only holds the Glacier bucket
     (`AWS_ACCOUNT_ID_COMPLIANCE`).
2. **Terraform 1.6+** installed locally.
3. **An S3 + DynamoDB remote state backend** for both compositions. (Local
   state is fine for the first apply; switch to remote before production.)
4. **MFA on the root user of the compliance account.** S3 MFA Delete on the
   compliance bucket is enabled *outside* Terraform (root credentials are
   required at enable-time; see "MFA Delete" below).

## Apply order

```
# 1. Apply primary composition under the primary AWS profile.
cd infra/terraform/environments/primary
cp terraform.tfvars.example terraform.tfvars   # fill in account_id, region, names
terraform init
terraform plan
terraform apply

# 2. Note the output `control_plane_iam_user_arn` — you'll feed it into compliance.
terraform output -raw control_plane_iam_user_arn

# 3. Switch to the compliance profile (AWS_PROFILE=...compliance...) and apply.
cd ../compliance
cp terraform.tfvars.example terraform.tfvars   # include the primary IAM ARN from above
terraform init
terraform plan
terraform apply
```

## Outputs you need to plug into the application

After both applies:

| Output (from where) | Set as | Where |
|---|---|---|
| `pgbackrest_railway_access_key_id` (primary) | `PGBACKREST_REPO1_S3_KEY` | Railway Postgres service env |
| `pgbackrest_railway_secret_access_key` (primary) | `PGBACKREST_REPO1_S3_KEY_SECRET` | Railway Postgres service env |
| `pgbackrest_fly_access_key_id` (primary) | `PGBACKREST_REPO1_S3_KEY` | Fly Postgres app secrets |
| `pgbackrest_fly_secret_access_key` (primary) | `PGBACKREST_REPO1_S3_KEY_SECRET` | Fly Postgres app secrets |
| `s3_hot_bucket_name` (primary) | `PGBACKREST_REPO1_S3_BUCKET` | Both pgBackRest principals |
| `kms_cmk_arn` (primary) | `AWS_KMS_CMK_ARN` | Vercel control plane env |
| `control_plane_access_key_id` (primary) | `AWS_ACCESS_KEY_ID` | Vercel control plane env |
| `control_plane_secret_access_key` (primary) | `AWS_SECRET_ACCESS_KEY` | Vercel control plane env |
| `s3_warm_bucket_name` (primary) | `S3_WARM_BUCKET` | Vercel control plane env |
| `s3_compliance_bucket_name` (compliance) | `S3_COMPLIANCE_BUCKET` | Vercel control plane env |

All access keys are sensitive Terraform outputs; treat the state file as
secret. Rotate keys quarterly via `terraform taint`+`terraform apply`.

## MFA Delete on the compliance bucket

Terraform cannot enable MFA Delete (S3 requires root credentials + MFA
device serial at enable time). After `terraform apply` on the compliance
environment:

```
aws s3api put-bucket-versioning \
  --bucket <s3_compliance_bucket_name> \
  --versioning-configuration Status=Enabled,MFADelete=Enabled \
  --mfa "<MFA-serial> <one-time-code>" \
  --profile <compliance-root-profile>
```

Then store the MFA device serial in the runbook so the on-call can rotate it
if needed.

## What's NOT in this Terraform

- **CloudTrail to a third account** — adding it is small, but it's a
  separate concern from the data plane and goes in a different repo
  (security tooling). Documented in the plan's risk register.
- **VPC endpoints for S3** — primary egress is fine over public S3 for the
  Phase 1 pilot. Add Gateway Endpoints when traffic justifies it.
- **AWS budget alarms** — set up via the AWS Console; not tracked here.
