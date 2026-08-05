"""
TOPLU_SORGU.PY
================
Toplu tarama gibi eşiği geçen hisseleri bulur (açık pozisyondakileri
ATLAYARAK), her biri için sorgu.py'deki TAM detaylı analizi çalıştırıp
AYRI AYRI Telegram mesajı olarak gönderir.
"""

import os
import time
import pandas as pd

from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI
from telegram_bildirim import telegram_mesaj_gonder
from sorgu import sorgula
from pozisyonlar import acik_semboller

ESIK = float(os.environ.get("TARAMA_ESIK", "0.55"))
MAX_HISSE = int(os.environ.get("MAX_HISSE", "15"))


def adaylari_bul():
    durum = durumu_oku()
    if durum is None:
        return [], "⚠️ Henüz hiç model eğitilmedi."
    if not os.path.exists('guncel_veri.parquet'):
        return [], "⚠️ guncel_veri.parquet bulunamadı."

    guncel_veri = pd.read_parquet('guncel_veri.parquet')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    kapali_semboller = acik_semboller()

    modeller = modelleri_yukle()
    if modeller.get('genel_siniflandirma') is None:
        return [], "⚠️ Model bulunamadı."

    adaylar = []
    for sembol, grup in guncel_veri.groupby('sembol'):
        if sembol in kapali_semboller:
            continue
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

            if olasilik >= ESIK:
                adaylar.append((sembol, olasilik))
        except Exception as e:
            print(f"  ⚠️ {sembol} ön tarama hatası: {e}")
            continue

    adaylar.sort(key=lambda x: x[1], reverse=True)
    return adaylar[:MAX_HISSE], None


if __name__ == "__main__":
    adaylar, hata = adaylari_bul()

    if hata:
        telegram_mesaj_gonder(hata)
        print(hata)
    elif not adaylar:
        mesaj = f"📊 <b>Toplu Sorgu</b>\n\nBugün eşiği (%{ESIK*100:.0f}) geçen yeni hisse yok."
        telegram_mesaj_gonder(mesaj)
        print(mesaj)
    else:
        baslik = (
            f"📊 <b>Toplu Sorgu Başlıyor</b>\n"
            f"{len(adaylar)} yeni hisse için detaylı analiz gönderiliyor...\n"
            f"(Eşik: %{ESIK*100:.0f}, açık pozisyondakiler atlandı)"
        )
        telegram_mesaj_gonder(baslik)
        print(baslik)

        for sembol, olasilik in adaylar:
            try:
                mesaj = sorgula(sembol)
                telegram_mesaj_gonder(mesaj)
                print(f"✅ {sembol} gönderildi (%{olasilik*100:.0f})")
                time.sleep(1.5)
            except Exception as e:
                print(f"⚠️ {sembol} için sorgu başarısız: {e}")
                continue

        print(f"\nTamamlandı: {len(adaylar)} hisse için detaylı analiz gönderildi.")
