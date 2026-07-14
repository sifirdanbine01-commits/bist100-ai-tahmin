"""
GÜNCELLE.PY — Sistemin Kalbi
=============================
İKİ MODDA ÇALIŞIR:

1) MANUEL MOD (sen tarih verirsin):
   HEDEF_TARIH=2025-01-31 şeklinde bir ortam değişkeni verilirse,
   model TAM O TARİHE KADAR eğitilir. (/egit ve /ilerlet komutları
   bu modu kullanır)

2) OTOMATİK MOD (kimse tarih vermez, günlük cron tetikler):
   HEDEF_TARIH boşsa, script "dün ne oldu" diye bakar ve şu kurala
   göre karar verir:
     - Eğer kayıtlı durum (durum.json) zaten BUGÜNE YAKINSA
       (son 10 gün içindeyse) → demek ki manuel ilerletme bitmiş,
       kendisi otomatik olarak dünü ekleyip öğrenir.
     - Eğer kayıtlı durum hâlâ ESKİ bir tarihteyse (sen henüz
       manuel ilerletme sürecindesin) → HİÇBİR ŞEY YAPMAZ, sessizce
       çıkar. Senin işine karışmaz.

Her iki modda da:
- 0'dan bugüne kadarki (veya hedef tarihe kadarki) TÜM veriyle
  model eğitilir, son 3-4 yıla üstel ağırlık verilir.
- Eğer önceki bir durum varsa (yani bu bir /ilerlet veya otomatik
  güncellemeyse), önceki sorguların gerçek sonuçları açığa çıkarılır
  ve Telegram'a özet gönderilir.
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

OTOMATIK_ESIK_GUN = 10  # bugüne bu kadar gün kaldıysa "yakın" sayılır


def hedef_tarihi_belirle(tum_veri_son_tarih):
    """Manuel mi otomatik mi olduğuna karar verir, hedef tarihi döner."""
    manuel_tarih = os.environ.get("HEDEF_TARIH", "").strip()

    if manuel_tarih:
        print(f"📌 MANUEL MOD: Hedef tarih = {manuel_tarih}")
        return pd.Timestamp(manuel_tarih), True

    # Otomatik mod - guard kontrolü
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

    print(f"🤖 OTOMATİK MOD: Bugüne yakınsın (son eğitim: "
          f"{son_egitim_tarihi.date()}, sadece {fark_gun} gün fark var). "
          f"Kendi kendime dünü ekleyip öğreniyorum.")
    return min(tum_veri_son_tarih, bugun - timedelta(days=1)), False


if __name__ == "__main__":
    print("=" * 60)
    print("ADIM 1: BIST100 verisi çekiliyor...")
    print("=" * 60)
    veri_sozlugu, cekilemeyenler = tum_bist100_verisini_cek()

    print("\n" + "=" * 60)
    print("ADIM 2: Günlük özellik seti oluşturuluyor (her gün, her hisse)")
    print("=" * 60)
    tum_ozellik_df = tum_hisseler_icin_gunluk_ozellik_seti(veri_sozlugu)
    tum_veri_son_tarih = tum_ozellik_df['tarih'].max()
    print(f"Toplam satır: {len(tum_ozellik_df)} | Son veri tarihi: {tum_veri_son_tarih.date()}")

    hedef_tarih, manuel_mi = hedef_tarihi_belirle(tum_veri_son_tarih)

    onceki_durum = durumu_oku()  # git commit sonrası kalıcı, ilerlet/otomatik için lazım

    print("\n" + "=" * 60)
    print(f"ADIM 3: Model, {hedef_tarih.date()} tarihine kadarki veriyle eğitiliyor")
    print("=" * 60)
    egitim_kismi = tum_ozellik_df[tum_ozellik_df['tarih'] <= hedef_tarih]
    print(f"Eğitim örneği sayısı: {len(egitim_kismi)}")

    if len(egitim_kismi) < 200:
        print("⚠️ Yeterli veri yok, en az 200 örnek gerekiyor. Çıkılıyor.")
        sys.exit(0)

    siniflandirma_model, regresyon_model = modelleri_egit(egitim_kismi, hedef_tarih)
    modelleri_kaydet(siniflandirma_model, regresyon_model)

    # Güncel durum verisini de kaydediyoruz (sorgu.py bunu okuyacak)
    tum_ozellik_df[tum_ozellik_df['tarih'] <= hedef_tarih].to_csv('guncel_veri.csv', index=False)

    yeni_durum = durumu_kaydet(hedef_tarih.date(), len(egitim_kismi))

    mesaj = (
        f"✅ <b>Model Güncellendi</b>\n\n"
        f"Mod: {'Manuel' if manuel_mi else 'Otomatik (günlük)'}\n"
        f"Eğitim Tarihi: {hedef_tarih.date()}\n"
        f"Eğitim Örneği: {len(egitim_kismi)}\n"
    )

    # Önceki sorguların gerçek sonucunu açığa çıkar (varsa)
    if onceki_durum is not None:
        aciklama = onceki_sorgulari_degerlendir(tum_ozellik_df, hedef_tarih)
        if aciklama:
            mesaj += f"\n📊 <b>Önceki Sorgu Sonuçları Açığa Çıktı:</b>\n{aciklama}"

    print(mesaj)
    telegram_mesaj_gonder(mesaj)
