"""
/sorgu KOMUTU (v4 — Genişletilmiş Bağlam + SHAP Açıklaması)
================================================================
Tek akış: Veto (trend_yonu) -> Genel Tahmin (her zaman) -> 
Fibonacci Kademeli Hedefler (varsa, ek olarak).

YENİ: Somut direnç/destek fiyat seviyeleri, temas sayısı, 
başarısız kırılım sayısı, aşırı genişleme ve FVG bilgisi de 
bağlam olarak gösteriliyor.
"""

import os
import pandas as pd

from telegram_bildirim import telegram_mesaj_gonder
from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'
FIB_ORANLARI = {1: 1.272, 2: 1.618, 3: 2.0}


def shap_aciklama_uret(model, X, ust_kac=3):
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
        if isinstance(shap_values, list):
            degerler = shap_values[1][0]
        else:
            degerler = shap_values[0]
        seri = pd.Series(degerler, index=X.columns).sort_values(ascending=False)
        olumlu = seri[seri > 0].head(ust_kac)
        olumsuz = seri[seri < 0].sort_values().head(ust_kac)
        return olumlu, olumsuz
    except Exception as e:
        print(f"  ⚠️ SHAP açıklaması üretilemedi: {e}")
        return None, None


def sorgu_logla(egitim_tarihi, sembol, detay: dict):
    yeni_kayit = pd.DataFrame([{
        'tarih': egitim_tarihi, 'sembol': sembol.upper(),
        **detay,
        'gercek_sonuc': None, 'gerceklesen_getiri': None,
    }])
    if os.path.exists(SORGU_GECMISI_DOSYASI):
        eski = pd.read_csv(SORGU_GECMISI_DOSYASI)
        birlesik = pd.concat([eski, yeni_kayit], ignore_index=True)
    else:
        birlesik = yeni_kayit
    birlesik.to_csv(SORGU_GECMISI_DOSYASI, index=False)


PENCERE_GUN = 504  # trend_cizgisi.py ile aynı pencere


def temas_noktalarini_bul(hisse_verisi, max_goster=4):
    """
    Direnç (LH) ve destek (HL) çizgisini oluşturan GERÇEK temas 
    noktalarının tarih ve fiyatlarını döndürür - son 504 gün 
    penceresinden, en yakın tarihten geriye doğru.
    """
    son_pencere = hisse_verisi.tail(PENCERE_GUN)

    lh_noktalar = son_pencere[
        (son_pencere['pivot_high'] == True) & (son_pencere['swing_tip'] == 'LH')
    ][['tarih', 'High']].tail(max_goster)

    hl_noktalar = son_pencere[
        (son_pencere['pivot_low'] == True) & (son_pencere['swing_tip'] == 'HL')
    ][['tarih', 'Low']].tail(max_goster)

    return lh_noktalar, hl_noktalar


def bağlam_satirlarini_olustur(son, hisse_verisi=None):
    """Genişletilmiş bağlam: yapısal sinyaller + somut seviyeler + yeni özellikler."""
    satirlar = []

    if son.get('son_bos_gecerli') == 1 and son.get('son_bos_yonu') == 1:
        satirlar.append(f"✓ Geçerli BOS_YUKARI ({int(son['son_bos_gun_farki'])} gün önce)")

    if son.get('cizgi_de_onayladi') == 1:
        satirlar.append("✓ Trend çizgisi kırılımı + CHoCH aynı yönde onaylı")
    elif son.get('cizgi_kirildi_choch_bekleniyor') == 1:
        satirlar.append("✓ Direnç çizgisi kırıldı, CHoCH henüz teyit etmedi")

    if son.get('coklu_zaman_uyumu') == 1:
        satirlar.append("✓ Haftalık trend de YUKARI yönlü uyumlu")

    if son.get('likidite_avi_teyitli') == 1:
        satirlar.append("✓ Son dönüşte likidite avı (Wyckoff Spring) tespit edildi")

    if pd.notna(son.get('duzeltme_derinlik_yuzde')):
        satirlar.append(f"ℹ️ Son düzeltme derinliği: %{son['duzeltme_derinlik_yuzde']:.1f}")

    # YENİ: Somut direnç/destek seviyeleri + temas/başarısız kırılım sayısı
    # + GERÇEK TEMAS NOKTALARI (tarih ve fiyat)
    if pd.notna(son.get('direnc_seviye_fiyat')):
        satirlar.append(
            f"📍 Direnç: {son['direnc_seviye_fiyat']:.2f} TL "
            f"({int(son.get('direnc_temas_sayisi', 0))} temas, "
            f"{int(son.get('direnc_basarisiz_kirilim_sayisi', 0))} başarısız kırılım denemesi)"
        )
        if hisse_verisi is not None:
            lh_noktalar, _ = temas_noktalarini_bul(hisse_verisi)
            if not lh_noktalar.empty:
                nokta_metinleri = [
                    f"{pd.Timestamp(r['tarih']).strftime('%d.%m.%Y')}@{r['High']:.2f}"
                    for _, r in lh_noktalar.iterrows()
                ]
                satirlar.append(f"   Temas noktaları: {', '.join(nokta_metinleri)}")

    if pd.notna(son.get('destek_seviye_fiyat')):
        satirlar.append(
            f"📍 Destek: {son['destek_seviye_fiyat']:.2f} TL "
            f"({int(son.get('destek_temas_sayisi', 0))} temas, "
            f"{int(son.get('destek_basarisiz_kirilim_sayisi', 0))} başarısız kırılım denemesi)"
        )
        if hisse_verisi is not None:
            _, hl_noktalar = temas_noktalarini_bul(hisse_verisi)
            if not hl_noktalar.empty:
                nokta_metinleri = [
                    f"{pd.Timestamp(r['tarih']).strftime('%d.%m.%Y')}@{r['Low']:.2f}"
                    for _, r in hl_noktalar.iterrows()
                ]
                satirlar.append(f"   Temas noktaları: {', '.join(nokta_metinleri)}")

    # YENİ: Aşırı genişleme uyarısı
    if son.get('asiri_genisleme_bayragi') == 1:
        satirlar.append(
            f"⚠️ Aşırı genişleme: son 21 günde %{son.get('son_21_gun_getiri_yuzde', 0):.1f} "
            f"hareket - bu hissenin normalinin ÇOK üstünde, düzeltme riski artmış olabilir"
        )

    # YENİ: FVG bilgisi
    if son.get('yakin_bogaFVG_var') == 1:
        satirlar.append("ℹ️ Yakın zamanda doldurulmamış bir Fair Value Gap (FVG) var")

    return satirlar


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

    # ADIM 1 — VETO
    trend_yonu = son.get('trend_yonu', 0)
    if pd.notna(trend_yonu) and int(trend_yonu) == -1:
        mesaj = (
            f"⚠️ <b>{sembol.upper()} — LONG İÇİN RİSKLİ</b> ({egitim_tarihi.date()} durumu)\n\n"
            f"Trend yönü şu an AŞAĞI. Sistem sadece LONG fırsatlar önerir — "
            f"bu hissede şu an düşüş yapısı hâkim olduğu için LONG pozisyon "
            f"açmak riskli olabilir.\n\n🚫 Hedef/stop önerisi verilmiyor.\n"
        )
        try:
            eksik_kolon_veto = [k for k in OZELLIK_KOLONLARI if pd.isna(son.get(k))]
            if not eksik_kolon_veto:
                modeller_veto = modelleri_yukle()
                if modeller_veto.get('genel_siniflandirma') is not None:
                    X_veto = pd.DataFrame([son[OZELLIK_KOLONLARI].to_dict()]).astype(float)
                    olumlu, olumsuz = shap_aciklama_uret(modeller_veto['genel_siniflandirma'], X_veto)
                    if olumsuz is not None and len(olumsuz) > 0:
                        mesaj += "\n🔍 Riski artıran başlıca etkenler:\n"
                        for ozellik, deger in olumsuz.items():
                            mesaj += f"  {ozellik} ({deger:+.2f})\n"
        except Exception:
            pass
        mesaj += "\n⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
        sorgu_logla(egitim_tarihi, sembol, detay={'veto': 1})
        return mesaj

    eksik_kolon = [k for k in OZELLIK_KOLONLARI if pd.isna(son.get(k))]
    if eksik_kolon:
        return f"⚠️ {sembol} için eksik veri var: {eksik_kolon}"

    X = pd.DataFrame([son[OZELLIK_KOLONLARI].to_dict()]).astype(float)
    modeller = modelleri_yukle()

    # ADIM 2 — GENEL TAHMİN (her zaman)
    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        return f"⚠️ {sembol} için model bulunamadı, önce eğitim yapılmalı."

    genel_olasilik = float(modeller['genel_siniflandirma'].predict_proba(X)[0][1])
    genel_getiri_yuzde = abs(float(modeller['genel_regresyon'].predict(X)[0]))
    genel_hedef = guncel_fiyat * (1 + genel_getiri_yuzde / 100)
    atr = float(son.get('atr', guncel_fiyat * 0.02))
    genel_stop = guncel_fiyat - 1 * atr

    baglam_satirlari = bağlam_satirlarini_olustur(son, hisse_verisi)

    # BAYAT REFERANS KONTROLÜ: Fibonacci hesaplaması yapılmadan önce
    # kontrol ediyoruz - eğer en yakın hedef (1.272) bile güncel fiyatın
    # altında/çok yakınındaysa, fiyat bu swing'i zaten geçmiş demektir.
    giris_fiyat = son.get('son_yukari_giris_fiyat')
    swing_baslangic = son.get('son_yukari_swing_baslangic')
    stop_ref = son.get('son_pivot_low_fiyat')

    fib_hesaplanabilir = (
        pd.notna(giris_fiyat) and pd.notna(swing_baslangic) and
        pd.notna(stop_ref) and stop_ref < guncel_fiyat and
        (giris_fiyat - swing_baslangic) > 0 and
        any(modeller.get(f'hedef{i}') is not None for i in [1, 2, 3])
    )

    if fib_hesaplanabilir:
        hareket_kontrol = giris_fiyat - swing_baslangic
        hedef1_kontrol = giris_fiyat + hareket_kontrol * (1.272 - 1)
        if hedef1_kontrol <= guncel_fiyat:
            fib_hesaplanabilir = False
            baglam_satirlari.append(
                "ℹ️ Önceki BOS referansı fiyatın gerisinde kaldı (hedefler "
                "zaten geçilmiş) - yeni bir Fibonacci hedefi için yeni bir "
                "sinyal bekleniyor."
            )

    baglam_metni = "\n".join(baglam_satirlari) if baglam_satirlari else "Belirgin ek yapısal bağlam yok"

    hedef_mesafe = genel_hedef - guncel_fiyat
    stop_mesafe = guncel_fiyat - genel_stop
    rr_orani = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0
    rr_uyarisi = "\n⚠️ R/R oranı düşük (1:1.5 altı)." if rr_orani < 1.5 else ""

    mesaj = (
        f"🔮 <b>{sembol.upper()} LONG Tahmin</b> ({egitim_tarihi.date()} durumu)\n\n"
        f"📊 Bağlam:\n{baglam_metni}\n\n"
        f"Başarı Olasılığı: %{genel_olasilik*100:.0f}\n"
        f"Beklenen Hareket: %{genel_getiri_yuzde:.1f}\n\n"
        f"💰 Güncel: {guncel_fiyat:.2f} TL\n"
        f"🎯 Hedef: {genel_hedef:.2f} TL\n"
        f"🛑 Stop: {genel_stop:.2f} TL (ATR bazlı)\n"
        f"⚖️ R/R: 1:{rr_orani:.2f}{rr_uyarisi}\n"
    )

    olumlu, olumsuz = shap_aciklama_uret(modeller['genel_siniflandirma'], X)
    if olumlu is not None:
        if len(olumlu) > 0:
            mesaj += "\n🔍 Bu tahmini destekleyen etkenler:\n"
            for ozellik, deger in olumlu.items():
                mesaj += f"  {ozellik} ({deger:+.2f})\n"
        if len(olumsuz) > 0:
            mesaj += "\n⚠️ Güveni azaltan etkenler:\n"
            for ozellik, deger in olumsuz.items():
                mesaj += f"  {ozellik} ({deger:+.2f})\n"

    log_detay = {
        'genel_olasilik': round(genel_olasilik, 3),
        'genel_hedef': round(genel_hedef, 2),
        'guncel_fiyat': guncel_fiyat,
        'stop_fiyat': genel_stop,
    }

    # ADIM 3 — FİBONACCİ KADEMELİ HEDEFLER (varsa, ek bilgi)
    # (giris_fiyat, swing_baslangic, stop_ref, fib_hesaplanabilir 
    # zaten yukarıda hesaplandı - bayat referans kontrolüyle birlikte)

    if fib_hesaplanabilir:
        hareket = giris_fiyat - swing_baslangic
        stop_fiyat_fib = float(stop_ref)
        stop_mesafe_fib = guncel_fiyat - stop_fiyat_fib

        satirlar = ["\n📐 <b>Fibonacci Kademeli Hedefler</b> (yapısal swing bazlı):"]
        for hedef_no, oran in FIB_ORANLARI.items():
            model_h = modeller.get(f'hedef{hedef_no}')
            hedef_fiyat = giris_fiyat + hareket * (oran - 1)
            hedef_mesafe_fib = hedef_fiyat - guncel_fiyat
            rr_fib = hedef_mesafe_fib / stop_mesafe_fib if stop_mesafe_fib > 0 else 0

            if model_h is not None:
                olasilik = float(model_h.predict_proba(X)[0][1])
                olasilik_metni = f"%{olasilik*100:.0f}"
                log_detay[f'hedef{hedef_no}_olasilik'] = round(olasilik, 3)
            else:
                olasilik_metni = "yetersiz veri"
                log_detay[f'hedef{hedef_no}_olasilik'] = None

            satirlar.append(
                f"  Hedef {hedef_no} (1:{oran}): {hedef_fiyat:.2f} TL | "
                f"Olasılık: {olasilik_metni} | R/R: 1:{rr_fib:.2f}"
            )
            log_detay[f'hedef{hedef_no}_fiyat'] = round(hedef_fiyat, 2)

        satirlar.append(f"  Yapısal Stop: {stop_fiyat_fib:.2f} TL (son pivot)")
        mesaj += "\n" + "\n".join(satirlar)

    mesaj += "\n\n⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."

    sorgu_logla(egitim_tarihi, sembol, detay=log_detay)
    return mesaj


if __name__ == "__main__":
    sembol = os.environ.get("SORGU_SEMBOL", "TUPRS")
    mesaj = sorgula(sembol)
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
