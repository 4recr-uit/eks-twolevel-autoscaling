terraform {
  backend "s3" {
    bucket       = "tfstate-bucket-2006"
    key          = "dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

