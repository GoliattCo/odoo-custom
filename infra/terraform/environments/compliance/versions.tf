terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
  # Uncomment and configure once you have an S3 + DynamoDB backend ready:
  # backend "s3" {
  #   bucket         = "odoo-saas-terraform-state-compliance"
  #   key            = "compliance/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "odoo-saas-terraform-locks-compliance"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      project = "odoo-saas"
      env     = "compliance"
      managed = "terraform"
    }
  }
}
