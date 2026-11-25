import asyncio
import sys

from backend_terminal import BackendTerminalManager


async def wait_until(condition, timeout=6):
    deadline = asyncio.get_running_loop().time() + timeout

    while asyncio.get_running_loop().time() < deadline:
        if condition():
            return True
        await asyncio.sleep(0.1)

    return False


async def main():
    messages = []

    async def capture_message(message):
        messages.append(message)

    manager = BackendTerminalManager(capture_message)
    session_id = "local-test-001"

    try:
        await manager.open(session_id)

        assert session_id in manager.sessions

        await manager.input(
            session_id,
            "echo ADRI_AI_TERMINAL_TEST\n",
        )

        output_received = await wait_until(
            lambda: any(
                message.get("type") == "terminal.output"
                and "ADRI_AI_TERMINAL_TEST" in message.get("data", "")
                for message in messages
            )
        )

        if not output_received:
            print("FAIL: Expected terminal output was not received.")
            sys.exit(1)

        print("PASS: Terminal command executed successfully.")

        await manager.input(session_id, "exit\n")

        session_removed = await wait_until(
            lambda: session_id not in manager.sessions
        )

        if not session_removed:
            print("FAIL: Naturally exited session was not removed.")
            sys.exit(1)

        print("PASS: Naturally exited terminal session was removed.")

    finally:
        await manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())
