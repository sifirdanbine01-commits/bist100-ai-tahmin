"""
TOPLU_TARAMA.PY
================
Her gün otomatik olarak TÜM hisseleri tarar, model skorunun
belirli bir eşiği geçtiği (ve trend_yonu veto etmediği) hisseleri
tek bir özet Telegram mesajında listeler.
"""

import os
import pandas as pd

from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI
from telegram_bildirim import telegram_mesaj_gonder

ESIK = float(os.environ.get("TARAMA_ESIK", "0.55"))


def toplu_tara():
    durum = durumu_oku()
    if durum is None:
        return "⚠️ Henüz hiç model eğitilmedi. Önce 'Egit veya Ilerlet' çalıştırılmalı."
    if not os.path.exists('guncel_veri.parquet'):
        return "⚠️ guncel_veri.parquet bulunamadı."

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi'])
    guncel_veri = pd.read_parquet('guncel_veri.parquet')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    modeller = modelleri_yukle()
    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        return "⚠️ Model bulunamadı."

    sonuclar = []
    hata_sayisi = 0

    for sembol, grup in guncel_veri.groupby('sembol'):
        try:
            son = grup.sort_values('tarih').iloc[-1]

            trend_yonu = son.get('trend_yonu', 0)
            if pd.notna(trend_yonu) and int(trend_yonu) == -1:
                continue

            eksik = [k for k in OZELLIK_KOLONLARI if pd.isna(son.get(k))]
            if eksik:
                continue

            X = pd.DataFrame([son[OZELLIK_KOLONLARI].to_dict()]).astype(float)
            olasilik = float(modeller['genel_siniflandirma'].predict_proba(X)[0][1])

            if olasilik < ESIK:
                continue

            guncel_fiyat = float(son['Close'])
            getiri_yuzde = abs(float(modeller['genel_regresyon'].predict(X)[0]))
            hedef = guncel_fiyat * (1 + getiri_yuzde / 100)
            atr = float(son.get('atr', guncel_fiyat * 0.02))
            stop = guncel_fiyat - atr
            rr = (hedef - guncel_fiyat) / (guncel_fiyat - stop) if guncel_fiyat > stop else 0

            sonuclar.append({
                'sembol': sembol,
                'olasilik': olasilik,
                'fiyat': guncel_fiyat,
                'hedef': hedef,
                'stop': stop,
                'rr': rr,
            })
        except Exception as e:
            hata_sayisi += 1
            print(f"  ⚠️ {sembol} taranamadı: {e}")
            continue

    sonuclar.sort(key=lambda x: x['olasilik'], reverse=True)

    if not sonuclar:
        mesaj = (
            f"📊 <b>Toplu Tarama</b> ({egitim_tarihi.date()} durumu)\n\n"
            f"Bugün eşiği (%{ESIK*100:.0f}) geçen hisse yok."
        )
    else:
        mesaj = (
            f"📊 <b>Toplu Tarama Sonuçları</b> ({egitim_tarihi.date()} durumu)\n"
            f"Eşik: %{ESIK*100:.0f} | Bulunan: {len(sonuclar)}\n\n"
        )
        for s in sonuclar:
            mesaj += (
                f"🟢 <b>{s['sembol']}</b> — %{s['olasilik']*100:.0f}\n"
                f"   {s['fiyat']:.2f} → 🎯{s['hedef']:.2f} / 🛑{s['stop']:.2f} "
                f"(R/R 1:{s['rr']:.2f})\n"
            )

    if hata_sayisi:
        mesaj += f"\n⚠️ {hata_sayisi} hisse taranamadı (veri eksikliği)."

    mesaj += "\n\n⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
    return mesaj


if __name__ == "__main__":
    mesaj = toplu_tara()
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
