#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo "Script không nhận tham số." >&2; exit 2; }

# amiAlias xác định bản image hệ điều hành dùng để Karpenter tạo EC2 node. AMI chứa hệ điều hành và các thành phần cần để node tham gia EKS; khác với Docker image của ứng dụng.

# Lấy AMI được AWS khuyến nghị với EKS cluster version là 1.36
aws ssm get-parameter --region us-east-1 --name "/aws/service/eks/optimized-ami/1.36/amazon-linux-2023/x86_64/standard/recommended/image_id" --query "Parameter.Value" --output text
# Kết quả trả về ví dụ: ami-0676d7e7e91ed014c

# Lấy tên AMI, thay ami-xxxxxxxx bằng kết quả bước trên, ví dụ với ami-0676d7e7e91ed014c
aws ec2 describe-images --region us-east-1 --image-ids ami-0676d7e7e91ed014c --query "Images[0].Name" --output text
# Kết quả trả về ví dụ: amazon-eks-node-al2023-x86_64-standard-1.36-v20261026

# => Điền vào kubernetes/environments/dev/platform.yaml:
# nodePool:
#   amiAlias: "al2023@v20261026"
