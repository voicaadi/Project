
import json
import os
import urllib.error
import urllib.request


RESEND_API_URL = "https://api.resend.com/emails"


def send_verification_email(to_email: str, code: str) -> None:
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    from_email = os.getenv(
        "RESEND_FROM_EMAIL",
        "ADRI AI <noreply@devopsadi.com>",
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
      <body style="font-family: Arial, sans-serif; color: #302642;">
        <div style="max-width: 500px; margin: 30px auto; padding: 30px;
                    background: #fff4dc; border-radius: 12px;
                    text-align: center;">
          <h2>Welcome to ADRI AI!</h2>
          <p>Use this verification code to activate your account:</p>
          <div style="font-size: 36px; font-weight: bold;
                      letter-spacing: 10px; padding: 20px;
                      background: white; border-radius: 10px;">
            {code}
          </div>
          <p>This code expires in 24 hours and can only be used once.</p>
          <p>If you did not create this account, ignore this email.</p>
          <p>ADRI AI Team</p>
        </div>
      </body>
    </html>
    """

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": "Your ADRI AI verification code",
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
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Resend email delivery failed: HTTP {error.code} - {details}"
        ) from None
    except urllib.error.URLError:
        raise RuntimeError("Could not connect to Resend") from None
