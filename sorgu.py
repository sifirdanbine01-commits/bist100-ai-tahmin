"""
/sorgu KOMUTU (v3 — Tek Akış, Dallanma Yok)
==============================================
ESKİ TASARIMDAKİ SORUN: "Yapısal Mod / Çizgi Modu / Genel Mod" diye
üç ayrı dal vardı, biri seçilince diğerleri tamamen görmezden
geliniyordu - bu yüzden çoğu sorguda sadece "Genel Hareket Modu,
yapısal referans yok" gibi zayıf bir mesaj görünüyordu, halbuki
trend çizgisi/haftalık uyum/likidite avı gibi zengin bilgiler zaten
o "genel" modelin İÇİNDE kullanılıyordu ama SANA gösterilmiyordu.

YENİ TASARIM:
1) VETO (tek koşulsuz güvenlik kuralı - kalıyor, kaldırılmadı)
2) Genel olasılık/hedef HER ZAMAN hesaplanır ve gösterilir
   (model zaten trend_yonu, çizgi, haftalık uyum, likidite avı
   dahil TÜM 24 özelliği görüyor - "genel" demek "zayıf" değil,
   sadece "kademeli Fibonacci hedefi ek olarak yok" demek)
3) Fibonacci kademeli hedefler (Hedef1/2/3), hesaplanabiliyorsa
   (yapısal swing verisi varsa) HER ZAMAN genel tahminin YANINA
   EK bilgi olarak eklenir - onun yerine geçmez, bir "mod" değildir
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
    """
    Bu SPESİFİK tahmine hangi özelliklerin ne kadar (olumlu/olumsuz)
    katkı sağladığını döndürür. Model çalışamazsa None döner (mesajı
    bozmadan sessizce atlanır).
    """
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
        if isinstance(shap_values, list):
            degerler = shap_values[1][0]  # pozitif sınıf (başarılı)
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
    # ADIM 1 — VETO (Tek Koşulsuz Güvenlik Kuralı)
    # ============================================================
    trend_yonu = son.get('trend_yonu', 0)
    if pd.notna(trend_yonu) and int(trend_yonu) == -1:
        mesaj = (
            f"⚠️ <b>{sembol.upper()} — LONG İÇİN RİSKLİ</b> ({egitim_tarihi.date()} durumu)\n\n"
            f"Trend yönü şu an AŞAĞI. Sistem sadece LONG fırsatlar önerir — "
            f"bu hissede şu an düşüş yapısı hâkim olduğu için LONG pozisyon "
            f"açmak riskli olabilir.\n\n🚫 Hedef/stop önerisi verilmiyor.\n"
        )
        # "Neden riskli" - hangi göstergeler bu düşüş görünümüne katkı sağlıyor
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

    # ============================================================
    # ADIM 2 — GENEL TAHMİN (HER ZAMAN HESAPLANIR, ANA GÖVDE)
    # ============================================================
    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        return f"⚠️ {sembol} için model bulunamadı, önce eğitim yapılmalı."

    genel_olasilik = float(modeller['genel_siniflandirma'].predict_proba(X)[0][1])
    genel_getiri_yuzde = abs(float(modeller['genel_regresyon'].predict(X)[0]))
    genel_hedef = guncel_fiyat * (1 + genel_getiri_yuzde / 100)
    atr = float(son.get('atr', guncel_fiyat * 0.02))
    genel_stop = guncel_fiyat - 1 * atr

    # Bu tahmine katkı sağlayan yapısal bağlam bilgileri (şeffaflık için)
    baglam_satirlari = []
    if son.get('son_bos_gecerli') == 1 and son.get('son_bos_yonu') == 1:
        baglam_satirlari.append(f"✓ Geçerli BOS_YUKARI ({int(son['son_bos_gun_farki'])} gün önce)")
    if son.get('cizgi_de_onayladi') == 1:
        baglam_satirlari.append("✓ Trend çizgisi kırılımı + CHoCH aynı yönde onaylı")
    elif son.get('cizgi_kirildi_choch_bekleniyor') == 1:
        baglam_satirlari.append("✓ Direnç çizgisi kırıldı, CHoCH henüz teyit etmedi")
    if son.get('coklu_zaman_uyumu') == 1:
        baglam_satirlari.append("✓ Haftalık trend de YUKARI yönlü uyumlu")
    if son.get('likidite_avi_teyitli') == 1:
        baglam_satirlari.append("✓ Son dönüşte likidite avı (Wyckoff Spring) tespit edildi")
    if pd.notna(son.get('duzeltme_derinlik_yuzde')):
        baglam_satirlari.append(f"ℹ️ Son düzeltme derinliği: %{son['duzeltme_derinlik_yuzde']:.1f}")

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

    # "Neden bu olasılık" - hangi özellikler tahmini yukarı/aşağı çekti
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

    # ============================================================
    # ADIM 3 — FİBONACCİ KADEMELİ HEDEFLER (VARSA, EK BİLGİ OLARAK)
    # ============================================================
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
