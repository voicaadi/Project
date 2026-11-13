
resource "kubernetes_deployment_v1" "backend" {
  metadata {
    name      = "devops-ai-backend"
    namespace = "devops-ai"

    labels = {
      app = "devops-ai-backend"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "devops-ai-backend"
      }
    }

    template {
      metadata {
        labels = {
          app = "devops-ai-backend"
        }

        annotations = {
          "kubectl.kubernetes.io/restartedAt" = "2026-11-11T18:36:20+02:00"
        }
      }

      spec {
        container {
          name              = "backend"
          image             = "ghcr.io/voicaadi/devops-ai-backend:latest"
          image_pull_policy = "Always"

          port {
            container_port = 8000
          }

          env_from {
            secret_ref {
              name = "devops-ai-secrets"
            }
          }

          env {
            name  = "POSTGRES_HOST"
            value = "postgres"
          }

          env {
            name  = "POSTGRES_PORT"
            value = "5432"
          }

          env {
            name  = "POSTGRES_DB"
            value = "devops_ai"
          }

          env {
            name  = "POSTGRES_USER"
            value = "devops_user"
          }

          env {
            name = "RESEND_API_KEY"

            value_from {
              secret_key_ref {
                name = "devops-ai-resend"
                key  = "RESEND_API_KEY"
              }
            }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }

            initial_delay_seconds = 10
            period_seconds        = 5
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }

            initial_delay_seconds = 20
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "backend" {
  metadata {
    name      = "backend"
    namespace = "devops-ai"
  }

  spec {
    selector = {
      app = "devops-ai-backend"
    }

    port {
      port        = 8000
      target_port = 8000
    }

    type = "ClusterIP"
  }
}
