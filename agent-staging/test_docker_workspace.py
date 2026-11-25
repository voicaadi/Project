import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from docker_workspace import DockerWorkspaceManager


class TestDockerWorkspaceManager(unittest.TestCase):
    def setUp(self):
        self.container = MagicMock()
        self.container.short_id = "test12345678"
        self.container.name = "devops-staging-user-1-workspace-1"
        self.container.status = "exited"
        self.container.labels = {
            "managed_by": "devops-ai-staging",
            "user_id": "1",
            "workspace_id": "1",
        }

        self.client = MagicMock()
        self.client.containers.get.return_value = self.container

        self.patcher = patch(
            "docker_workspace.docker.from_env",
            return_value=self.client,
        )
        self.patcher.start()
        self.manager = DockerWorkspaceManager()

    def tearDown(self):
        self.manager.close()
        self.patcher.stop()

    def test_status_returns_existing_container(self):
        result = self.manager.status(1, 1)

        self.assertEqual(result["status"], "exited")
        self.assertEqual(result["container_id"], "test12345678")

    def test_start_reuses_existing_container(self):
        def simulate_start():
            self.container.status = "running"

        self.container.start.side_effect = simulate_start

        result = self.manager.start(1, 1)

        self.container.start.assert_called_once()
        self.assertEqual(result["status"], "running")

    def test_stop_stops_running_container(self):
        self.container.status = "running"

        result = self.manager.stop(1, 1)

        self.container.stop.assert_called_once_with(timeout=10)
        self.assertEqual(result["status"], "stopped")

    def test_rejects_wrong_owner(self):
        with self.assertRaises(PermissionError):
            self.manager.status(2, 1)

    def test_execute_returns_command_output(self):
        self.container.status = "running"
        self.container.exec_run.return_value = SimpleNamespace(
            exit_code=0,
            output=(b"ADRI_AI_TEST\n", None),
        )

        result = self.manager.execute(1, 1, "echo ADRI_AI_TEST")

        self.assertEqual(result["exit_code"], 0)
        self.assertIn("ADRI_AI_TEST", result["stdout"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
