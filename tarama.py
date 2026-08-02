"""
TARAMA.PY — Tüm BIST100 Hisseleri İçin Toplu Giriş Taraması
==============================================================
guncel_veri.csv içindeki (modelin HEDEF_TARIH'e kadarki veriyle
eğitildiği) TÜM hisseleri tek tek değerlendirir ve modelin
"girilebilir" bulduğu LONG pozisyonları TEK bir Telegram mesajında
özetler.

Kullanım akışı:
  1) "Egit veya Ilerlet" workflow'unu hedef_tarih = 2024-12-31 ile
     çalıştır -> model sadece o tarihe kadarki veriyle eğitilir.
  2) "Toplu Tarama" workflow'unu çalıştır -> 2024-12-31 itibarıyla
     hangi hisselere LONG girilebileceğini tek mesajda alırsın.

Bu, sorgu.py'deki tek-sembol sorgusunun (SORGU_SEMBOL) aksine,
guncel_veri.csv'deki TÜM sembolleri otomatik tarar.
"""

import os
import pandas as pd

from telegram_bildirim import telegram_mesaj_gonder
from durum import durumu_oku
from model_egit import modelleri_yukle
from gunluk_ozellik_seti import OZELLIK_KOLONLARI
from bolge_tespiti import bolgeleri_bul
from sorgu import _direnc_destek_uygula

ESIK_OLASILIK = float(os.environ.get("TARAMA_ESIK_OLASILIK", "0.55"))
TELEGRAM_KARAKTER_LIMITI = 3500  # Telegram sınırı 4096 - güvenlik payı bırakıldı


def _hisseyi_degerlendir(sembol, hisse_verisi, modeller):
    """Tek bir hisse için hızlı giriş uygunluğu değerlendirmesi.
    Uygun değilse (veto, eksik veri, eşik altı olasılık) None döner."""
    if hisse_verisi.empty:
        return None

    son = hisse_verisi.iloc[-1]
    guncel_fiyat = float(son['Close'])

    # VETO: trend aşağı ise hiç değerlendirme
    trend_yonu = son.get('trend_yonu', 0)
    if pd.notna(trend_yonu) and int(trend_yonu) == -1:
        return None

    eksik_kolon = [k for k in OZELLIK_KOLONLARI if pd.isna(son.get(k))]
    if eksik_kolon:
        return None

    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        return None

    X = pd.DataFrame([son[OZELLIK_KOLONLARI].to_dict()]).astype(float)
    genel_olasilik = float(modeller['genel_siniflandirma'].predict_proba(X)[0][1])
    if genel_olasilik < ESIK_OLASILIK:
        return None

    genel_getiri_yuzde = abs(float(modeller['genel_regresyon'].predict(X)[0]))
    genel_hedef = guncel_fiyat * (1 + genel_getiri_yuzde / 100)
    atr = float(son.get('atr', guncel_fiyat * 0.02))
    genel_stop = guncel_fiyat - 1 * atr

    bolge_hatasi = None
    try:
        bolgeler = bolgeleri_bul(hisse_verisi)
        genel_hedef, genel_stop, _, _, _ = _direnc_destek_uygula(
            guncel_fiyat, genel_hedef, genel_stop, bolgeler
        )
    except Exception as e:
        bolge_hatasi = str(e)
        print(f"  ⚠️ {sembol}: Bölge tespiti başarısız: {e}")

    hedef_mesafe = genel_hedef - guncel_fiyat
    stop_mesafe = guncel_fiyat - genel_stop
    rr_orani = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0

    return {
        'sembol': sembol,
        'olasilik': genel_olasilik,
        'beklenen_getiri': genel_getiri_yuzde,
        'guncel_fiyat': guncel_fiyat,
        'hedef': genel_hedef,
        'stop': genel_stop,
        'rr': rr_orani,
        'bolge_hatasi': bolge_hatasi,
    }


def tarama_yap():
    durum = durumu_oku()
    if durum is None:
        return ["⚠️ Henüz hiç model eğitilmedi. Önce 'Egit veya Ilerlet' workflow'unu çalıştır."]
    if not os.path.exists('guncel_veri.csv'):
        return ["⚠️ guncel_veri.csv bulunamadı. Önce 'Egit veya Ilerlet' workflow'unu çalıştır."]

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi'])
    guncel_veri = pd.read_csv('guncel_veri.csv')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    modeller = modelleri_yukle()
    sonuclar = []
    hatali_semboller = []

    for sembol, grup in guncel_veri.groupby('sembol'):
        grup = grup.sort_values('tarih')
        try:
            sonuc = _hisseyi_degerlendir(sembol, grup, modeller)
        except Exception as e:
            print(f"  ⚠️ {sembol} değerlendirilemedi: {e}")
            hatali_semboller.append(sembol)
            continue
        if sonuc:
            sonuclar.append(sonuc)

    sonuclar.sort(key=lambda s: s['olasilik'], reverse=True)

    bolge_hatali_semboller = [s['sembol'] for s in sonuclar if s.get('bolge_hatasi')]

    baslik = (
        f"📋 <b>Toplu Tarama Sonucu</b> ({egitim_tarihi.date()} durumu)\n"
        f"Taranan hisse: {guncel_veri['sembol'].nunique()} | "
        f"Eşik: başarı olasılığı ≥ %{ESIK_OLASILIK*100:.0f}\n\n"
    )

    if not sonuclar:
        gövde = "Bu eşiği geçen LONG fırsatı bulunamadı."
    else:
        satirlar = [
            f"• <b>{s['sembol']}</b>: %{s['olasilik']*100:.0f} olasılık | "
            f"Güncel {s['guncel_fiyat']:.2f} → Hedef {s['hedef']:.2f} "
            f"(Stop {s['stop']:.2f}) | R/R 1:{s['rr']:.2f}"
            + (" ⚠️ bölge tespiti hatalı, kırpma uygulanmadı" if s.get('bolge_hatasi') else "")
            for s in sonuclar
        ]
        gövde = "\n".join(satirlar)

    alt_notlar = f"\n\n(Eşiği geçen toplam: {len(sonuclar)} hisse)"
    if hatali_semboller:
        alt_notlar += f"\n⚠️ Değerlendirilemeyen hisseler: {', '.join(hatali_semboller)}"
    if bolge_hatali_semboller:
        alt_notlar += f"\n⚠️ Bölge tespiti hatalı hisseler: {', '.join(bolge_hatali_semboller)}"
    alt_notlar += "\n\n⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir."

    tam_mesaj = baslik + gövde + alt_notlar

    # TELEGRAM'IN 4096 KARAKTER SINIRI İÇİN: mesaj çok uzunsa satır satır
    # birden fazla mesaja böl (veri kaybı OLMASIN diye - önceden ilk 25
    # ile sınırlıydı, artık HİÇBİR sonuç kesilmiyor).
    if len(tam_mesaj) <= TELEGRAM_KARAKTER_LIMITI:
        return [tam_mesaj]

    parcalar = []
    mevcut = baslik
    for satir in gövde.split("\n"):
        if len(mevcut) + len(satir) + 1 > TELEGRAM_KARAKTER_LIMITI:
            parcalar.append(mevcut)
            mevcut = ""
        mevcut += satir + "\n"
    mevcut += alt_notlar
    parcalar.append(mevcut)
    return parcalar


if __name__ == "__main__":
    mesajlar = tarama_yap()
    for parca in mesajlar:
        print(parca)
        print("---")
        telegram_mesaj_gonder(parca)
