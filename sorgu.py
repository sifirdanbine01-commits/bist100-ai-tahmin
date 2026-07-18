"""
/sorgu KOMUTU (v2 — Veto + Kademeli Fibonacci Hedefler)
===========================================================
AKIŞ:
1) trend_yonu == -1 ise → LONG VETO, risk uyarısı (hiçbir hedef 
   önerilmez). Bu, sadece geçerli BOS_ASAGI değil, CHoCH_ASAGI ile 
   henüz BOS'a dönüşmemiş ama trend'in zaten döndüğü durumları da 
   kapsar (AEFES örneğinde doğruladığımız kural).

2) Veto yoksa, geçerli bir "son yukarı swing" referansı var mı bak:
   VARSA → Fibonacci Kademeli Hedef Modu (Hedef 1/2/3, yapısal stop)
   YOKSA → Genel Hareket Modu (eski sistem: tek hedef, ATR stop)
"""

import os
import pandas as pd
import joblib

from telegram_bildirim import telegram_mesaj_gonder
from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'

FIB_ORANLARI = {1: 1.272, 2: 1.618, 3: 2.0}


def sorgu_logla(egitim_tarihi, sembol, mod, detay: dict):
    yeni_kayit = pd.DataFrame([{
        'tarih': egitim_tarihi, 'sembol': sembol.upper(), 'mod': mod,
        **detay,
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
    if not os.path.exists('guncel_veri.csv'):
        return "⚠️ guncel_veri.csv bulunamadı. Önce 'Egit veya Ilerlet' workflow'unu çalıştır."

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi'])
    guncel_veri = pd.read_csv('guncel_veri.csv')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    hisse_verisi = guncel_veri[guncel_veri['sembol'] == sembol.upper()].sort_values('tarih')
    if hisse_verisi.empty:
        return f"⚠️ {sembol} için veri bulunamadı. Sembolü kontrol et."

    son = hisse_verisi.iloc[-1]
    guncel_fiyat = float(son['Close'])

    # ============================================================
    # ADIM 1 — TREND YÖNÜ VETOSU
    # ============================================================
    trend_yonu = son.get('trend_yonu', 0)
    if pd.notna(trend_yonu) and int(trend_yonu) == -1:
        mesaj = (
            f"⚠️ <b>{sembol.upper()} — LONG İÇİN RİSKLİ</b> ({egitim_tarihi.date()} durumu)\n\n"
            f"Trend yönü şu an AŞAĞI (son yapısal kırılım aşağı yönlü, "
            f"henüz yukarı dönüş yok).\n\n"
            f"Sistem sadece LONG fırsatlar önerir — bu hissede şu an "
            f"düşüş yapısı hâkim olduğu için LONG pozisyon açmak riskli olabilir.\n\n"
            f"🚫 Hedef/stop önerisi verilmiyor.\n\n"
            f"⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
        )
        sorgu_logla(egitim_tarihi, sembol, mod='risk_uyarisi_asagi', detay={})
        return mesaj

    eksik_kolon = [k for k in OZELLIK_KOLONLARI if pd.isna(son.get(k))]
    if eksik_kolon:
        return f"⚠️ {sembol} için eksik veri var: {eksik_kolon}"

    X = pd.DataFrame([son[OZELLIK_KOLONLARI].to_dict()]).astype(float)
    modeller = modelleri_yukle()

    # ============================================================
    # ADIM 2 — Fibonacci Kademeli Hedef Modu mu, Genel Mod mu?
    # ============================================================
    giris_fiyat = son.get('son_yukari_giris_fiyat')
    swing_baslangic = son.get('son_yukari_swing_baslangic')
    stop_ref = son.get('son_pivot_low_fiyat')

    fib_moda_uygun = (
        pd.notna(giris_fiyat) and pd.notna(swing_baslangic) and
        pd.notna(stop_ref) and stop_ref < guncel_fiyat and
        (giris_fiyat - swing_baslangic) > 0 and
        any(modeller.get(f'hedef{i}') is not None for i in [1, 2, 3])
    )

    yapisal_aktif = (son.get('son_bos_gecerli') == 1 and son.get('son_bos_yonu') == 1)

    if fib_moda_uygun:
        hareket = giris_fiyat - swing_baslangic
        stop_fiyat = float(stop_ref)
        stop_mesafe = guncel_fiyat - stop_fiyat

        mod_aciklamasi = (
            "Yapısal Sinyal Modu — geçerli BOS_YUKARI referansı kullanılıyor."
            if yapisal_aktif else
            "Trend Çizgisi Modu — direnç kırılımı referans alınıyor "
            "(henüz taze BOS yok ama yapısal kanıt var)."
        )

        satirlar = []
        detay_log = {}
        for hedef_no, oran in FIB_ORANLARI.items():
            model_h = modeller.get(f'hedef{hedef_no}')
            hedef_fiyat = giris_fiyat + hareket * (oran - 1)
            hedef_mesafe = hedef_fiyat - guncel_fiyat
            rr = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0

            if model_h is not None:
                olasilik = float(model_h.predict_proba(X)[0][1])
                olasilik_metni = f"%{olasilik*100:.0f}"
                detay_log[f'hedef{hedef_no}_olasilik'] = round(olasilik, 3)
            else:
                olasilik_metni = "yetersiz veri"
                detay_log[f'hedef{hedef_no}_olasilik'] = None

            satirlar.append(
                f"🎯 Hedef {hedef_no} (1:{oran}): {hedef_fiyat:.2f} TL "
                f"| Olasılık: {olasilik_metni} | R/R: 1:{rr:.2f}"
            )
            detay_log[f'hedef{hedef_no}_fiyat'] = round(hedef_fiyat, 2)

        mesaj = (
            f"🔮 <b>{sembol.upper()} LONG — Kademeli Hedef</b> ({egitim_tarihi.date()} durumu)\n\n"
            f"📊 {mod_aciklamasi}\n\n"
            f"💰 Güncel: {guncel_fiyat:.2f} TL\n"
            f"🛑 Stop: {stop_fiyat:.2f} TL (son yapısal pivot)\n\n"
            + "\n".join(satirlar) +
            f"\n\n⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
        )

        sorgu_logla(egitim_tarihi, sembol,
                    mod='yapisal' if yapisal_aktif else 'cizgi',
                    detay={'guncel_fiyat': guncel_fiyat, 'stop_fiyat': stop_fiyat, **detay_log})
        return mesaj

    # ============================================================
    # GENEL MOD (fallback — yapısal referans yok)
    # ============================================================
    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        return f"⚠️ {sembol} için model bulunamadı, önce eğitim yapılmalı."

    basari_olasiligi = float(modeller['genel_siniflandirma'].predict_proba(X)[0][1])
    beklenen_getiri_yuzde = abs(float(modeller['genel_regresyon'].predict(X)[0]))

    hedef_fiyat = guncel_fiyat * (1 + beklenen_getiri_yuzde / 100)
    atr = float(son.get('atr', guncel_fiyat * 0.02))
    stop_fiyat = guncel_fiyat - 1 * atr

    hedef_mesafe = hedef_fiyat - guncel_fiyat
    stop_mesafe = guncel_fiyat - stop_fiyat
    rr_orani = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0
    rr_uyarisi = "\n⚠️ <b>R/R oranı düşük (1:1.5 altı).</b>" if rr_orani < 1.5 else ""

    mesaj = (
        f"🔮 <b>{sembol.upper()} LONG Tahmin</b> ({egitim_tarihi.date()} durumu)\n\n"
        f"📊 Genel Hareket Modu — yapısal referans yok, göstergelere göre tahmin.\n\n"
        f"Başarı Olasılığı: %{basari_olasiligi*100:.0f}\n"
        f"Beklenen Hareket: %{beklenen_getiri_yuzde:.1f}\n\n"
        f"💰 Güncel: {guncel_fiyat:.2f} TL\n"
        f"🎯 Hedef: {hedef_fiyat:.2f} TL\n"
        f"🛑 Stop: {stop_fiyat:.2f} TL (ATR bazlı)\n"
        f"⚖️ R/R Oranı: 1:{rr_orani:.2f}"
        f"{rr_uyarisi}\n\n"
        f"⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
    )

    sorgu_logla(egitim_tarihi, sembol, mod='genel',
                detay={'guncel_fiyat': guncel_fiyat, 'stop_fiyat': stop_fiyat,
                       'hedef1_fiyat': round(hedef_fiyat, 2),
                       'hedef1_olasilik': round(basari_olasiligi, 3)})
    return mesaj


if __name__ == "__main__":
    sembol = os.environ.get("SORGU_SEMBOL", "TUPRS")
    mesaj = sorgula(sembol)
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
