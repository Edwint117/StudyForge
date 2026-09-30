output "engine_url" { value = try(google_cloud_run_v2_service.engine[0].uri, null) }
output "engine_service_account" { value = google_service_account.engine.email }
output "engine_job_name" { value = try(google_cloud_run_v2_job.long[0].name, null) }
output "artifact_repository" { value = google_artifact_registry_repository.engine.name }
output "engine_canary_url" { value = try([for t in google_cloud_run_v2_service.engine[0].traffic_statuses : t.uri if t.tag == "canary"][0], null) }
