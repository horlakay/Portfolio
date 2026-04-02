variable "repositories" {
  type = list(string)
}

variable "image_tag_mutability" {
  type    = string
  default = "IMMUTABLE"
}

variable "force_delete" {
  type    = bool
  default = false
}

variable "max_image_count" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
