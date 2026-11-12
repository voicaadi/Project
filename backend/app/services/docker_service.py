
import docker
from docker.errors import DockerException, NotFound

client = None


def get_docker_client():
    """Connect to Docker only when a Docker operation is requested."""
    global client

    if client is None:
        try:
            client = docker.from_env()
            client.ping()
        except DockerException as exc:
            client = None
            raise RuntimeError(
                "Docker Engine is unavailable. "
                "Docker operations are not yet configured for Kubernetes."
            ) from exc

    return client


def get_containers():
    """Return container information for the dashboard."""
    docker_client = get_docker_client()
    containers = docker_client.containers.list(all=True)

    return [
        {
            "id": container.short_id,
            "name": container.name,
            "image": container.image.tags[0] if container.image.tags else "Unknown",
            "status": container.status,
            "ports": container.ports,
        }
        for container in containers
    ]


def get_docker_info():
    """Return Docker Engine information."""
    return get_docker_client().info()


def run_docker_operation(action: str, target: str | None = None) -> str:
    """Run a small set of approved, read-only Docker operations."""
    try:
        docker_client = get_docker_client()

        if action == "ps":
            containers = docker_client.containers.list()

            if not containers:
                return "No running containers."

            lines = ["CONTAINER ID\\tIMAGE\\tSTATUS\\tNAME"]

            for container in containers:
                image = container.image.tags[0] if container.image.tags else "unknown"
                lines.append(
                    f"{container.short_id}\\t{image}\\t{container.status}\\t{container.name}"
                )

            return "\\n".join(lines)

        if action == "images":
            images = docker_client.images.list()

            if not images:
                return "No Docker images found."

            lines = ["IMAGE\\tID\\tSIZE"]

            for image in images:
                tags = ", ".join(image.tags) if image.tags else "<none>"
                size_mb = round(image.attrs.get("Size", 0) / (1024 * 1024), 1)
                lines.append(f"{tags}\\t{image.short_id}\\t{size_mb} MB")

            return "\\n".join(lines)

        if action in {"logs", "inspect"}:
            if not target or not target.strip():
                raise ValueError("Select a container first.")

            container = docker_client.containers.get(target.strip())

            if action == "logs":
                output = container.logs(
                    tail=200,
                    timestamps=True,
                    stdout=True,
                    stderr=True,
                )
                return output.decode("utf-8", errors="replace") or "No logs available."

            attrs = container.attrs
            config = attrs.get("Config", {})
            state = attrs.get("State", {})
            network = attrs.get("NetworkSettings", {})
            ports = network.get("Ports") or {}

            return (
                f"Name: {attrs.get('Name', '').lstrip('/')}\\n"
                f"ID: {attrs.get('Id', '')[:12]}\\n"
                f"Image: {config.get('Image', 'unknown')}\\n"
                f"Status: {state.get('Status', 'unknown')}\\n"
                f"Created: {attrs.get('Created', 'unknown')}\\n"
                f"Ports: {ports}"
            )

        raise ValueError("Unsupported operation. Allowed: ps, images, logs, inspect.")

    except NotFound:
        raise ValueError(f"Container '{target}' was not found.")
    except DockerException as exc:
        raise RuntimeError(f"Docker error: {exc}") from exc
