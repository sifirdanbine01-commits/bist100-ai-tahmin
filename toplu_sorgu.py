"""
TOPLU_SORGU.PY
================
Toplu tarama gibi eşiği geçen hisseleri bulur (açık pozisyondakileri
ATLAYARAK), R/R oranı en az 1:1.5 olanları filtreler, her biri için
sorgu.py'deki TAM detaylı analizi çalıştırıp AYRI AYRI Telegram mesajı
olarak gönderir. Yeni sinyal bulunan her hisse için pozisyon açar.
"""

import os
import time
import pandas as pd

from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI
from telegram_bildirim import telegram_mesaj_gonder
from sorgu import sorgula
from pozisyonlar import acik_semboller, pozisyon_ac, pozisyonlari_kontrol_et

ESIK = float(os.environ.get("TARAMA_ESIK", "0.55"))
MAX_HISSE = int(os.environ.get("MAX_HISSE", "200"))
MIN_RR = float(os.environ.get("MIN_RR", "1.5"))


def adaylari_bul(guncel_veri, modeller):
    kapali_semboller = acik_semboller()

    adaylar = []
    rr_elenen_sayisi = 0

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

            if olasilik < ESIK:
                continue

            guncel_fiyat = float(son['Close'])
            getiri_yuzde = abs(float(modeller['genel_regresyon'].predict(X)[0]))
            hedef = guncel_fiyat * (1 + getiri_yuzde / 100)
            atr = float(son.get('atr', guncel_fiyat * 0.02))
            stop = guncel_fiyat - atr

            hedef_mesafe = hedef - guncel_fiyat
            stop_mesafe = guncel_fiyat - stop
            rr = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0

            if rr < MIN_RR:
                rr_elenen_sayisi += 1
                continue

            adaylar.append({
                'sembol': sembol,
                'olasilik': olasilik,
                'fiyat': guncel_fiyat,
                'hedef': hedef,
                'stop': stop,
                'rr': rr,
                'tarih': son['tarih'],
            })
        except Exception as e:
            print(f"  ⚠️ {sembol} ön tarama hatası: {e}")
            continue

    adaylar.sort(key=lambda x: x['olasilik'], reverse=True)
    print(f"R/R < {MIN_RR} olduğu için elenen: {rr_elenen_sayisi}")
    return adaylar[:MAX_HISSE], rr_elenen_sayisi


if __name__ == "__main__":
    durum = durumu_oku()
    if durum is None:
        mesaj = "⚠️ Henüz hiç model eğitilmedi."
        telegram_mesaj_gonder(mesaj)
        print(mesaj)
        exit(0)

    if not os.path.exists('guncel_veri.parquet'):
        mesaj = "⚠️ guncel_veri.parquet bulunamadı."
        telegram_mesaj_gonder(mesaj)
        print(mesaj)
        exit(0)

    guncel_veri = pd.read_parquet('guncel_veri.parquet')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    kapanan_mesajlari = pozisyonlari_kontrol_et(guncel_veri)
    if kapanan_mesajlari:
        telegram_mesaj_gonder("📋 <b>Kapanan Pozisyonlar</b>\n\n" + "\n\n".join(kapanan_mesajlari))
        print("Kapanan pozisyonlar bildirildi.")

    modeller = modelleri_yukle()
    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        mesaj = "⚠️ Model bulunamadı."
        telegram_mesaj_gonder(mesaj)
        print(mesaj)
        exit(0)

    adaylar, rr_elenen = adaylari_bul(guncel_veri, modeller)

    if not adaylar:
        mesaj = (
            f"📊 <b>Toplu Sorgu</b>\n\n"
            f"Bugün eşiği (%{ESIK*100:.0f}) ve R/R şartını (1:{MIN_RR}) "
            f"birlikte geçen yeni hisse yok.\n"
            f"(R/R yetersiz olduğu için elenen: {rr_elenen})"
        )
        telegram_mesaj_gonder(mesaj)
        print(mesaj)
    else:
        baslik = (
            f"📊 <b>Toplu Sorgu Başlıyor</b>\n"
            f"{len(adaylar)} yeni hisse için detaylı analiz gönderiliyor...\n"
            f"(Eşik: %{ESIK*100:.0f}, Min R/R: 1:{MIN_RR}, "
            f"açık pozisyondakiler ve düşük R/R'liler atlandı: {rr_elenen})"
        )
        telegram_mesaj_gonder(baslik)
        print(baslik)

        for aday in adaylar:
            sembol = aday['sembol']
            try:
                mesaj = sorgula(sembol)
                telegram_mesaj_gonder(mesaj)

                pozisyon_ac(
                    sembol, aday['tarih'].date(), aday['fiyat'],
                    aday['hedef'], aday['stop'], aday['olasilik']
                )

                print(f"✅ {sembol} gönderildi ve pozisyon açıldı (%{aday['olasilik']*100:.0f}, R/R 1:{aday['rr']:.2f})")
                time.sleep(1.5)
            except Exception as e:
                print(f"⚠️ {sembol} için sorgu başarısız: {e}")
                continue

        print(f"\nTamamlandı: {len(adaylar)} hisse için detaylı analiz gönderildi, pozisyonlar açıldı.")