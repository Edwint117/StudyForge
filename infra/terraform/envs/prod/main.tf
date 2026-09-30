locals {
  apis = toset([
    "run.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com",
    "compute.googleapis.com", "cloudbilling.googleapis.com", "billingbudgets.googleapis.com",
    "iamcredentials.googleapis.com", "logging.googleapis.com", "monitoring.googleapis.com"
  ])
  secret_names = toset([
    "ENGINE_DATABASE_URL", "ENGINE_RPC_SECRET", "ENGINE_WAKE_SECRET", "SUPABASE_SERVICE_ROLE_KEY",
    "ANTHROPIC_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "DEEPGRAM_API_KEY",
    "ASSEMBLYAI_API_KEY", "MISTRAL_API_KEY", "VOYAGE_API_KEY", "OPENAI_API_KEY", "SENTRY_DSN"
  ])
}
resource "google_project_service" "api" {
  for_each           = local.apis
  service            = each.value
  disable_on_destroy = false
}
resource "google_artifact_registry_repository" "engine" {
  repository_id = var.artifact_repo
  location      = var.region
  format        = "DOCKER"
  depends_on    = [google_project_service.api]
}
resource "google_service_account" "engine" {
  account_id   = "sf-engine"
  display_name = "StudyForge engine runtime"
}
resource "google_service_account" "batch" {
  account_id   = "sf-engine-long"
  display_name = "StudyForge long job runtime"
}
resource "google_secret_manager_secret" "engine" {
  for_each  = local.secret_names
  secret_id = "sf-${lower(replace(each.value, "_", "-"))}"
  replication {
    auto {}
  }
  depends_on = [google_project_service.api]
}
resource "google_secret_manager_secret_iam_member" "service" {
  for_each  = local.secret_names
  secret_id = google_secret_manager_secret.engine[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.engine.email}"
}
resource "google_secret_manager_secret_iam_member" "batch" {
  for_each  = local.secret_names
  secret_id = google_secret_manager_secret.engine[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.batch.email}"
}
resource "google_cloud_run_v2_service" "engine" {
  count               = var.enable_runtime ? 1 : 0
  name                = "sf-engine"
  location            = var.region
  deletion_protection = true
  ingress             = "INGRESS_TRAFFIC_ALL"
  # Canary (doc 02 section 6): deploy-prod first applies with the previous serving revision pinned and the new one at
  # engine_canary_percent behind the "canary" tag, health-checks the tag URL, then applies again with no previous
  # revision so the latest revision takes 100%.
  dynamic "traffic" {
    for_each = var.engine_canary_previous_revision == "" ? [1] : []
    content {
      type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
      percent = 100
    }
  }
  dynamic "traffic" {
    for_each = var.engine_canary_previous_revision == "" ? [] : [1]
    content {
      type     = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION"
      revision = var.engine_canary_previous_revision
      percent  = 100 - var.engine_canary_percent
    }
  }
  dynamic "traffic" {
    for_each = var.engine_canary_previous_revision == "" ? [] : [1]
    content {
      type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
      percent = var.engine_canary_percent
      tag     = "canary"
    }
  }
  template {
    service_account                  = google_service_account.engine.email
    timeout                          = "3600s"
    max_instance_request_concurrency = 4
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.engine_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "1Gi" }
        cpu_idle = true
      }
      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "ENGINE_POLL_MODE"
        value = "0"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "ENGINE_RELEASE"
        value = var.engine_release
      }
      dynamic "env" {
        for_each = var.engine_secret_versions
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.engine[env.key].secret_id
              version = env.value
            }
          }
        }
      }
      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 10
        failure_threshold     = 12
        http_get { path = "/health" }
      }
      liveness_probe {
        period_seconds = 30
        http_get { path = "/health" }
      }
    }
  }
  depends_on = [google_project_service.api, google_secret_manager_secret_iam_member.service, google_service_account_iam_member.deployer_act_as]
}
# pg_net cannot obtain Google identity tokens. The engine validates all work with HMAC.
# Only liveness is unauthenticated; the sandbox must never have an allUsers binding.
resource "google_cloud_run_v2_service_iam_member" "signed_ingress" {
  count    = var.enable_runtime ? 1 : 0
  name     = google_cloud_run_v2_service.engine[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
resource "google_cloud_run_v2_job" "long" {
  count               = var.enable_runtime ? 1 : 0
  name                = var.engine_job_name
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.batch.email
      timeout         = "86400s"
      max_retries     = 0 # pgmq owns retries and attempts.
      containers {
        image   = var.engine_image
        command = ["python", "-m", "engine.jobs.entrypoint"]
        resources {
          limits = { cpu = "2", memory = "4Gi" }
        }
        env {
          name  = "APP_ENV"
          value = "production"
        }
        env {
          name  = "ENGINE_POLL_MODE"
          value = "0"
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "GCP_REGION"
          value = var.region
        }
        env {
          name  = "ENGINE_RELEASE"
          value = var.engine_release
        }
        dynamic "env" {
          for_each = var.engine_secret_versions
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.engine[env.key].secret_id
                version = env.value
              }
            }
          }
        }
      }
    }
  }
  depends_on = [google_project_service.api, google_secret_manager_secret_iam_member.batch, google_service_account_iam_member.deployer_act_as]
}
resource "google_cloud_run_v2_job_iam_member" "dispatch" {
  count    = var.enable_runtime ? 1 : 0
  name     = google_cloud_run_v2_job.long[0].name
  location = var.region
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = "serviceAccount:${google_service_account.engine.email}"
}
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "StudyForge monthly guardrail"
  budget_filter { projects = ["projects/${data.google_project.current.number}"] }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = "5"
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }
  depends_on = [google_project_service.api]
}
data "google_project" "current" {}
resource "google_logging_project_bucket_config" "default" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = 30
}

resource "google_service_account_iam_member" "deployer_act_as" {
  for_each = {
    service = google_service_account.engine.name
    batch   = google_service_account.batch.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:sf-deployer@${var.project_id}.iam.gserviceaccount.com"
}
