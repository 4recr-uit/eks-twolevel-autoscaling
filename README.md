# Two-Level Autoscaling for Event-Driven Microservices

This repository is the infrastructure and orchestration hub for the **Two-Level Autoscaling on Amazon EKS** project. It contains Terraform for AWS infrastructure and optional monitoring, plus Kubernetes manifests for application deployment.

## Project Overview

Traditional CPU-based autoscaling often falls short for asynchronous, queue-based workloads. This coursework project demonstrates scaling worker pods from queue backlog and provisioning EC2 nodes when needed.

The architecture implements a two-level elasticity model:
- **Pod-Level Elasticity (KEDA):** Dynamically scales worker pods from `0 → N → 0` based on Amazon SQS queue depth via external metric triggers.
- **Node-Level Elasticity (Karpenter):** Automatically provisions and consolidates On-Demand EC2 capacity when pods are pending due to insufficient cluster capacity. Spot is an optional later experiment.

This repository provisions the underlying AWS platform and coordinates the deployment, scaling policies, and benchmarking experiments across the entire ecosystem.

## System Architecture

![System Architecture](assets/infrastructure.png)

**Core Data Flow:** 
`Traffic (k6)` → `Producer API` → `Amazon SQS` → `Worker Pods (Scaled by KEDA)` → `EC2 Nodes (Provisioned by Karpenter)`

## Technology Stack

* **Cloud Provider:** Amazon Web Services (EKS, EC2, SQS, ECR, IAM, VPC)
* **Infrastructure as Code (IaC):** Terraform
* **Orchestration & Scaling:** Kubernetes, KEDA, HPA, Karpenter
* **Messaging:** Amazon SQS (Decoupling Producers and Workers)
* **Observability:** Prometheus, Grafana
* **Load Testing:** k6

---

## KEDA deployment

See [Terraform deployment](terraform/README.md) for the staged apply sequence, RDS configuration, EKS API CIDR, budget and optional monitoring.

Terraform pins EKS `1.36`, Karpenter `1.15.0`, and KEDA `2.21.0`. The KEDA module installs the official Helm chart in the `keda` namespace and creates a `ClusterTriggerAuthentication` named `keda-sqs-pod-identity`. Its operator ServiceAccount is `keda-operator`, matching the EKS Pod Identity association and read-only SQS policy in the IAM module. No AWS access keys are stored in Kubernetes.

The three SQS `ScaledObject` resources are defined in Terraform but disabled by default (`enable_keda_scaled_objects = false`). First deploy the `retailstore` namespace and the `cart-worker`, `checkout-worker`, and `orders-worker` Deployments with those exact names. Then set `enable_keda_scaled_objects = true` and apply Terraform. Each worker must use its corresponding SQS queue; only KEDA should manage its replicas while the SQS scaler is enabled. Do not apply the empty files under `kubernetes/keda/` as an additional owner of the same resources.

The default target is 10 messages per replica, with 0–10 replicas, a 30-second poll, and a 300-second cooldown. Tune `keda_queue_length`, `keda_min_replica_count`, `keda_max_replica_count`, `keda_polling_interval`, and `keda_cooldown_period` through Terraform variables. For the CPU HPA comparison, remove or disable a worker's KEDA `ScaledObject` before attaching a separate HPA to that Deployment.

Verify after deployment with `helm status keda -n keda`, `kubectl get clustertriggerauthentication keda-sqs-pod-identity`, and `kubectl get scaledobjects -n retailstore`. The last command will show no objects until the switch is enabled.

## SQS workload identities

The IAM module creates one EKS Pod Identity role and association per outbox publisher and per worker. Each publisher can send to its own main queue; each worker can consume only its own main queue. Worker roles have no DLQ permissions. KEDA has a separate read-only role for queue depth.

| Main queue | Publisher ServiceAccount | Worker ServiceAccount |
|---|---|---|
| `cart-queue` | `cart-publisher` | `cart-worker` |
| `checkout-queue` | `checkout-publisher` | `checkout-worker` |
| `orders-queue` | `orders-publisher` | `orders-worker` |

The ServiceAccounts are defined in `kubernetes/apps/service-accounts.yaml` for namespace `retailstore`. Create the namespace, then run `kubectl apply -k kubernetes/apps`. Future publisher and worker Deployments must set the matching `serviceAccountName`; API Deployments write to their DB outboxes and do not need these SQS roles. Terraform exports maps of role ARNs and ServiceAccount names keyed by main queue. Investigate or redrive DLQs with a separate operator identity.

The seed Managed Node Group keeps the node IAM role exported as `eks_node_role_arn`. Karpenter uses a separate EC2 node role exported as `karpenter_node_role_arn`; its controller's `iam:PassRole`, EKS `EC2_LINUX` access entry, and `EC2NodeClass.spec.role` all reference that dedicated role. The Karpenter controller uses a separate Pod Identity role. Its six IAM policies in `terraform/modules/karpenter/controller-policy.tf` follow the [Karpenter v1.15.0 reference](https://karpenter.sh/v1.15/reference/cloudformation/); validate with `terraform plan` and a real node provisioning test before marking the deployment complete.

Both seed and Karpenter nodes attach the EKS primary cluster security group and the shared `eks_node_security_group_id`. The seed node group uses a custom launch template; `EC2NodeClass` selects the two groups by ID. Terraform now creates two private Single-AZ RDS instances, each with a database SG allowing only its database port from `eks_node_security_group_id`. This is node-level network access, so database users and credentials must still limit each service. If the seed node group already exists, inspect `terraform plan` for replacement before applying the launch-template change.

---

## Related Repositories

This infrastructure hosts and orchestrates the following application components:

### 1. [retailstore-backend-microservices](https://github.com/UITMagnolia/retailstore-backend-microservices)
**Role:** Backend Microservices & Asynchronous Processing  
**Description:** Houses the core backend services, including the Producer APIs and background Workers. Implements the business logic, event-driven task processing with Amazon SQS, and container configurations for deployment on Kubernetes.

### 2. [retailstore-android](https://github.com/UITMagnolia/retailstore-android)
**Role:** Mobile Client Application  
**Description:** Native Android client providing the retail store user interface. Interacts with the backend microservices to generate user traffic, handle transactions, and demonstrate real-world workload generation.
