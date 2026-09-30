variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-east1"
}
variable "billing_account" { type = string }
variable "artifact_repo" {
  type    = string
  default = "studyforge"
}
variable "engine_image" {
  type    = string
  default = ""
  validation {
    condition     = !var.enable_runtime || can(regex("@sha256:[0-9a-f]{64}$", var.engine_image))
    error_message = "Use an immutable Artifact Registry image digest."
  }
}
variable "engine_release" {
  type    = string
  default = "unknown" # git sha; becomes the Sentry release (Cloud Run jobs have no K_REVISION)
}
variable "engine_secret_versions" {
  type    = map(string)
  default = {}
  validation {
    condition = !var.enable_runtime || alltrue([for key in ["ENGINE_DATABASE_URL", "ENGINE_RPC_SECRET", "ENGINE_WAKE_SECRET"] :
    can(regex("^[1-9][0-9]*$", lookup(var.engine_secret_versions, key, "")))])
    error_message = "Pin required engine secrets to numeric versions for reproducible rollback."
  }
}
variable "engine_job_name" {
  type    = string
  default = "sf-engine-long"
}

variable "enable_runtime" {
  type    = bool
  default = false
}
variable "engine_canary_previous_revision" {
  type    = string
  default = ""
}
variable "engine_canary_percent" {
  type    = number
  default = 100
  validation {
    condition     = var.engine_canary_percent >= 0 && var.engine_canary_percent <= 100
    error_message = "Canary percent must be 0-100."
  }
}
