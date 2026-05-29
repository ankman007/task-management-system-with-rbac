import time
from app.core.celery_app import celery_app

@celery_app.task(name="send_welcome_email_task")
def send_welcome_email(user_email: str):
    """
    Simulates sending a heavy welcome email.
    Because this runs in the background worker container, 
    the user doesn't experience this 5-second delay!
    """
    print(f"✉️ Starting email sequence for {user_email}...")
    time.sleep(5)  # Mimic slow network SMTP handshake
    print(f"✅ Email successfully sent to {user_email}!")
    return {"status": "sent", "recipient": user_email}