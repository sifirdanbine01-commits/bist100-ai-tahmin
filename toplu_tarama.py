"""
TOPLU_TARAMA.PY
================
1) Önce açık pozisyonları günceller (hedef/stop'a ulaşan var mı kontrol eder)
2) Açık pozisyondaki hisseleri ATLAYARAK geri kalanları tarar
3) Yeni sinyal bulunan hisseler için pozisyon açar
"""

import os
import pandas as pd

from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI
from telegram_bildirim import telegram_mesaj_gonder
from pozisyonlar import pozisyonlari_kontrol_et, acik_semboller, pozisyon_ac

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

    kapanan_mesajlari = pozisyonlari_kontrol_et(guncel_veri)
    kapali_semboller = acik_semboller()

    modeller = modelleri_yukle()
    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        return "⚠️ Model bulunamadı."

    sonuclar = []
    hata_sayisi = 0
    atlanan_sayisi = 0

    for sembol, grup in guncel_veri.groupby('sembol'):
        if sembol in kapali_semboller:
            atlanan_sayisi += 1
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
            rr = (hedef - guncel_fiyat) / (guncel_fiyat - stop) if guncel_fiyat > stop else 0

            sonuclar.append({
                'sembol': sembol,
                'olasilik': olasilik,
                'fiyat': guncel_fiyat,
                'hedef': hedef,
                'stop': stop,
                'rr': rr,
                'tarih': son['tarih'],
            })
        except Exception as e:
            hata_sayisi += 1
            print(f"  ⚠️ {sembol} taranamadı: {e}")
            continue

    sonuclar.sort(key=lambda x: x['olasilik'], reverse=True)

    for s in sonuclar:
        pozisyon_ac(s['sembol'], s['tarih'].date(), s['fiyat'], s['hedef'], s['stop'], s['olasilik'])

    mesajlar = []

    if kapanan_mesajlari:
        mesajlar.append("📋 <b>Kapanan Pozisyonlar</b>\n\n" + "\n\n".join(kapanan_mesajlari))

    if not sonuclar:
        mesajlar.append(
            f"📊 <b>Toplu Tarama</b> ({egitim_tarihi.date()} durumu)\n\n"
            f"Bugün eşiği (%{ESIK*100:.0f}) geçen yeni hisse yok.\n"
            f"(Açık pozisyon nedeniyle atlanan: {atlanan_sayisi})"
        )
    else:
        mesaj = (
            f"📊 <b>Toplu Tarama — Yeni Sinyaller</b> ({egitim_tarihi.date()} durumu)\n"
            f"Eşik: %{ESIK*100:.0f} | Bulunan: {len(sonuclar)} | "
            f"Zaten pozisyonda (atlanan): {atlanan_sayisi}\n\n"
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
        mesajlar.append(mesaj)

    return "\n\n---\n\n".join(mesajlar)


if __name__ == "__main__":
    mesaj = toplu_tara()
    print(mesaj)
    for parca in mesaj.split("\n\n---\n\n"):
        telegram_mesaj_gonder(parca)
