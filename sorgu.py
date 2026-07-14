"""
/sorgu KOMUTU (Birleşik Model Versiyonu)
==========================================
Kayıtlı modeli (guncelle.py tarafından eğitilmiş) okur, istenen
hissenin GÜNCEL DURUMUNU (son eğitim tarihi itibariyle) alır,
tahmin üretir. Sonucu sorgu_gecmisi.csv'ye loglar (ileride
sonuc_ac.py bunun gerçek sonucunu değerlendirecek).
"""

import os
import pandas as pd
from datetime import datetime

from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI
from durum import durumu_oku
from telegram_bildirim import telegram_mesaj_gonder
from market_structure import market_structure_tespit_et
from gostergeler import gostergeleri_ekle

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'


def stop_seviyesi_hesapla(df_g, son_index, yon):
    """Yapısal pivot ile ATR bazlı stop'un daha temkinli olanını seçer."""
    atr = df_g['atr'].iloc[son_index]
    giris = df_g['Close'].iloc[son_index]

    if yon == 1:
        atr_stop = giris - 2 * atr
        pivotlar = df_g.iloc[max(0, son_index - 40):son_index]
        pivot_lowlar = pivotlar[pivotlar['pivot_low']]['Low']
        yapisal_stop = pivot_lowlar.iloc[-1] if not pivot_lowlar.empty else atr_stop
        return max(atr_stop, yapisal_stop)  # ikisinden giriş fiyatına yakın olan (temkinli)
    else:
        atr_stop = giris + 2 * atr
        pivotlar = df_g.iloc[max(0, son_index - 40):son_index]
        pivot_highlar = pivotlar[pivotlar['pivot_high']]['High']
        yapisal_stop = pivot_highlar.iloc[-1] if not pivot_highlar.empty else atr_stop
        return min(atr_stop, yapisal_stop)


def sorgula(sembol):
    durum = durumu_oku()
    if durum is None:
        return "⚠️ Henüz hiç model eğitilmedi. Önce /egit komutunu çalıştır."

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi'])

    guncel_veri = pd.read_csv('guncel_veri.csv')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    hisse_verisi = guncel_veri[guncel_veri['sembol'] == sembol.upper()].sort_values('tarih')
    if hisse_verisi.empty:
        return f"⚠️ {sembol} için veri bulunamadı."

    son_satir = hisse_verisi.iloc[-1]

    yapisal_gecerli = son_satir['son_bos_gecerli'] == 1
    yon = int(son_satir['son_bos_yonu']) if yapisal_gecerli else 1  # yoksa varsayılan yön (regresyon karar verecek)

    X = pd.DataFrame([son_satir[OZELLIK_KOLONLARI].to_dict()]).astype(float)

    siniflandirma_model, regresyon_model = modelleri_yukle()
    basari_olasiligi = siniflandirma_model.predict_proba(X)[0][1]
    beklenen_getiri_yuzde = regresyon_model.predict(X)[0]

    guncel_fiyat = son_satir['Close']
    if beklenen_getiri_yuzde >= 0:
        hedef_fiyat = guncel_fiyat * (1 + beklenen_getiri_yuzde / 100)
        gercek_yon = 1
    else:
        hedef_fiyat = guncel_fiyat * (1 + beklenen_getiri_yuzde / 100)
        gercek_yon = -1

    mod_aciklamasi = (
        f"Yapısal Sinyal Modu — son BOS {int(son_satir['son_bos_gun_farki'])} gün önce "
        f"oluştu, hâlâ geçerli."
        if yapisal_gecerli else
        "Genel Hareket Modu — aktif yapısal sinyal yok, model genel gösterge "
        "durumuna göre tahmin üretiyor (daha az güvenilir)."
    )

    mesaj = (
        f"🔮 <b>{sembol.upper()} Tahmin</b> ({egitim_tarihi.date()} durumu)\n\n"
        f"📊 {mod_aciklamasi}\n\n"
        f"Başarı Olasılığı: %{basari_olasiligi*100:.0f}\n"
        f"Beklenen Hareket: %{beklenen_getiri_yuzde:+.1f}\n\n"
        f"💰 Güncel: {guncel_fiyat:.2f} TL\n"
        f"🎯 Hedef: {hedef_fiyat:.2f} TL\n\n"
        f"⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
    )

    # Sorguyu logla (ileride sonuc_ac.py gerçek sonucu bulacak)
    yeni_kayit = pd.DataFrame([{
        'tarih': egitim_tarihi, 'sembol': sembol.upper(), 'yon': gercek_yon,
        'tahmin_basari_olasiligi': round(basari_olasiligi, 3),
        'beklenen_getiri_yuzde': round(beklenen_getiri_yuzde, 2),
        'mod': 'yapisal' if yapisal_gecerli else 'genel',
        'gercek_sonuc': None, 'gerceklesen_getiri': None,
    }])

    if os.path.exists(SORGU_GECMISI_DOSYASI):
        eski = pd.read_csv(SORGU_GECMISI_DOSYASI)
        birlesik = pd.concat([eski, yeni_kayit], ignore_index=True)
    else:
        birlesik = yeni_kayit
    birlesik.to_csv(SORGU_GECMISI_DOSYASI, index=False)

    return mesaj


if __name__ == "__main__":
    sembol = os.environ.get("SORGU_SEMBOL", "TUPRS")
    mesaj = sorgula(sembol)
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
