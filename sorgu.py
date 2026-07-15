"""
/sorgu KOMUTU — TEMİZ VERSİYON
================================
Kayıtlı modeli okur, istenen hissenin GÜNCEL DURUMUNU (guncel_veri.csv
içinden, son eğitim tarihi itibariyle) alır, tahmin üretir.

ÖNEMLİ: Bu dosya market_structure.py veya gostergeler.py'yi
İMPORT ETMEZ — çünkü guncel_veri.csv zaten hesaplanmış tüm
göstergeleri içeriyor (RSI, ATR, BOS bilgisi vb.). Bu yüzden
pandas-ta-classic gibi ağır kütüphanelere ihtiyaç duymaz,
sadece pandas + lightgbm + joblib yeterlidir.
"""

import os
import pandas as pd
import joblib

from telegram_bildirim import telegram_mesaj_gonder
from durum import durumu_oku

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'

OZELLIK_KOLONLARI = [
    'rsi_14', 'macd_hist', 'adx', 'hacim_orani', 'bb_genislik',
    'stoch_k', 'fiyat_ma200_ustu', 'ema_kesisim_yukari',
    'son_bos_gun_farki', 'son_bos_yonu', 'son_bos_gecerli',
]


def modelleri_yukle():
    siniflandirma_model = joblib.load('model_siniflandirma.pkl')
    regresyon_model = joblib.load('model_regresyon.pkl')
    return siniflandirma_model, regresyon_model


def stop_seviyesi_hesapla(guncel_fiyat, atr, yon):
    """ATR bazlı basit stop hesaplama - ekstra veri gerektirmez."""
    if yon == 1:
        return guncel_fiyat - 2 * atr
    else:
        return guncel_fiyat + 2 * atr


def sorgula(sembol):
    durum = durumu_oku()
    if durum is None:
        return "⚠️ Henüz hiç model eğitilmedi. Önce 'Egit veya Ilerlet' workflow'unu çalıştır."

    if not os.path.exists('guncel_veri.csv') or not os.path.exists('model_siniflandirma.pkl'):
        return "⚠️ Model dosyaları bulunamadı. Önce 'Egit veya Ilerlet' workflow'unu çalıştır."

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi'])

    guncel_veri = pd.read_csv('guncel_veri.csv')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    hisse_verisi = guncel_veri[guncel_veri['sembol'] == sembol.upper()].sort_values('tarih')
    if hisse_verisi.empty:
        return (f"⚠️ {sembol} için veri bulunamadı. Sembolü kontrol et veya "
                f"bu hisse şu anki hisse listesinde olmayabilir.")

    son_satir = hisse_verisi.iloc[-1]

    yapisal_gecerli = son_satir['son_bos_gecerli'] == 1
    yon = int(son_satir['son_bos_yonu']) if yapisal_gecerli else 1

    eksik_kolon = [k for k in OZELLIK_KOLONLARI if pd.isna(son_satir.get(k))]
    if eksik_kolon:
        return f"⚠️ {sembol} için eksik veri var: {eksik_kolon}"

    X = pd.DataFrame([son_satir[OZELLIK_KOLONLARI].to_dict()]).astype(float)

    siniflandirma_model, regresyon_model = modelleri_yukle()
    basari_olasiligi = float(siniflandirma_model.predict_proba(X)[0][1])
    beklenen_getiri_yuzde = float(regresyon_model.predict(X)[0])

    guncel_fiyat = float(son_satir['Close'])
    hedef_fiyat = guncel_fiyat * (1 + beklenen_getiri_yuzde / 100)
    atr = float(son_satir.get('atr', guncel_fiyat * 0.02))  # atr yoksa kaba tahmin
    stop_fiyat = stop_seviyesi_hesapla(guncel_fiyat, atr, yon)

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
        f"🎯 Hedef: {hedef_fiyat:.2f} TL\n"
        f"🛑 Stop: {stop_fiyat:.2f} TL\n\n"
        f"⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
    )

    yeni_kayit = pd.DataFrame([{
        'tarih': egitim_tarihi, 'sembol': sembol.upper(), 'yon': yon,
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
