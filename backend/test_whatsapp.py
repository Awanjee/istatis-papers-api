import requests
import os
from dotenv import load_dotenv

load_dotenv()

PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")


def send_test_message(to_number: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": "iStatis WhatsApp integration test. Working."},
    }
    response = requests.post(url, headers=headers, json=payload)
    print(response.status_code)
    print(response.json())


if __name__ == "__main__":
    send_test_message("61432036325")  # your number in full international format
