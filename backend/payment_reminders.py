import requests
import os
import json
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PAYMENTS_FILE = "payments.json"


def load_payments():
    with open(PAYMENTS_FILE) as f:
        return json.load(f)


def save_payments(payments):
    with open(PAYMENTS_FILE, "w") as f:
        json.dump(payments, f, indent=2)


def send_template(to, template_name, params):
    url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }
            ],
        },
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.status_code, response.json()


def days_overdue(due_date_str):
    due = date.fromisoformat(due_date_str)
    return (date.today() - due).days


def run_reminders():
    payments = load_payments()
    today = date.today().isoformat()

    for p in payments:
        overdue = days_overdue(p["due_date"])
        name = p["customer_name"]
        phone = p["phone"]
        amount = p["amount"]
        order = p["order_id"]
        reminded = p["reminded_at"]

        if overdue == 0 and "due" not in reminded:
            template = "arco_payment_due"
            stage = "due"
        elif overdue >= 7 and "7d" not in reminded:
            template = "arco_payment_overdue_7"
            stage = "7d"
        elif overdue >= 14 and "14d" not in reminded:
            template = "arco_payment_overdue_14"
            stage = "14d"
        else:
            continue

        status, resp = send_template(phone, template, [name, amount, order])
        if status == 200:
            p["reminded_at"].append(stage)
            print(f"Sent {stage} reminder to {name} ({phone})")
        else:
            print(f"Failed for {name}: {resp}")

    save_payments(payments)


if __name__ == "__main__":
    run_reminders()
