"""
/sorgu KOMUTU — SADECE LONG (YUKARI) SİNYAL VERSİYONU
========================================================
Sistem SADECE long (yukarı yönlü) fırsatları önerir.

Eğer o hissede yapısal olarak AŞAĞI yönlü bir sinyal (geçerli BOS_ASAGI)
varsa, bu bir "short öner" anlamına gelmez — bunun yerine kullanıcıya
"şu an long açmak riskli olabilir" uyarısı verilir, hiçbir hedef/stop
önerilmez.

Yapısal sinyal yoksa veya yukarı yönlüyse, normal long analizi yapılır.
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


def stop_seviyesi_hesapla(guncel_fiyat, atr):
    """Long pozisyon için stop her zaman fiyatın altında olur."""
    return guncel_fiyat - 1 * atr


def sorgu_logla(egitim_tarihi, sembol, yon, basari_olasiligi,
                 beklenen_getiri_yuzde, mod):
    yeni_kayit = pd.DataFrame([{
        'tarih': egitim_tarihi, 'sembol': sembol.upper(), 'yon': yon,
        'tahmin_basari_olasiligi': round(basari_olasiligi, 3) if basari_olasiligi is not None else None,
        'beklenen_getiri_yuzde': round(beklenen_getiri_yuzde, 2) if beklenen_getiri_yuzde is not None else None,
        'mod': mod,
        'gercek_sonuc': None, 'gerceklesen_getiri': None,
    }])
    if os.path.exists(SORGU_GECMISI_DOSYASI):
        eski = pd.read_csv(SORGU_GECMISI_DOSYASI)
        birlesik = pd.concat([eski, yeni_kayit], ignore_index=True)
    else:
        birlesik = yeni_kayit
    birlesik.to_csv(SORGU_GECMISI_DOSYASI, index=False)


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
    yapisal_yon = int(son_satir['son_bos_yonu']) if yapisal_gecerli else 0

    # ============================================================
    # DURUM 1: Yapısal olarak AŞAĞI yönlü geçerli bir sinyal var
    # -> LONG önerilmez, risk uyarısı verilir. Hedef/stop YOK.
    # ============================================================
    if yapisal_gecerli and yapisal_yon == -1:
        mesaj = (
            f"⚠️ <b>{sembol.upper()} — LONG İÇİN RİSKLİ</b> ({egitim_tarihi.date()} durumu)\n\n"
            f"Son BOS {int(son_satir['son_bos_gun_farki'])} gün önce AŞAĞI yönlü "
            f"oluştu ve hâlâ geçerli (ters yönlü kırılım yok).\n\n"
            f"Sistem sadece LONG (yukarı yönlü) fırsatlar önerir — bu hissede şu an "
            f"düşüş yapısı hâkim olduğu için LONG pozisyon açmak riskli olabilir.\n\n"
            f"🚫 Hedef/stop önerisi verilmiyor.\n\n"
            f"⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
        )
        sorgu_logla(egitim_tarihi, sembol, yon=-1, basari_olasiligi=None,
                    beklenen_getiri_yuzde=None, mod='risk_uyarisi_asagi')
        return mesaj

    # ============================================================
    # DURUM 2: Yapısal olarak YUKARI geçerli sinyal VAR
    # -> Yapısal Sinyal Modu, normal LONG analizi
    # DURUM 3: Yapısal sinyal YOK
    # -> Genel Hareket Modu, normal LONG analizi (varsayılan yukarı bakış)
    # ============================================================
    yon = 1  # Bu noktaya geldiysek zaten LONG analiz yapıyoruz

    eksik_kolon = [k for k in OZELLIK_KOLONLARI if pd.isna(son_satir.get(k))]
    if eksik_kolon:
        return f"⚠️ {sembol} için eksik veri var: {eksik_kolon}"

    X = pd.DataFrame([son_satir[OZELLIK_KOLONLARI].to_dict()]).astype(float)

    siniflandirma_model, regresyon_model = modelleri_yukle()
    basari_olasiligi = float(siniflandirma_model.predict_proba(X)[0][1])
    beklenen_getiri_yuzde = abs(float(regresyon_model.predict(X)[0]))

    guncel_fiyat = float(son_satir['Close'])
    hedef_fiyat = guncel_fiyat * (1 + beklenen_getiri_yuzde / 100)
    atr = float(son_satir.get('atr', guncel_fiyat * 0.02))
    stop_fiyat = stop_seviyesi_hesapla(guncel_fiyat, atr)

    hedef_mesafe = hedef_fiyat - guncel_fiyat
    stop_mesafe = guncel_fiyat - stop_fiyat
    rr_orani = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0

    rr_uyarisi = ""
    if rr_orani < 1.5:
        rr_uyarisi = "\n⚠️ <b>R/R oranı düşük (1:1.5 altı) — bu sinyal zayıf, dikkatli ol.</b>"

    mod_aciklamasi = (
        f"Yapısal Sinyal Modu — son BOS {int(son_satir['son_bos_gun_farki'])} gün önce "
        f"YUKARI yönlü oluştu, hâlâ geçerli."
        if (yapisal_gecerli and yapisal_yon == 1) else
        "Genel Hareket Modu — aktif yapısal sinyal yok, model genel gösterge "
        "durumuna göre LONG tahmin üretiyor (daha az güvenilir)."
    )

    mesaj = (
        f"🔮 <b>{sembol.upper()} LONG Tahmin</b> ({egitim_tarihi.date()} durumu)\n\n"
        f"📊 {mod_aciklamasi}\n\n"
        f"Başarı Olasılığı: %{basari_olasiligi*100:.0f}\n"
        f"Beklenen Hareket: %{beklenen_getiri_yuzde:.1f}\n\n"
        f"💰 Güncel: {guncel_fiyat:.2f} TL\n"
        f"🎯 Hedef: {hedef_fiyat:.2f} TL\n"
        f"🛑 Stop: {stop_fiyat:.2f} TL\n"
        f"⚖️ R/R Oranı: 1 : {rr_orani:.2f}"
        f"{rr_uyarisi}\n\n"
        f"⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
    )

    mod_kisa = 'yapisal' if (yapisal_gecerli and yapisal_yon == 1) else 'genel'
    sorgu_logla(egitim_tarihi, sembol, yon=1, basari_olasiligi=basari_olasiligi,
                beklenen_getiri_yuzde=beklenen_getiri_yuzde, mod=mod_kisa)

    return mesaj


if __name__ == "__main__":
    sembol = os.environ.get("SORGU_SEMBOL", "TUPRS")
    mesaj = sorgula(sembol)
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
