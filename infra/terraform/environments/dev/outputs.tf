output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_oidc_provider_arn" {
  value = module.eks.cluster_oidc_provider_arn
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "artifact_bucket_name" {
  value = module.artifact_store.bucket_name
}

output "ecr_repository_urls" {
  value = try(module.ecr[0].repository_urls, {})
}
