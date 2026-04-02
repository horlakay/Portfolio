variable "cluster_name" {
  type = string
}

variable "cluster_version" {
  type    = string
  default = "1.30"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "cluster_endpoint_public_access" {
  type    = bool
  default = true
}

variable "cluster_public_access_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "cluster_enabled_log_types" {
  type = list(string)
  default = [
    "api",
    "audit",
    "authenticator",
    "controllerManager",
    "scheduler",
  ]
}

variable "cluster_log_retention_days" {
  type    = number
  default = 30
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.large"]
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

variable "tags" {
  type    = map(string)
  default = {}
}
