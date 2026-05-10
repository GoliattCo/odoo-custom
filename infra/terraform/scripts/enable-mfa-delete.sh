#!/bin/bash
# enable-mfa-delete.sh
#
# Enables MFA Delete on the COMPLIANCE bucket. S3 requires this be done with
# root credentials AND a current MFA token at enable-time; Terraform can't
# do it (the AWS SDK call doesn't accept assume-role credentials for this
# specific operation). That's why it lives here, as a one-shot runbook step
# run after `terraform apply` on the compliance composition.
#
# Once enabled:
#   - Any DeleteObject / DeleteObjectVersion / version suspension on the
#     bucket requires the requester to present an MFA token.
#   - Combined with Object Lock COMPLIANCE 10y, the regulated archive
#     becomes effectively unkillable for the retention window even by
#     a compromised root account, because both retention AND MFA Delete
#     guard the deletion path.
#
# Reversal: re-run with Status=Suspended,MFADelete=Disabled (also requires
# MFA). Document any reversal in the audit log per Habeas Data process.

set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 -b BUCKET -s MFA_SERIAL -c MFA_CODE [-p AWS_PROFILE]

Required:
  -b BUCKET       The compliance bucket name (e.g., the s3_compliance_bucket_name
                  output from the compliance Terraform composition).
  -s MFA_SERIAL   MFA device serial number, e.g.:
                    arn:aws:iam::<compliance-account-id>:mfa/<device-name>
  -c MFA_CODE     6-digit code from the MFA device, captured in the same
                  ~30-second window as you run this script.

Optional:
  -p AWS_PROFILE  AWS profile to authenticate with. Must be the
                  compliance-account ROOT user — MFA Delete cannot be
                  enabled by IAM users, only by root.

Example:
  $0 -b acme-odoo-saas-compliance \\
     -s arn:aws:iam::222222222222:mfa/ops-yubikey \\
     -c 123456 \\
     -p saas-compliance-root
EOF
}

BUCKET=""
MFA_SERIAL=""
MFA_CODE=""
AWS_PROFILE_ARG=""

while getopts ":b:s:c:p:h" opt; do
    case "$opt" in
        b) BUCKET="$OPTARG" ;;
        s) MFA_SERIAL="$OPTARG" ;;
        c) MFA_CODE="$OPTARG" ;;
        p) AWS_PROFILE_ARG="--profile $OPTARG" ;;
        h) usage; exit 0 ;;
        *) usage; exit 1 ;;
    esac
done

if [ -z "$BUCKET" ] || [ -z "$MFA_SERIAL" ] || [ -z "$MFA_CODE" ]; then
    echo "Missing required argument." >&2
    usage
    exit 1
fi

if ! [[ "$MFA_CODE" =~ ^[0-9]{6}$ ]]; then
    echo "MFA_CODE must be exactly 6 digits." >&2
    exit 1
fi

echo "→ Enabling MFA Delete on bucket: $BUCKET"
# shellcheck disable=SC2086
aws s3api put-bucket-versioning \
    $AWS_PROFILE_ARG \
    --bucket "$BUCKET" \
    --versioning-configuration Status=Enabled,MFADelete=Enabled \
    --mfa "$MFA_SERIAL $MFA_CODE"

echo "→ Verifying versioning + MFA Delete state:"
# shellcheck disable=SC2086
aws s3api get-bucket-versioning $AWS_PROFILE_ARG --bucket "$BUCKET"

cat <<EOF

Done.

Capture the output above (Status=Enabled, MFADelete=Enabled) in your
deployment journal — auditors will ask for proof MFA Delete was enabled,
not just that you intended to.
EOF
