import unittest
from unittest.mock import AsyncMock, MagicMock

from backend_connection import handle_workspace_request


class TestWorkspaceProtocol(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.docker_manager = MagicMock()
        self.send_message = AsyncMock()

    async def test_start_request(self):
        self.docker_manager.start.return_value = {
            "container_id": "abc123",
            "status": "running",
        }

        await handle_workspace_request(
            {
                "request_id": "req-001",
                "operation": "start",
                "user_id": 1,
                "workspace_id": 1,
            },
            self.docker_manager,
            self.send_message,
        )

        response = self.send_message.await_args.args[0]
        self.assertEqual(response["type"], "workspace.response")
        self.assertEqual(response["request_id"], "req-001")
        self.assertTrue(response["success"])
        self.assertEqual(response["result"]["status"], "running")

    async def test_execute_request(self):
        self.docker_manager.execute.return_value = {
            "exit_code": 0,
            "stdout": "ADRI_AI_TEST",
            "stderr": "",
        }

        await handle_workspace_request(
            {
                "request_id": "req-002",
                "operation": "execute",
                "user_id": 1,
                "workspace_id": 1,
                "command": "echo ADRI_AI_TEST",
            },
            self.docker_manager,
            self.send_message,
        )

        response = self.send_message.await_args.args[0]
        self.assertTrue(response["success"])
        self.assertEqual(response["result"]["exit_code"], 0)
        self.docker_manager.execute.assert_called_once_with(
            1, 1, "echo ADRI_AI_TEST"
        )

    async def test_rejects_invalid_user_id(self):
        await handle_workspace_request(
            {
                "request_id": "req-003",
                "operation": "status",
                "user_id": True,
                "workspace_id": 1,
            },
            self.docker_manager,
            self.send_message,
        )

        response = self.send_message.await_args.args[0]
        self.assertFalse(response["success"])
        self.assertIn("Invalid user ID", response["error"])
        self.docker_manager.status.assert_not_called()

    async def test_rejects_unsupported_operation(self):
        await handle_workspace_request(
            {
                "request_id": "req-004",
                "operation": "delete",
                "user_id": 1,
                "workspace_id": 1,
            },
            self.docker_manager,
            self.send_message,
        )

        response = self.send_message.await_args.args[0]
        self.assertFalse(response["success"])
        self.assertIn("Unsupported", response["error"])

    async def test_returns_docker_errors(self):
        self.docker_manager.status.side_effect = RuntimeError(
            "Workspace container not found"
        )

        await handle_workspace_request(
            {
                "request_id": "req-005",
                "operation": "status",
                "user_id": 1,
                "workspace_id": 1,
            },
            self.docker_manager,
            self.send_message,
        )

        response = self.send_message.await_args.args[0]
        self.assertFalse(response["success"])
        self.assertIn("container not found", response["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
