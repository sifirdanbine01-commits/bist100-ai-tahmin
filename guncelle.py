"""
GÜNCELLE.PY — Sistemin Kalbi
=============================
İKİ MODDA ÇALIŞIR: Manuel (HEDEF_TARIH verilir) veya Otomatik 
(boşsa, guard mekanizmasıyla - sadece bugüne yakınsa çalışır).
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta

from veri_cek import tum_bist100_verisini_cek
from gunluk_ozellik_seti import tum_hisseler_icin_gunluk_ozellik_seti
from model_egit import modelleri_egit, modelleri_kaydet
from durum import durumu_oku, durumu_kaydet
from telegram_bildirim import telegram_mesaj_gonder
from sonuc_ac import onceki_sorgulari_degerlendir

OTOMATIK_ESIK_GUN = 10


def hedef_tarihi_belirle(tum_veri_son_tarih):
    manuel_tarih = os.environ.get("HEDEF_TARIH", "").strip()

    if manuel_tarih:
        print(f"📌 MANUEL MOD: Hedef tarih = {manuel_tarih}")
        return pd.Timestamp(manuel_tarih), True

    durum = durumu_oku()
    bugun = pd.Timestamp(datetime.now().date())

    if durum is None:
        print("⏸️ Henüz hiç /egit yapılmamış. Otomatik mod bekliyor, çıkılıyor.")
        sys.exit(0)

    son_egitim_tarihi = pd.Timestamp(durum['egitim_tarihi'])
    fark_gun = (bugun - son_egitim_tarihi).days

    if fark_gun > OTOMATIK_ESIK_GUN:
        print(f"⏸️ Manuel ilerletme sürecindesin (son eğitim: "
              f"{son_egitim_tarihi.date()}, bugüne {fark_gun} gün var). "
              f"Otomatik güncelleme BEKLEMEDE, çıkılıyor.")
        sys.exit(0)

    print(f"🤖 OTOMATİK MOD: Bugüne yakınsın, kendi kendime dünü ekleyip öğreniyorum.")
    return min(tum_veri_son_tarih, bugun - timedelta(days=1)), False


if __name__ == "__main__":
    print("=" * 60)
    print("ADIM 1: BIST verisi çekiliyor...")
    print("=" * 60)
    veri_sozlugu, cekilemeyenler = tum_bist100_verisini_cek()

    print("\n" + "=" * 60)
    print("ADIM 2: Günlük özellik seti oluşturuluyor")
    print("=" * 60)
    tum_ozellik_df = tum_hisseler_icin_gunluk_ozellik_seti(veri_sozlugu)
    tum_veri_son_tarih = tum_ozellik_df['tarih'].max()
    print(f"Toplam satır: {len(tum_ozellik_df)} | Son veri tarihi: {tum_veri_son_tarih.date()}")

    hedef_tarih, manuel_mi = hedef_tarihi_belirle(tum_veri_son_tarih)
    onceki_durum = durumu_oku()

    print("\n" + "=" * 60)
    print(f"ADIM 3: Model, {hedef_tarih.date()} tarihine kadarki veriyle eğitiliyor")
    print("=" * 60)
    egitim_kismi = tum_ozellik_df[tum_ozellik_df['tarih'] <= hedef_tarih]
    print(f"Eğitim örneği sayısı: {len(egitim_kismi)}")

    if len(egitim_kismi) < 200:
        print("⚠️ Yeterli veri yok, en az 200 örnek gerekiyor. Çıkılıyor.")
        sys.exit(0)

    modeller = modelleri_egit(egitim_kismi, hedef_tarih)
    modelleri_kaydet(modeller)

    tum_ozellik_df[tum_ozellik_df['tarih'] <= hedef_tarih].to_csv('guncel_veri.csv', index=False)
    yeni_durum = durumu_kaydet(hedef_tarih.date(), len(egitim_kismi))

    mesaj = (
        f"✅ <b>Model Güncellendi</b>\n\n"
        f"Mod: {'Manuel' if manuel_mi else 'Otomatik (günlük)'}\n"
        f"Eğitim Tarihi: {hedef_tarih.date()}\n"
        f"Eğitim Örneği: {len(egitim_kismi)}\n"
    )

    try:
        from gunluk_ozellik_seti import OZELLIK_KOLONLARI
        if modeller.get('genel_siniflandirma') is not None:
            onem = pd.Series(
                modeller['genel_siniflandirma'].feature_importances_,
                index=OZELLIK_KOLONLARI
            ).sort_values(ascending=False)
            onem_yuzde = (onem / onem.sum() * 100).round(1)
            mesaj += "\n📊 <b>En Etkili 5 Özellik</b> (genel model):\n"
            for ozellik, yuzde in onem_yuzde.head(5).items():
                mesaj += f"  {ozellik}: %{yuzde}\n"
    except Exception as e:
        print(f"⚠️ Feature importance hesaplanamadı: {e}")

    if onceki_durum is not None:
        aciklama = onceki_sorgulari_degerlendir(tum_ozellik_df, hedef_tarih)
        if aciklama:
            mesaj += f"\n📊 <b>Önceki Sorgu Sonuçları Açığa Çıktı:</b>\n{aciklama}"

    print(mesaj)
    telegram_mesaj_gonder(mesaj)
