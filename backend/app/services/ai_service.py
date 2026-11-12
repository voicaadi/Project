
import os
import time
from pathlib import Path
from functools import lru_cache

from google import genai
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

MODEL = "gemini-3.5-flash"


@lru_cache(maxsize=1)
def get_gemini_client():
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured.")

    return genai.Client(
        api_key=api_key,
        http_options={"timeout": 60000}
    )


def ask_gemini(message: str) -> str:
    client = get_gemini_client()

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=f"""
You are Adrian AI Assistant, a DevOps specialist.

Help users with Linux, Docker, Kubernetes, AWS,
Terraform, CI/CD, networking and troubleshooting.

Rules:
- Give practical, step-by-step explanations.
- Provide safe commands.
- Explain what commands do.
- Never claim you executed a command unless you actually did.
- Never assume you have access to a user's terminal.

User question:
{message}
"""
            )

            return response.text or "No response generated."

        except Exception:
            if attempt == 2:
                raise

            time.sleep(1)
