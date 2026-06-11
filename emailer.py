import os
import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "chess@yourdomain.com")
APP_URL = os.environ.get("APP_URL", "http://localhost:5858")


def send_feedback_email(to_email: str, username: str, feedback: str, games_count: int):
    """Send a chess coaching email via Resend."""
    # Convert markdown-ish feedback to basic HTML paragraphs
    html_feedback = ""
    for line in feedback.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            html_feedback += f"<h3 style='color:#2c5f2e;margin-top:20px'>{stripped[3:]}</h3>"
        elif stripped.startswith("**") and stripped.endswith("**"):
            html_feedback += f"<strong>{stripped[2:-2]}</strong><br>"
        elif stripped:
            html_feedback += f"<p style='margin:6px 0'>{stripped}</p>"

    unsubscribe_url = f"{APP_URL}/unsubscribe?email={to_email}&username={username}"

    html = f"""
<div style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:24px;background:#fafaf7">
  <div style="border-left:4px solid #2c5f2e;padding-left:16px;margin-bottom:24px">
    <h2 style="margin:0;color:#1a1a1a">♟ Chess Teacher</h2>
    <p style="margin:4px 0 0;color:#666">Daily feedback for <strong>{username}</strong></p>
  </div>
  <p style="color:#444">Here's your coaching from your {games_count} most recent game{'s' if games_count > 1 else ''}:</p>
  <hr style="border:none;border-top:1px solid #e0e0d8;margin:16px 0">
  {html_feedback}
  <hr style="border:none;border-top:1px solid #e0e0d8;margin:24px 0">
  <p style="font-size:12px;color:#999">
    Chess Teacher · <a href="{unsubscribe_url}" style="color:#999">Unsubscribe</a>
  </p>
</div>
"""

    resend.Emails.send({
        "from": f"Chess Teacher <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"♟ Your chess feedback — {username}",
        "html": html,
    })
