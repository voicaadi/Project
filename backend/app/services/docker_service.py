import docker
from docker.errors import DockerException, NotFound

client = docker.from_env()


def get_containers():
    """Return container information for the dashboard."""
    containers = client.containers.list(all=True)
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
    return client.info()


def run_docker_operation(action: str, target: str | None = None) -> str:
    """Run a small set of approved, read-only Docker operations."""
    try:
        if action == "ps":
            containers = client.containers.list()
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
            images = client.images.list()
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

            container = client.containers.get(target.strip())

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
