resource "kubernetes_namespace_v1" "devops_ai" {
  metadata {
    name = "devops-ai"

    labels = {
      app         = "devops-ai"
      environment = "local"
    }
  }
}