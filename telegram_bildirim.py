"""
TELEGRAM BİLDİRİM GÖNDERİCİ
============================
Walk-forward backtest sonucunu Telegram'a özet mesaj olarak gönderir.

Gerekli GitHub Secrets (repo ayarlarından eklenecek):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
"""

import os
import requests
import pandas as pd


def telegram_mesaj_gonder(mesaj):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID bulunamadı, "
              "mesaj gönderilemedi. (GitHub Secrets kontrol edilmeli)")
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


def sonuc_ozetini_olustur(sonuc_csv_yolu, cekilemeyenler=None):
    df = pd.read_csv(sonuc_csv_yolu)
    if df.empty:
        return "📊 BIST100 Walk-Forward Backtest\n\n⚠️ Yeterli veri birikmediği için hiçbir ay test edilemedi."

    ort_dogruluk = df['dogruluk'].mean() * 100
    son_3_ay = df.tail(3)

    mesaj = (
        f"📊 <b>BIST100 Walk-Forward Backtest Sonucu</b>\n\n"
        f"Test edilen ay sayısı: {len(df)}\n"
        f"Ortalama doğruluk: %{ort_dogruluk:.1f}\n\n"
        f"Son 3 ay:\n"
    )
    for _, row in son_3_ay.iterrows():
        mesaj += f"  {row['ay']}: %{row['dogruluk']*100:.0f} doğruluk ({int(row['test_ornegi'])} sinyal)\n"

    if cekilemeyenler:
        mesaj += f"\n⚠️ Çekilemeyen hisseler: {', '.join(cekilemeyenler[:10])}"

    mesaj += "\n\n⚠️ Bu bir yatırım tavsiyesi değildir."
    return mesaj


if __name__ == "__main__":
    ozet = sonuc_ozetini_olustur('/home/claude/bist_ai_tahmin/bist100_walk_forward_sonuc.csv')
    print(ozet)
    telegram_mesaj_gonder(ozet)
