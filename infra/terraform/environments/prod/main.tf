terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}

locals {
  project = "sentinelstream"
  name    = "${local.project}-prod"
  services = [
    "ingestion-service",
    "feature-service",
    "rule-engine",
    "model-service",
    "decision-service",
    "feedback-service",
    "analyst-console",
  ]
  tags = {
    project     = local.project
    environment = "prod"
    managed_by  = "terraform"
  }
}

module "network" {
  source               = "../../modules/network"
  name                 = local.name
  vpc_cidr             = "10.50.0.0/16"
  public_subnet_cidrs  = ["10.50.0.0/24", "10.50.1.0/24"]
  private_subnet_cidrs = ["10.50.10.0/24", "10.50.11.0/24"]
  availability_zones   = var.availability_zones
  kubernetes_cluster_name = local.name
  enable_nat_gateway      = true
  tags                 = local.tags
}

module "eks" {
  source                         = "../../modules/eks"
  cluster_name                   = local.name
  cluster_version                = var.cluster_version
  vpc_id                         = module.network.vpc_id
  private_subnet_ids             = module.network.private_subnet_ids
  cluster_endpoint_public_access = var.cluster_endpoint_public_access
  cluster_public_access_cidrs    = var.cluster_public_access_cidrs
  node_instance_types            = var.node_instance_types
  node_capacity_type             = var.node_capacity_type
  node_desired_size              = var.node_desired_size
  node_min_size                  = var.node_min_size
  node_max_size                  = var.node_max_size
  admin_principal_arns           = var.admin_principal_arns
  cluster_log_retention_days     = var.cluster_log_retention_days
  tags                           = local.tags
}

module "ecr" {
  count                = var.manage_ecr_repositories ? 1 : 0
  source               = "../../modules/ecr"
  repositories         = [for service in local.services : "${local.project}/${service}"]
  image_tag_mutability = var.ecr_image_tag_mutability
  force_delete         = var.ecr_force_delete
  max_image_count      = var.ecr_max_image_count
  tags                 = local.tags
}

module "artifact_store" {
  source      = "../../modules/artifact-store"
  bucket_name = var.artifact_bucket_name
  tags        = local.tags
}
