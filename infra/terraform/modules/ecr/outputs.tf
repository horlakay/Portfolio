output "registry_id" {
  value = try(values(aws_ecr_repository.repos)[0].registry_id, null)
}

output "repository_urls" {
  value = { for name, repository in aws_ecr_repository.repos : name => repository.repository_url }
}

output "repository_arns" {
  value = { for name, repository in aws_ecr_repository.repos : name => repository.arn }
}
