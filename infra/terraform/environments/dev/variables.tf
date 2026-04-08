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
  default = ["0.0.0.0/0"]
}

variable "cluster_log_retention_days" {
  type    = number
  default = 30
}

variable "node_instance_types" {
  type    = list(string)
  default = ["m7i-flex.large"]
}

variable "node_capacity_type" {
  type    = string
  default = "ON_DEMAND"
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 5
}

variable "admin_principal_arns" {
  type    = list(string)
  default = []
}

variable "manage_ecr_repositories" {
  type    = bool
  default = true
}

variable "ecr_image_tag_mutability" {
  type    = string
  default = "MUTABLE"
}

variable "ecr_force_delete" {
  type    = bool
  default = true
}

variable "ecr_max_image_count" {
  type    = number
  default = 60
}

variable "artifact_bucket_name" {
  type    = string
  default = "sentinelstream-dev-artifacts-change-me"
}
