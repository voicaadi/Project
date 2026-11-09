import docker
from docker.errors import NotFound
IMAGE = "devops-ubuntu:24.04"
NETWORK = "devops-workspace-network"


def get_docker_client():
    return docker.from_env()


def start_workspace(user_id: int, workspace_id: int):
    client = get_docker_client()

    container_name = f"devops-user-{user_id}-workspace-{workspace_id}"
    volume_name = container_name + "-data"

    try:
        container = client.containers.get(container_name)

        if container.status != "running":
            container.start()

        return {
            "container_id": container.short_id,
            "container_name": container.name,
            "status": container.status,
        }

    except NotFound:
        pass

    client.volumes.create(name=volume_name)

    container = client.containers.run(
        IMAGE,
        name=container_name,
        detach=True,
        init=True,
        network_mode="none",
        mem_limit="1g",
        nano_cpus=1_000_000_000,
        pids_limit=128,
        read_only=True,
        tmpfs={
            "/tmp": "rw,noexec,nosuid,size=64m",
            "/run": "rw,noexec,nosuid,size=16m",
        },
        volumes={
            volume_name: {
                "bind": "/home/devops/workspace",
                "mode": "rw",
            }
        },
        user="devops",
        labels={
            "managed_by": "devops-ai",
            "user_id": str(user_id),
            "workspace_id": str(workspace_id),
        },
    )

    return {
        "container_id": container.short_id,
        "container_name": container.name,
        "status": container.status,
    }


def stop_workspace(user_id: int, workspace_id: int):
    client = get_docker_client()

    container_name = f"devops-user-{user_id}-workspace-{workspace_id}"

    try:
        container = client.containers.get(container_name)
        container.stop(timeout=10)

        return {"status": "stopped"}

    except NotFound:
        return {"status": "not_found"}


def get_workspace_status(user_id: int, workspace_id: int):
    client = get_docker_client()

    container_name = f"devops-user-{user_id}-workspace-{workspace_id}"

    try:
        container = client.containers.get(container_name)
        container.reload()

        return {
            "container_id": container.short_id,
            "status": container.status,
        }

    except NotFound:
        return {"status": "not_created"}
def execute_workspace_command(
    user_id: int,
    workspace_id: int,
    command: str,
):
    client = get_docker_client()

    container_name = f"devops-user-{user_id}-workspace-{workspace_id}"

    try:
        container = client.containers.get(container_name)
        container.reload()

        if container.status != "running":
            raise RuntimeError("Workspace is not running")

        # Execute the command inside the user's Ubuntu container.
        exec_result = container.exec_run(
            ["bash", "-lc", command],
            user="devops",
            workdir="/home/devops/workspace",
            demux=True,
        )

        stdout, stderr = exec_result.output

        return {
            "exit_code": exec_result.exit_code,
            "stdout": stdout.decode("utf-8", errors="replace")[-10000:] if stdout else "",
            "stderr": stderr.decode("utf-8", errors="replace")[-10000:] if stderr else "",
        }

    except NotFound:
        raise RuntimeError("Workspace container not found")