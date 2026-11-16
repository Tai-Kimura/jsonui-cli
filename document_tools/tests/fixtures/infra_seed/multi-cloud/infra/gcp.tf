provider "google" {
  project = "example-project"
  region  = "asia-northeast1"
}

resource "google_cloud_run_v2_service" "reports" {
  name     = "reports"
  location = "asia-northeast1"
  template {
    containers {
      image = "example/reports:1"
      env {
        name  = "DB"
        value = google_sql_database_instance.reports.connection_name
      }
    }
  }
}

resource "google_sql_database_instance" "reports" {
  name             = "reports"
  database_version = "POSTGRES_16"
}

resource "google_storage_bucket" "exports" {
  name     = "example-exports"
  location = "ASIA"
}
