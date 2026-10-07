# Two-Level Autoscaling for Event-Driven Microservices

This repository is the central infrastructure and orchestration hub for the **Two-Level Autoscaling on Amazon EKS** project. It provides the end-to-end Infrastructure as Code (Terraform), Kubernetes manifests, autoscaling configurations (KEDA + Karpenter), observability stacks, and automated load-testing suites.

## Project Overview

Traditional CPU-based autoscaling often falls short for asynchronous, queue-based workloads. This project demonstrates a production-grade elasticity pattern designed to scale resources accurately according to real-time message backlog (queue depth) while provisioning compute instances on demand.

The architecture implements a two-level elasticity model:
- **Pod-Level Elasticity (KEDA):** Dynamically scales worker pods from `0 → N → 0` based on Amazon SQS queue depth via external metric triggers.
- **Node-Level Elasticity (Karpenter):** Automatically provisions and consolidates EC2 capacity (including Spot instances) just-in-time when pods are pending due to insufficient cluster capacity.

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

## Related Repositories

This infrastructure hosts and orchestrates the following application components:

### 1. [retailstore-backend-microservices](https://github.com/UITMagnolia/retailstore-backend-microservices)
**Role:** Backend Microservices & Asynchronous Processing  
**Description:** Houses the core backend services, including the Producer APIs and background Workers. Implements the business logic, event-driven task processing with Amazon SQS, and container configurations for deployment on Kubernetes.

### 2. [retailstore-android](https://github.com/UITMagnolia/retailstore-android)
**Role:** Mobile Client Application  
**Description:** Native Android client providing the retail store user interface. Interacts with the backend microservices to generate user traffic, handle transactions, and demonstrate real-world workload generation.
