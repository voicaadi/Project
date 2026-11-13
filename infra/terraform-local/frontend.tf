
resource "kubernetes_deployment_v1" "frontend" {
  metadata {
    name      = "devops-ai-frontend"
    namespace = kubernetes_namespace_v1.devops_ai.metadata[0].name

    labels = {
      app = "devops-ai-frontend"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "devops-ai-frontend"
      }
    }

    template {
      metadata {
        labels = {
          app = "devops-ai-frontend"
        }

        annotations = {
          "kubectl.kubernetes.io/restartedAt" = "2026-11-12T23:57:38+02:00"
        }
      }

      spec {
        container {
          name              = "frontend"
          image             = "ghcr.io/voicaadi/devops-ai-frontend:latest"
          image_pull_policy = "Always"

          port {
            container_port = 80
          }

          resources {
            requests = {
              cpu    = "50m"
              memory = "64Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "256Mi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "frontend" {
  metadata {
    name      = "frontend"
    namespace = kubernetes_namespace_v1.devops_ai.metadata[0].name
  }

  spec {
    selector = {
      app = "devops-ai-frontend"
    }

    port {
      port        = 80
      target_port = 80
    }

    type = "ClusterIP"
  }
}
