output "github_variables" {
  description = "Variables to set on each GitHub environment (Settings > Environments > <name>)."
  value = {
    for env, service in local.services : env => {
      GCP_PROJECT_ID                 = var.project_id
      GCP_REGION                     = var.region
      GCP_WORKLOAD_IDENTITY_PROVIDER = google_iam_workload_identity_pool_provider.github.name
      GCP_SERVICE_ACCOUNT            = google_service_account.deployer.email
      GAR_REPOSITORY                 = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/${var.service_name}"
      CLOUD_RUN_SERVICE              = service
    }
  }
}

output "gh_commands" {
  description = "The same variables as GitHub CLI commands. Run them from a clone of the repository."
  value = join("\n", concat(
    ["gh variable set DEPLOY_TARGET --body gcp"],
    flatten([
      for env, service in local.services : [
        "gh variable set GCP_PROJECT_ID --env ${env} --body ${var.project_id}",
        "gh variable set GCP_REGION --env ${env} --body ${var.region}",
        "gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --env ${env} --body ${google_iam_workload_identity_pool_provider.github.name}",
        "gh variable set GCP_SERVICE_ACCOUNT --env ${env} --body ${google_service_account.deployer.email}",
        "gh variable set GAR_REPOSITORY --env ${env} --body ${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/${var.service_name}",
        "gh variable set CLOUD_RUN_SERVICE --env ${env} --body ${service}",
      ]
    ]),
  ))
}

output "service_urls" {
  description = "Live URL of each environment."
  value       = { for env, svc in google_cloud_run_v2_service.app : env => svc.uri }
}
variable "warm_cache" {
  type    = bool
  default = true
}