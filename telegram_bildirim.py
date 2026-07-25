"""
TELEGRAM BİLDİRİM GÖNDERİCİ
============================
"""

import os
import requests


def telegram_mesaj_gonder(mesaj):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID bulunamadı, "
              "mesaj gönderilemedi.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mesaj, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            print("✅ Telegram mesajı gönderildi.")
        else:
            print(f"⚠️ Telegram gönderim hatası: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram bağlantı hatası: {e}")
