
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
      }

      spec {
        container {
          name              = "frontend"
          image             = "devops-ai-frontend:local"
          image_pull_policy = "IfNotPresent"

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
