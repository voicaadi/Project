
resource "kubernetes_service_v1" "postgres_external" {
  metadata {
    name      = "postgres"
    namespace = "devops-ai"
  }

  spec {
    type = "ExternalName"

    external_name = "host.docker.internal"
  }
}
