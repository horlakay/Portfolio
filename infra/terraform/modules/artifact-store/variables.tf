variable "bucket_name" {
  type = string
}

variable "noncurrent_version_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
