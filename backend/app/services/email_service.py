
import json
import os
import urllib.error
import urllib.request
from html import escape


RESEND_API_URL = "https://api.resend.com/emails"


def send_verification_email(to_email: str, token: str) -> None:
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "https://devopsadi.com",
    ).rstrip("/")

    from_email = os.getenv(
        "RESEND_FROM_EMAIL",
        "ADRI AI <noreply@devopsadi.com>",
    )

    verification_url = f"{frontend_url}/api/auth/verify-email?token={token}"

    safe_url = escape(verification_url, quote=True)

    html_content = f"""
    <!DOCTYPE html>
    <html>
      <body style="font-family: Arial, sans-serif; color: #222;">
        <h2>Welcome to ADRI AI!</h2>

        <p>Thank you for creating your account.</p>

        <p>Please verify your email address by clicking below:</p>

        <p>
          <a href="{safe_url}"
             style="background:#2563eb;color:white;padding:12px 24px;
                    text-decoration:none;border-radius:6px;
                    display:inline-block;">
            Verify my email
          </a>
        </p>

        <p>This link expires in 24 hours and can only be used once.</p>

        <p>If you did not create this account, you can ignore this email.</p>

        <p>ADRI AI Team</p>
      </body>
    </html>
    """

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": "Verify your ADRI AI email address",
        "html": html_content,
    }

    request = urllib.request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status not in (200, 201):
                raise RuntimeError(
                    f"Resend returned HTTP {response.status}"
                )

    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Resend email delivery failed: HTTP {error.code}"
        ) from None

    except urllib.error.URLError:
        raise RuntimeError("Could not connect to Resend") from None
