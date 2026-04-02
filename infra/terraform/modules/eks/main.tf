terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  access_entries = {
    for index, arn in var.admin_principal_arns :
    "admin-${index}" => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  enable_irsa                               = true
  enable_cluster_creator_admin_permissions  = true
  create_cloudwatch_log_group               = true
  cloudwatch_log_group_retention_in_days    = var.cluster_log_retention_days
  cluster_enabled_log_types                 = var.cluster_enabled_log_types
  cluster_endpoint_private_access           = true
  cluster_endpoint_public_access            = var.cluster_endpoint_public_access
  cluster_endpoint_public_access_cidrs      = var.cluster_public_access_cidrs
  authentication_mode                       = "API_AND_CONFIG_MAP"
  access_entries                            = local.access_entries

  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
  }

  eks_managed_node_groups = {
    general = {
      instance_types = var.node_instance_types
      capacity_type  = var.node_capacity_type
      min_size       = var.node_min_size
      max_size       = var.node_max_size
      desired_size   = var.node_desired_size
      subnet_ids     = var.private_subnet_ids

      labels = {
        workload = "general"
      }

      update_config = {
        max_unavailable_percentage = 50
      }
    }
  }

  tags = var.tags
}
