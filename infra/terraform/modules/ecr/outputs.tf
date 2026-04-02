output "registry_id" {
  value = one(values(aws_ecr_repository.repos)).registry_id
}

output "repository_urls" {
  value = { for name, repository in aws_ecr_repository.repos : name => repository.repository_url }
}

output "repository_arns" {
  value = { for name, repository in aws_ecr_repository.repos : name => repository.arn }
}
