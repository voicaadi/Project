import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from docker_terminal import DockerTerminalManager, DockerTerminalSession


class TestDockerTerminalManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.container = MagicMock()
        self.container.id = "container-123"
        self.container.status = "running"

        self.docker_manager = MagicMock()
        self.docker_manager._get_owned_container.return_value = self.container
        self.docker_manager.client.api.exec_create.return_value = {
            "Id": "exec-123"
        }

        self.socket = MagicMock()
        self.docker_manager.client.api.exec_start.return_value = self.socket

        self.send_message = AsyncMock()
        self.manager = DockerTerminalManager(
            self.docker_manager,
            self.send_message,
        )

    async def test_open_creates_owned_container_terminal(self):
        with patch.object(
            self.manager,
            "_read_output",
            new_callable=AsyncMock,
        ):
            await self.manager.open("session-1", 1, 1, 30, 100)

        self.docker_manager._get_owned_container.assert_called_once_with(1, 1)
        self.docker_manager.client.api.exec_create.assert_called_once()
        self.docker_manager.client.api.exec_start.assert_called_once_with(
            "exec-123",
            detach=False,
            tty=True,
            socket=True,
        )
        self.assertIn("session-1", self.manager.sessions)

        await self.manager.close_all()

    async def test_open_rejects_wrong_container_owner(self):
        self.docker_manager._get_owned_container.side_effect = PermissionError(
            "Container ownership labels do not match"
        )

        with self.assertRaises(PermissionError):
            await self.manager.open("session-2", 2, 1)

        self.docker_manager.client.api.exec_create.assert_not_called()

    async def test_input_writes_to_terminal_socket(self):
        session = DockerTerminalSession(
            user_id=1,
            workspace_id=1,
            exec_id="exec-123",
            socket=self.socket,
        )
        self.manager.sessions["session-3"] = session

        await self.manager.input("session-3", "echo ADRI\n")

        self.socket.sendall.assert_called_once_with(b"echo ADRI\n")

    async def test_resize_uses_bounded_dimensions(self):
        session = DockerTerminalSession(
            user_id=1,
            workspace_id=1,
            exec_id="exec-123",
            socket=self.socket,
        )
        self.manager.sessions["session-4"] = session

        await self.manager.resize("session-4", 200, 500)

        self.docker_manager.client.api.exec_resize.assert_called_once_with(
            "exec-123",
            height=100,
            width=300,
        )

    async def test_close_preserves_container_and_volume(self):
        session = DockerTerminalSession(
            user_id=1,
            workspace_id=1,
            exec_id="exec-123",
            socket=self.socket,
            reader_task=asyncio.create_task(asyncio.sleep(0)),
        )
        self.manager.sessions["session-5"] = session

        await self.manager.close("session-5")

        self.socket.close.assert_called_once()
        self.assertNotIn("session-5", self.manager.sessions)
        self.docker_manager.stop.assert_not_called()
        self.docker_manager.client.containers.remove.assert_not_called()
        self.docker_manager.client.volumes.get.return_value.remove.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
