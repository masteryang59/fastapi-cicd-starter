variable "project_id" {
  description = "Google Cloud project to deploy into."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "github_repository" {
  description = "The GitHub repository allowed to deploy, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use the owner/name form, e.g. acme/fastapi-cicd-starter."
  }
}

variable "service_name" {
  description = "Base name. Each environment gets a Cloud Run service called <service_name>-<environment>."
  type        = string
  default     = "shortlinks"
}

variable "environments" {
  description = "GitHub environments, one Cloud Run service each. Must match the names in ci.yml."
  type        = list(string)
  default     = ["staging", "production"]
}

variable "repository_id" {
  description = "Artifact Registry repository for the images."
  type        = string
  default     = "apps"
}

variable "bootstrap_image" {
  description = "Image for the very first revision, before the pipeline has deployed anything."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "database_url_secrets" {
  description = <<-EOT
    Optional Secret Manager secret ids holding a PostgreSQL DATABASE_URL, per environment,
    e.g. { production = "shortlinks-production-db-url" }. Create the secrets yourself, so the
    password never appears in Terraform state. Without one, the service uses SQLite in /tmp,
    which is lost whenever an instance stops.
  EOT
  type        = map(string)
  default     = {}
}

variable "admin_api_key_secrets" {
  description = "Optional Secret Manager secret ids holding ADMIN_API_KEY, per environment."
  type        = map(string)
  default     = {}
}

variable "public" {
  description = "Allow unauthenticated requests (it's a URL shortener). Some org policies forbid allUsers."
  type        = bool
  default     = true
}

variable "max_instances" {
  description = "Upper bound on instances per service; keeps a traffic spike from becoming a bill."
  type        = number
  default     = 3
}

variable "deletion_protection" {
  description = "Stop `terraform destroy` from deleting the services."
  type        = bool
  default     = false
}
variable "prefetch_data" {
  type    = bool
  default = true
}