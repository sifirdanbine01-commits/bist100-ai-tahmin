"""
/basari KOMUTU
================
Genel tahmin bazlı başarı oranını gösterir. Veto satırları hariç.
"""

import pandas as pd
import os

from telegram_bildirim import telegram_mesaj_gonder

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'


def basari_raporu_olustur():
    if not os.path.exists(SORGU_GECMISI_DOSYASI):
        return "⚠️ Henüz hiç sorgu yapılmadı."

    df = pd.read_csv(SORGU_GECMISI_DOSYASI)

    veto_sayisi = len(df[df.get('veto') == 1])
    trade_onerileri = df[df.get('veto') != 1].copy()

    degerlendirilen = trade_onerileri[
        trade_onerileri['gercek_sonuc'].notna() & (trade_onerileri['gercek_sonuc'] != -1)
    ].copy()

    if degerlendirilen.empty:
        mesaj = (f"📊 Toplam {len(trade_onerileri)} LONG önerisi yapıldı ama henüz "
                  f"hiçbiri sonuçlanmadı (yeterli gün geçmemiş).")
        if veto_sayisi:
            mesaj += f"\n\nAyrıca {veto_sayisi} kez 'long riskli' uyarısı verildi."
        return mesaj

    degerlendirilen['dogru_mu'] = (
        ((degerlendirilen['genel_olasilik'] >= 0.5) & (degerlendirilen['gercek_sonuc'] == 1)) |
        ((degerlendirilen['genel_olasilik'] < 0.5) & (degerlendirilen['gercek_sonuc'] == 0))
    )

    genel_dogruluk = degerlendirilen['dogru_mu'].mean() * 100
    fib_mevcut = degerlendirilen['hedef1_fiyat'].notna() if 'hedef1_fiyat' in degerlendirilen.columns else pd.Series([False] * len(degerlendirilen))

    mesaj = (
        f"📊 <b>Başarı Takibi</b>\n\n"
        f"Toplam sonuçlanan öneri: {len(degerlendirilen)}\n"
        f"Genel doğruluk: %{genel_dogruluk:.1f}\n"
        f"Fibonacci kademeli hedefli öneri sayısı: {fib_mevcut.sum()}\n\n"
    )

    if fib_mevcut.sum() > 0:
        fib_dogruluk = degerlendirilen[fib_mevcut]['dogru_mu'].mean() * 100
        genel_sade_dogruluk = degerlendirilen[~fib_mevcut]['dogru_mu'].mean() * 100 if (~fib_mevcut).sum() > 0 else None
        mesaj += f"Fibonacci verisi olan önerilerde doğruluk: %{fib_dogruluk:.1f}\n"
        if genel_sade_dogruluk is not None:
            mesaj += f"Sadece genel veriyle önerilerde doğruluk: %{genel_sade_dogruluk:.1f}\n"

    mesaj += "\nSon 5 öneri:\n"
    for _, satir in degerlendirilen.tail(5).iterrows():
        durum = "✅" if satir['dogru_mu'] else "❌"
        mesaj += f"  {satir['sembol']} ({str(satir['tarih'])[:7]}): {durum}\n"

    bekleyen = len(trade_onerileri) - len(degerlendirilen)
    if bekleyen > 0:
        mesaj += f"\n⏳ {bekleyen} öneri henüz sonuçlanmadı."
    if veto_sayisi:
        mesaj += f"\n\n(Ayrıca {veto_sayisi} kez 'long riskli' uyarısı verildi.)"

    return mesaj


if __name__ == "__main__":
    mesaj = basari_raporu_olustur()
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
