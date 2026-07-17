"""
/basari KOMUTU (v2)
======================
sorgu_gecmisi.csv'yi okuyup Hedef1 bazlı başarı oranını gösterir.
Risk uyarısı satırları (mod=risk_uyarisi_asagi) sayıma dahil edilmez.
"""

import pandas as pd
import os

from telegram_bildirim import telegram_mesaj_gonder

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'


def basari_raporu_olustur():
    if not os.path.exists(SORGU_GECMISI_DOSYASI):
        return "⚠️ Henüz hiç sorgu yapılmadı."

    df = pd.read_csv(SORGU_GECMISI_DOSYASI)

    risk_uyarisi_sayisi = len(df[df.get('mod') == 'risk_uyarisi_asagi'])
    trade_onerileri = df[df.get('mod') != 'risk_uyarisi_asagi'].copy()

    degerlendirilen = trade_onerileri[
        trade_onerileri['gercek_sonuc'].notna() & (trade_onerileri['gercek_sonuc'] != -1)
    ].copy()

    if degerlendirilen.empty:
        mesaj = (f"📊 Toplam {len(trade_onerileri)} LONG önerisi yapıldı ama henüz "
                  f"hiçbiri sonuçlanmadı (yeterli gün geçmemiş).")
        if risk_uyarisi_sayisi:
            mesaj += f"\n\nAyrıca {risk_uyarisi_sayisi} kez 'long riskli' uyarısı verildi."
        return mesaj

    degerlendirilen['dogru_mu'] = (
        ((degerlendirilen['hedef1_olasilik'] >= 0.5) & (degerlendirilen['gercek_sonuc'] == 1)) |
        ((degerlendirilen['hedef1_olasilik'] < 0.5) & (degerlendirilen['gercek_sonuc'] == 0))
    )

    genel_dogruluk = degerlendirilen['dogru_mu'].mean() * 100

    mesaj = (
        f"📊 <b>Başarı Takibi (Hedef 1 Bazlı)</b>\n\n"
        f"Toplam sonuçlanan öneri: {len(degerlendirilen)}\n"
        f"Genel doğruluk: %{genel_dogruluk:.1f}\n\n"
    )

    for mod in ['yapisal', 'cizgi', 'genel']:
        alt = degerlendirilen[degerlendirilen['mod'] == mod]
        if len(alt) > 0:
            oran = alt['dogru_mu'].mean() * 100
            mod_adi = {'yapisal': 'Yapısal Sinyal Modu', 'cizgi': 'Trend Çizgisi Modu',
                       'genel': 'Genel Hareket Modu'}[mod]
            mesaj += f"{mod_adi}: %{oran:.1f} ({len(alt)} öneri)\n"

    mesaj += "\nSon 5 öneri:\n"
    for _, satir in degerlendirilen.tail(5).iterrows():
        durum = "✅" if satir['dogru_mu'] else "❌"
        mesaj += f"  {satir['sembol']} ({str(satir['tarih'])[:7]}, {satir['mod']}): {durum}\n"

    bekleyen = len(trade_onerileri) - len(degerlendirilen)
    if bekleyen > 0:
        mesaj += f"\n⏳ {bekleyen} öneri henüz sonuçlanmadı."
    if risk_uyarisi_sayisi:
        mesaj += f"\n\n(Ayrıca {risk_uyarisi_sayisi} kez 'long riskli' uyarısı verildi.)"

    return mesaj


if __name__ == "__main__":
    mesaj = basari_raporu_olustur()
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
