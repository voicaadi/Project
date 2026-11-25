from __future__ import annotations

import docker
from docker.errors import DockerException, NotFound

IMAGE = "devops-ubuntu:24.04"
MANAGED_BY = "devops-ai-staging"


class DockerWorkspaceManager:
    def __init__(self):
        self.client = docker.from_env()

    @staticmethod
    def _container_name(user_id: int, workspace_id: int) -> str:
        if user_id < 1 or workspace_id < 1:
            raise ValueError("Invalid workspace ownership identifiers")
        return f"devops-staging-user-{user_id}-workspace-{workspace_id}"

    def _get_owned_container(self, user_id: int, workspace_id: int):
        name = self._container_name(user_id, workspace_id)

        try:
            container = self.client.containers.get(name)
        except NotFound:
            return None

        container.reload()
        labels = container.labels

        if (
            labels.get("managed_by") != MANAGED_BY
            or labels.get("user_id") != str(user_id)
            or labels.get("workspace_id") != str(workspace_id)
        ):
            raise PermissionError(
                "Container ownership labels do not match this workspace"
            )

        return container

    def start(self, user_id: int, workspace_id: int):
        name = self._container_name(user_id, workspace_id)
        container = self._get_owned_container(user_id, workspace_id)

        if container is not None:
            if container.status != "running":
                container.start()
                container.reload()

            return {
                "container_id": container.short_id,
                "container_name": container.name,
                "status": container.status,
            }

        self.client.images.get(IMAGE)

        volume_name = name + "-data"
        self.client.volumes.create(name=volume_name)

        container = self.client.containers.run(
            IMAGE,
            name=name,
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
                "managed_by": MANAGED_BY,
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
            },
        )

        return {
            "container_id": container.short_id,
            "container_name": container.name,
            "status": container.status,
        }

    def stop(self, user_id: int, workspace_id: int):
        container = self._get_owned_container(user_id, workspace_id)

        if container is None:
            return {"status": "not_found"}

        if container.status == "running":
            container.stop(timeout=10)

        return {"status": "stopped"}

    def status(self, user_id: int, workspace_id: int):
        container = self._get_owned_container(user_id, workspace_id)

        if container is None:
            return {"status": "not_created"}

        return {
            "container_id": container.short_id,
            "status": container.status,
        }

    def execute(
        self,
        user_id: int,
        workspace_id: int,
        command: str,
    ):
        if not command or len(command) > 1000:
            raise ValueError("Command must contain 1 to 1000 characters")

        container = self._get_owned_container(user_id, workspace_id)

        if container is None:
            raise RuntimeError("Workspace container not found")

        if container.status != "running":
            raise RuntimeError("Workspace is not running")

        result = container.exec_run(
            ["bash", "-lc", command],
            user="devops",
            workdir="/home/devops/workspace",
            demux=True,
        )

        stdout, stderr = result.output

        return {
            "exit_code": result.exit_code,
            "stdout": stdout.decode("utf-8", errors="replace")[-10000:] if stdout else "",
            "stderr": stderr.decode("utf-8", errors="replace")[-10000:] if stderr else "",
        }

    def overview(self):
        self.client.ping()

        info = self.client.info()
        containers = [
            container
            for container in self.client.containers.list(all=True)
            if container.name.startswith("devops-staging-user-")
        ]

        return {
            "online": True,
            "engine": {
                "name": info.get("Name", "Docker Engine"),
                "version": info.get("ServerVersion", "Unknown"),
            },
            "containers": [
                {
                    "id": container.short_id,
                    "name": container.name,
                    "image": (
                        container.image.tags[0]
                        if container.image.tags
                        else "Unknown"
                    ),
                    "status": container.status,
                    "ports": container.ports,
                }
                for container in containers
            ],
        }

    def close(self):
        self.client.close()
