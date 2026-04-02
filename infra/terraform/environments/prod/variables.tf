variable "aws_region" {
  type    = string
  default = "eu-west-1"
}

variable "availability_zones" {
  type    = list(string)
  default = ["eu-west-1a", "eu-west-1b"]
}

variable "cluster_version" {
  type    = string
  default = "1.30"
}

variable "cluster_endpoint_public_access" {
  type    = bool
  default = true
}

variable "cluster_public_access_cidrs" {
  type    = list(string)
  default = ["203.0.113.10/32"]
}

variable "cluster_log_retention_days" {
  type    = number
  default = 90
}

variable "node_instance_types" {
  type    = list(string)
  default = ["m6i.large"]
}

variable "node_capacity_type" {
  type    = string
  default = "ON_DEMAND"
}

variable "node_desired_size" {
  type    = number
  default = 3
}

variable "node_min_size" {
  type    = number
  default = 3
}

variable "node_max_size" {
  type    = number
  default = 8
}

variable "admin_principal_arns" {
  type    = list(string)
  default = []
}

variable "manage_ecr_repositories" {
  type    = bool
  default = false
}

variable "ecr_image_tag_mutability" {
  type    = string
  default = "IMMUTABLE"
}

variable "ecr_force_delete" {
  type    = bool
  default = false
}

variable "ecr_max_image_count" {
  type    = number
  default = 90
}

variable "artifact_bucket_name" {
  type    = string
  default = "sentinelstream-prod-artifacts-change-me"
}
