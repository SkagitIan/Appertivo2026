"""Send every Appertivo system template to the configured review recipient."""
from app import app
from email_system.email_service import send_all_test_emails


with app.app_context():
    if not app.config["EMAIL_TEST_ENABLED"]:
        raise SystemExit("Email test sending is disabled. Set EMAIL_TEST_ENABLED=1.")
    recipient = app.config["EMAIL_TEST_RECIPIENT"]
    results = send_all_test_emails(recipient)
    for template_name, result in results.items():
        print(f"{template_name}: {'sent' if result['success'] else result['error']}")
    if not all(result["success"] for result in results.values()):
        raise SystemExit(1)
