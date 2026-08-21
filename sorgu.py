"""
/sorgu KOMUTU (v5 — Bileşen Bazlı Analiz)
================================================================
Analiz mantığı artık `analiz_bilesenleri()` fonksiyonunda üretiliyor,
hem sorgula() (Telegram mesajı) hem de PDF modülü bunu kullanıyor.
Böylece ikisi HER ZAMAN aynı sayılara dayanır, tutarsızlık olmaz.
"""

import os
import pandas as pd

from telegram_bildirim import telegram_mesaj_gonder
from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI
from bolge_tespiti import bolgeleri_bul

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'
FIB_ORANLARI = {1: 1.272, 2: 1.618, 3: 2.0}
PENCERE_GUN = 504


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


def bağlam_satirlarini_olustur(son, bolgeler=None):
    """Her satırı {'metin': str, 'tip': 'direnc'|'destek'|'normal'}
    olarak döndürür - PDF'te renklendirmek için tip bilgisi taşınıyor."""
    satirlar = []

    if son.get('son_bos_gecerli') == 1 and son.get('son_bos_yonu') == 1:
        satirlar.append({'metin': f"✓ Geçerli BOS_YUKARI ({int(son['son_bos_gun_farki'])} gün önce)", 'tip': 'normal'})

    if son.get('cizgi_de_onayladi') == 1:
        satirlar.append({'metin': "✓ Trend çizgisi kırılımı + CHoCH aynı yönde onaylı", 'tip': 'normal'})
    elif son.get('cizgi_kirildi_choch_bekleniyor') == 1:
        satirlar.append({'metin': "✓ Direnç çizgisi kırıldı, CHoCH henüz teyit etmedi", 'tip': 'normal'})

    if son.get('coklu_zaman_uyumu') == 1:
        satirlar.append({'metin': "✓ Haftalık trend de YUKARI yönlü uyumlu", 'tip': 'normal'})

    if son.get('likidite_avi_teyitli') == 1:
        satirlar.append({'metin': "✓ Son dönüşte likidite avı (Wyckoff Spring) tespit edildi", 'tip': 'normal'})

    if pd.notna(son.get('duzeltme_derinlik_yuzde')):
        satirlar.append({'metin': f"ℹ️ Son düzeltme derinliği: %{son['duzeltme_derinlik_yuzde']:.1f}", 'tip': 'normal'})

    if bolgeler is not None:
        direnc_aktif = bolgeler['direnc_bolgeleri']
        destek_aktif = bolgeler['destek_bolgeleri']

        for idx, b in enumerate(direnc_aktif[:2], start=1):
            nokta_metinleri = [
                f"{pd.Timestamp(t).strftime('%d.%m.%Y')}@{f:.2f}"
                for t, f in b['noktalar']
            ]
            satirlar.append({
                'metin': f"📍 Direnç Bölgesi {idx} ({b['tip']}): {b['seviye_fiyat']:.2f} TL ({b['temas_sayisi']} temas, kırılmamış)",
                'tip': 'direnc'
            })
            satirlar.append({'metin': f"   Temas noktaları: {', '.join(nokta_metinleri)}", 'tip': 'direnc'})

        for idx, b in enumerate(destek_aktif[:2], start=1):
            nokta_metinleri = [
                f"{pd.Timestamp(t).strftime('%d.%m.%Y')}@{f:.2f}"
                for t, f in b['noktalar']
            ]
            satirlar.append({
                'metin': f"📍 Destek Bölgesi {idx} ({b['tip']}): {b['seviye_fiyat']:.2f} TL ({b['temas_sayisi']} temas, kırılmamış)",
                'tip': 'destek'
            })
            satirlar.append({'metin': f"   Temas noktaları: {', '.join(nokta_metinleri)}", 'tip': 'destek'})

    if son.get('asiri_genisleme_bayragi') == 1:
        satirlar.append({
            'metin': f"⚠️ Aşırı genişleme: son 21 günde %{son.get('son_21_gun_getiri_yuzde', 0):.1f} hareket - bu hissenin normalinin ÇOK üstünde, düzeltme riski artmış olabilir",
            'tip': 'normal'
        })

    if son.get('yakin_bogaFVG_var') == 1:
        satirlar.append({'metin': "ℹ️ Yakın zamanda doldurulmamış bir Fair Value Gap (FVG) var", 'tip': 'normal'})

    return satirlar


def analiz_bilesenleri(sembol, logla=True):
    """Tüm analiz verisini bir sözlük olarak üretir. sorgula() bunu
    Telegram formatına çevirir, PDF modülü kendi düzenini kurar."""

    durum = durumu_oku()
    if durum is None:
        return {'hata': "⚠️ Henüz hiç model eğitilmedi. Önce 'Egit veya Ilerlet' workflow'unu çalıştır."}
    if not os.path.exists('guncel_veri.parquet'):
        return {'hata': "⚠️ guncel_veri.parquet bulunamadı. Önce 'Egit veya Ilerlet' workflow'unu çalıştır."}

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi'])
    guncel_veri = pd.read_parquet('guncel_veri.parquet')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    hisse_verisi = guncel_veri[guncel_veri['sembol'] == sembol.upper()].sort_values('tarih')
    if hisse_verisi.empty:
        return {'hata': f"⚠️ {sembol} için veri bulunamadı. Sembolü kontrol et."}

    son = hisse_verisi.iloc[-1]
    guncel_fiyat = float(son['Close'])
    trend_yonu = son.get('trend_yonu', 0)

    if pd.notna(trend_yonu) and int(trend_yonu) == -1:
        sonuc = {
            'hata': None, 'veto': True, 'sembol': sembol.upper(),
            'tarih': egitim_tarihi.date(), 'guncel_fiyat': guncel_fiyat,
            'shap_olumsuz': None,
        }
        try:
            eksik_kolon_veto = [k for k in OZELLIK_KOLONLARI if pd.isna(son.get(k))]
            if not eksik_kolon_veto:
                modeller_veto = modelleri_yukle()
                if modeller_veto.get('genel_siniflandirma') is not None:
                    X_veto = pd.DataFrame([son[OZELLIK_KOLONLARI].to_dict()]).astype(float)
                    _, olumsuz = shap_aciklama_uret(modeller_veto['genel_siniflandirma'], X_veto)
                    sonuc['shap_olumsuz'] = olumsuz
        except Exception:
            pass
        if logla:
            sorgu_logla(egitim_tarihi, sembol, detay={'veto': 1})
        return sonuc

    eksik_kolon = [k for k in OZELLIK_KOLONLARI if pd.isna(son.get(k))]
    if eksik_kolon:
        return {'hata': f"⚠️ {sembol} için eksik veri var: {eksik_kolon}"}

    X = pd.DataFrame([son[OZELLIK_KOLONLARI].to_dict()]).astype(float)
    modeller = modelleri_yukle()

    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        return {'hata': f"⚠️ {sembol} için model bulunamadı, önce eğitim yapılmalı."}

    genel_olasilik = float(modeller['genel_siniflandirma'].predict_proba(X)[0][1])
    genel_getiri_yuzde = abs(float(modeller['genel_regresyon'].predict(X)[0]))
    genel_hedef = guncel_fiyat * (1 + genel_getiri_yuzde / 100)
    atr = float(son.get('atr', guncel_fiyat * 0.02))
    genel_stop = guncel_fiyat - 1 * atr

    bolgeler = None
    direnc_uyarisi = None
    try:
        bolgeler = bolgeleri_bul(hisse_verisi)
        direnc_aktif = bolgeler['direnc_bolgeleri']

        for b in direnc_aktif:
            yakinlik_yuzde = abs(guncel_fiyat - b['seviye_fiyat']) / b['seviye_fiyat'] * 100
            if yakinlik_yuzde <= 1.5:
                direnc_uyarisi = (
                    f"⚠️ Fiyat aktif bir direnç bölgesine ({b['seviye_fiyat']:.2f} TL, "
                    f"{b['temas_sayisi']} temas) ÇOK YAKIN - bu seviyeyi aşamazsa işlem riskli olabilir."
                )
                break

        aradaki_direncler = [
            b for b in direnc_aktif
            if guncel_fiyat < b['seviye_fiyat'] < genel_hedef
        ]
        if aradaki_direncler:
            en_yakin_direnc = min(aradaki_direncler, key=lambda b: b['seviye_fiyat'])
            genel_hedef = en_yakin_direnc['seviye_fiyat'] * 0.995
            ek = f"ℹ️ Hedef, aradaki direnç bölgesine ({en_yakin_direnc['seviye_fiyat']:.2f} TL) göre sınırlandırıldı."
            direnc_uyarisi = (direnc_uyarisi + " " + ek) if direnc_uyarisi else ek
    except Exception as e:
        print(f"  ⚠️ Bölge tespiti başarısız: {e}")

    baglam = bağlam_satirlarini_olustur(son, bolgeler)

    giris_fiyat = son.get('son_yukari_giris_fiyat')
    swing_baslangic = son.get('son_yukari_swing_baslangic')
    stop_ref = son.get('son_pivot_low_fiyat')

    fib_hesaplanabilir = (
        pd.notna(giris_fiyat) and pd.notna(swing_baslangic) and
        pd.notna(stop_ref) and stop_ref < guncel_fiyat and
        (giris_fiyat - swing_baslangic) > 0 and
        any(modeller.get(f'hedef{i}') is not None for i in [1, 2, 3])
    )

    fib_notu = None
    if fib_hesaplanabilir:
        hareket_kontrol = giris_fiyat - swing_baslangic
        hedef1_kontrol = giris_fiyat + hareket_kontrol * (1.272 - 1)
        if hedef1_kontrol <= guncel_fiyat:
            fib_hesaplanabilir = False
            fib_notu = ("ℹ️ Önceki BOS referansı fiyatın gerisinde kaldı (hedefler zaten geçilmiş) - "
                        "yeni bir Fibonacci hedefi için yeni bir sinyal bekleniyor.")
            baglam.append({'metin': fib_notu, 'tip': 'normal'})

    hedef_mesafe = genel_hedef - guncel_fiyat
    stop_mesafe = guncel_fiyat - genel_stop
    rr_orani = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0

    olumlu, olumsuz = shap_aciklama_uret(modeller['genel_siniflandirma'], X)

    log_detay = {
        'genel_olasilik': round(genel_olasilik, 3),
        'genel_hedef': round(genel_hedef, 2),
        'guncel_fiyat': guncel_fiyat,
        'stop_fiyat': genel_stop,
    }

    fib_hedefler = None
    stop_fib = None
    if fib_hesaplanabilir:
        hareket = giris_fiyat - swing_baslangic
        stop_fib = float(stop_ref)
        stop_mesafe_fib = guncel_fiyat - stop_fib
        fib_hedefler = []
        for hedef_no, oran in FIB_ORANLARI.items():
            model_h = modeller.get(f'hedef{hedef_no}')
            hedef_fiyat = giris_fiyat + hareket * (oran - 1)
            hedef_mesafe_fib = hedef_fiyat - guncel_fiyat
            rr_fib = hedef_mesafe_fib / stop_mesafe_fib if stop_mesafe_fib > 0 else 0

            if model_h is not None:
                olasilik_fib = float(model_h.predict_proba(X)[0][1])
                log_detay[f'hedef{hedef_no}_olasilik'] = round(olasilik_fib, 3)
            else:
                olasilik_fib = None
                log_detay[f'hedef{hedef_no}_olasilik'] = None

            fib_hedefler.append({
                'hedef_no': hedef_no, 'oran': oran, 'fiyat': hedef_fiyat,
                'olasilik': olasilik_fib, 'rr': rr_fib,
            })
            log_detay[f'hedef{hedef_no}_fiyat'] = round(hedef_fiyat, 2)

    if logla:
        sorgu_logla(egitim_tarihi, sembol, detay=log_detay)

    return {
        'hata': None, 'veto': False, 'sembol': sembol.upper(),
        'tarih': egitim_tarihi.date(),
        'baglam': baglam,
        'olasilik': genel_olasilik,
        'beklenen_hareket': genel_getiri_yuzde,
        'guncel_fiyat': guncel_fiyat,
        'hedef': genel_hedef,
        'stop': genel_stop,
        'rr': rr_orani,
        'direnc_uyarisi': direnc_uyarisi,
        'shap_olumlu': olumlu,
        'shap_olumsuz': olumsuz,
        'fib_hedefler': fib_hedefler,
        'stop_fib': stop_fib,
    }


def sorgula(sembol, logla=True):
    """Telegram için tam metin mesajı üretir (eski format, değişmedi)."""
    veri = analiz_bilesenleri(sembol, logla=logla)

    if veri.get('hata'):
        return veri['hata']

    if veri['veto']:
        mesaj = (
            f"⚠️ <b>{veri['sembol']} — LONG İÇİN RİSKLİ</b> ({veri['tarih']} durumu)\n\n"
            f"Trend yönü şu an AŞAĞI. Sistem sadece LONG fırsatlar önerir — "
            f"bu hissede şu an düşüş yapısı hâkim olduğu için LONG pozisyon "
            f"açmak riskli olabilir.\n\n🚫 Hedef/stop önerisi verilmiyor.\n"
        )
        if veri['shap_olumsuz'] is not None and len(veri['shap_olumsuz']) > 0:
            mesaj += "\n🔍 Riski artıran başlıca etkenler:\n"
            for ozellik, deger in veri['shap_olumsuz'].items():
                mesaj += f"  {ozellik} ({deger:+.2f})\n"
        mesaj += "\n⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
        return mesaj

    baglam_metni = "\n".join(s['metin'] for s in veri['baglam']) if veri['baglam'] else "Belirgin ek yapısal bağlam yok"
    rr_uyarisi = "\n⚠️ R/R oranı düşük (1:1.5 altı)." if veri['rr'] < 1.5 else ""
    direnc_uyarisi_metni = f"\n{veri['direnc_uyarisi']}" if veri['direnc_uyarisi'] else ""

    mesaj = (
        f"🔮 <b>{veri['sembol']} LONG Tahmin</b> ({veri['tarih']} durumu)\n\n"
        f"📊 Bağlam:\n{baglam_metni}\n\n"
        f"Başarı Olasılığı: %{veri['olasilik']*100:.0f}\n"
        f"Beklenen Hareket: %{veri['beklenen_hareket']:.1f}\n\n"
        f"💰 Güncel: {veri['guncel_fiyat']:.2f} TL\n"
        f"🎯 Hedef: {veri['hedef']:.2f} TL\n"
        f"🛑 Stop: {veri['stop']:.2f} TL (ATR bazlı)\n"
        f"⚖️ R/R: 1:{veri['rr']:.2f}{rr_uyarisi}{direnc_uyarisi_metni}\n"
    )

    if veri['shap_olumlu'] is not None:
        if len(veri['shap_olumlu']) > 0:
            mesaj += "\n🔍 Bu tahmini destekleyen etkenler:\n"
            for ozellik, deger in veri['shap_olumlu'].items():
                mesaj += f"  {ozellik} ({deger:+.2f})\n"
        if len(veri['shap_olumsuz']) > 0:
            mesaj += "\n⚠️ Güveni azaltan etkenler:\n"
            for ozellik, deger in veri['shap_olumsuz'].items():
                mesaj += f"  {ozellik} ({deger:+.2f})\n"

    if veri['fib_hedefler']:
        satirlar = ["\n📐 <b>Fibonacci Kademeli Hedefler</b> (yapısal swing bazlı):"]
        for f in veri['fib_hedefler']:
            olasilik_metni = f"%{f['olasilik']*100:.0f}" if f['olasilik'] is not None else "yetersiz veri"
            satirlar.append(
                f"  Hedef {f['hedef_no']} (1:{f['oran']}): {f['fiyat']:.2f} TL | "
                f"Olasılık: {olasilik_metni} | R/R: 1:{f['rr']:.2f}"
            )
        satirlar.append(f"  Yapısal Stop: {veri['stop_fib']:.2f} TL (son pivot)")
        mesaj += "\n" + "\n".join(satirlar)

    mesaj += "\n\n⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."
    return mesaj


if __name__ == "__main__":
    sembol = os.environ.get("SORGU_SEMBOL", "TUPRS")
    mesaj = sorgula(sembol)
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
