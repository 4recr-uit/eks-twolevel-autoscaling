import os
import sys
from pathlib import Path
import argparse

import boto3
from botocore.exceptions import ClientError, BotoCoreError

def parse_arguments():
    parser = argparse.ArgumentParser(description="Initialize S3 bucket and configure it for Terraform remote backend.")

    parser.add_argument(
        "--bucket-name", 
        default=os.environ.get("S3_BUCKET_NAME"),
        help="Name of the S3 bucket to create"
    )

    parser.add_argument(
        "--region", 
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="AWS Region to create the S3 bucket in (default: us-east-1)"
    )

    parser.add_argument(
        "--environment", 
        default=os.environ.get("ENVIRONMENT", "dev"),
        choices=["dev", "staging", "prod"], 
        help="Environment name (default: dev)"
    )

    parser.add_argument(
        "--account-id",
        default=os.environ.get("AWS_ACCOUNT_ID"),
        help="AWS Account ID"
    )

    return parser.parse_args()

def validate_config(args):
    if not args.bucket_name: 
        raise ValueError("Bucket name cannot be empty.")
    if not args.region.strip():
        raise ValueError("Region cannot be empty.")
    if not args.account_id.isdigit():
        raise ValueError("Account ID must contain only digits")
    if len(args.account_id) != 12:
        raise ValueError("Account ID must be 12 digits")
    if args.environment not in ["dev", "staging", "prod"]:
        raise ValueError("Environment must be one of 'dev', 'staging', or 'prod'.")

def create_bucket(s3, bucket, region, account_id):
    try:
        s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account_id)
        print(f"Bucket {bucket} already exists.")
        return
    except ClientError as e:
        status = e.response["ResponseMetadata"]["HTTPStatusCode"]
        if status != 404:
            raise e
    print(f"Creating bucket {bucket}...")
    params = {"Bucket": bucket}

    if region != "us-east-1":
        params["CreateBucketConfiguration"] = {
            "LocationConstraint": region
        }

    s3.create_bucket(**params)
    s3.get_waiter("bucket_exists").wait(Bucket=bucket)

    print(f"Bucket {bucket} created successfully.")

def configure_bucket(s3, bucket, region, account_id):
    owner = {"ExpectedBucketOwner": account_id}

    s3.head_bucket(Bucket=bucket, **owner)

    response = s3.get_bucket_location(Bucket=bucket, **owner)
    actual_region = response.get("LocationConstraint") or "us-east-1"

    if actual_region == "EU":
        actual_region = "eu-west-1"

    if actual_region != region:
        raise ValueError(f"Bucket region mismatch: {actual_region} != {region}")

    print("Enabling bucket versioning...")

    s3.put_bucket_versioning(
        Bucket=bucket,
        VersioningConfiguration={"Status": "Enabled"},
        **owner
    )

    print("Configuring bucket encryption...")

    s3.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }
            ]
        },
        **owner
    )

    print("Blocking public access...")

    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True
        },
        **owner
    )

    print("Configuring bucket ownership...")

    s3.put_bucket_ownership_controls(
        Bucket=bucket,
        OwnershipControls={
            "Rules": [
                {
                    "ObjectOwnership": "BucketOwnerEnforced"
                }
            ]
        },
        **owner
    )

    print(f"Bucket {bucket} configured successfully.")

def print_backend_info(bucket, region, environment, account_id):
    state_key = f"{environment}/terraform.tfstate"

    print("\n" + "=" * 50)
    print("TERRAFORM REMOTE BACKEND READY")
    print("=" * 50)
    print(f"Bucket Name : {bucket}")
    print(f"AWS Region  : {region}")
    print(f"Environment : {environment}")
    print(f"Account ID  : {account_id}")
    print(f"State Key   : {state_key}")
    print("Encryption  : SSE-S3 (AES256)")
    print("Versioning  : Enabled")
    print("Locking     : S3 Native Lockfile")
    print("=" * 50)

    print("\nTerraform backend configuration:\n")

    print(f'''terraform {{
  backend "s3" {{
    bucket       = "{bucket}"
    key          = "{state_key}"
    region       = "{region}"
    encrypt      = true
    use_lockfile = true
  }}
}}''')

def main():
    parser = parse_arguments()

    session = boto3.Session(profile_name="default", region_name=parser.region)
    sts = session.client("sts")
    s3 = session.client("s3")
    parser.account_id = sts.get_caller_identity()["Account"]

    validate_config(parser)
    print(f"Bucket Name: {parser.bucket_name}")
    print(f"Region: {parser.region}")
    print(f"Environment: {parser.environment}")
    print(f"Account ID: {parser.account_id}")
    
    create_bucket(s3, parser.bucket_name, parser.region, parser.account_id)
    configure_bucket(s3, parser.bucket_name, parser.region, parser.account_id)
    print_backend_info(parser.bucket_name, parser.region, parser.environment, parser.account_id)

if __name__ == "__main__":
    try:
        main()
    except (ClientError, BotoCoreError, Exception) as e:
        print(f"Error: {e}")
        sys.exit(1)