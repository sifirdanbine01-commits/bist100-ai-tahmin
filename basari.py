"""
/basari KOMUTU
================
sorgu_gecmisi.csv'yi okuyup genel ve mod bazlı başarı oranını gösterir.
"""

import pandas as pd
import os

from telegram_bildirim import telegram_mesaj_gonder

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'


def basari_raporu_olustur():
    if not os.path.exists(SORGU_GECMISI_DOSYASI):
        return "⚠️ Henüz hiç sorgu yapılmadı."

    df = pd.read_csv(SORGU_GECMISI_DOSYASI)
    degerlendirilen = df[df['gercek_sonuc'].notna()].copy()

    if degerlendirilen.empty:
        return (f"📊 Toplam {len(df)} sorgu yapıldı ama henüz hiçbiri "
                f"sonuçlanmadı (yeterli gün geçmemiş). /ilerlet ile "
                f"zamanı ilerlettikçe sonuçlar açığa çıkacak.")

    degerlendirilen['dogru_mu'] = (
        ((degerlendirilen['tahmin_basari_olasiligi'] >= 0.5) & (degerlendirilen['gercek_sonuc'] == 1)) |
        ((degerlendirilen['tahmin_basari_olasiligi'] < 0.5) & (degerlendirilen['gercek_sonuc'] == 0))
    )

    genel_dogruluk = degerlendirilen['dogru_mu'].mean() * 100

    mesaj = (
        f"📊 <b>Başarı Takibi</b>\n\n"
        f"Toplam sonuçlanan sorgu: {len(degerlendirilen)}\n"
        f"Genel doğruluk: %{genel_dogruluk:.1f}\n\n"
    )

    for mod in ['yapisal', 'genel']:
        alt = degerlendirilen[degerlendirilen['mod'] == mod]
        if len(alt) > 0:
            oran = alt['dogru_mu'].mean() * 100
            mod_adi = "Yapısal Sinyal Modu" if mod == 'yapisal' else "Genel Hareket Modu"
            mesaj += f"{mod_adi}: %{oran:.1f} ({len(alt)} sorgu)\n"

    mesaj += "\nSon 5 sorgu:\n"
    for _, satir in degerlendirilen.tail(5).iterrows():
        durum = "✅" if satir['dogru_mu'] else "❌"
        mesaj += f"  {satir['sembol']} ({satir['tarih'][:7]}): {durum}\n"

    bekleyen = len(df) - len(degerlendirilen)
    if bekleyen > 0:
        mesaj += f"\n⏳ {bekleyen} sorgu henüz sonuçlanmadı."

    return mesaj


if __name__ == "__main__":
    mesaj = basari_raporu_olustur()
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
