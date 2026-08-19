"""
POZISYONLAR.PY
================
Açık pozisyonları (sinyal verilip henüz sonuçlanmamış hisseleri) takip eder.
Bir hisse için pozisyon açıkken, o hisse tekrar taranmaz/sorgulanmaz.

KURAL:
- HEDEF: gün içi en yüksek fiyat (High) hedefe değerse yeterli.
- STOP: sadece günün KAPANIŞ fiyatı (Close) stop seviyesinin altındaysa
  tetiklenir - gün içi bir düşüş (Low) tek başına yeterli değil, kapanışta
  da o seviyenin altında kalması gerekiyor.
"""

import os
import json
import pandas as pd

POZISYON_DOSYASI = 'acik_pozisyonlar.json'
GECMIS_DOSYASI = 'pozisyon_gecmisi.csv'
MAX_GUN = 10  # bu kadar günde sonuçlanmazsa zorla kapat


def pozisyonlari_oku():
    if not os.path.exists(POZISYON_DOSYASI):
        return {}
    with open(POZISYON_DOSYASI, 'r', encoding='utf-8') as f:
        return json.load(f)


def pozisyonlari_kaydet(pozisyonlar):
    with open(POZISYON_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(pozisyonlar, f, indent=2, ensure_ascii=False, default=str)


def pozisyon_ac(sembol, giris_tarihi, giris_fiyat, hedef, stop, olasilik=None):
    pozisyonlar = pozisyonlari_oku()
    pozisyonlar[sembol] = {
        'giris_tarihi': str(giris_tarihi),
        'giris_fiyat': float(giris_fiyat),
        'hedef': float(hedef),
        'stop': float(stop),
        'olasilik': float(olasilik) if olasilik is not None else None,
    }
    pozisyonlari_kaydet(pozisyonlar)
    print(f"  📌 {sembol} pozisyon açıldı: {giris_fiyat:.2f} -> hedef {hedef:.2f} / stop {stop:.2f}")


def sonucu_gecmise_yaz(sembol, bilgi, sonuc, cikis_fiyat, cikis_tarihi, getiri_yuzde):
    yeni_kayit = pd.DataFrame([{
        'sembol': sembol,
        'giris_tarihi': bilgi['giris_tarihi'],
        'giris_fiyat': bilgi['giris_fiyat'],
        'cikis_tarihi': str(cikis_tarihi),
        'cikis_fiyat': cikis_fiyat,
        'hedef': bilgi['hedef'],
        'stop': bilgi['stop'],
        'sonuc': sonuc,
        'getiri_yuzde': getiri_yuzde,
        'olasilik': bilgi.get('olasilik'),
    }])
    if os.path.exists(GECMIS_DOSYASI):
        eski = pd.read_csv(GECMIS_DOSYASI)
        birlesik = pd.concat([eski, yeni_kayit], ignore_index=True)
    else:
        birlesik = yeni_kayit
    birlesik.to_csv(GECMIS_DOSYASI, index=False)


def pozisyonlari_kontrol_et(guncel_veri):
    """
    Açık pozisyonları güncel veriyle kontrol eder. Hedefe ulaşanları
    (gün içi High) veya kapanışta stop'un altına düşenleri (Close) ya da
    süresi dolanları kapatır. Kapanan hisselerin Telegram mesajlarını
    (liste hâlinde) döndürür.
    """
    pozisyonlar = pozisyonlari_oku()
    if not pozisyonlar:
        return []

    kapanan_mesajlari = []
    guncellenmis_pozisyonlar = dict(pozisyonlar)

    for sembol, bilgi in pozisyonlar.items():
        grup = guncel_veri[guncel_veri['sembol'] == sembol].sort_values('tarih')
        if grup.empty:
            continue

        giris_tarihi = pd.Timestamp(bilgi['giris_tarihi'])
        sonraki_gunler = grup[grup['tarih'] > giris_tarihi]
        if sonraki_gunler.empty:
            continue

        hedef = bilgi['hedef']
        stop = bilgi['stop']
        giris_fiyat = bilgi['giris_fiyat']
        kapandi = False

        for _, gun in sonraki_gunler.iterrows():
            # HEDEF: gün içi en yüksek fiyat yeterli
            if gun['High'] >= hedef:
                getiri = (hedef / giris_fiyat - 1) * 100
                sonucu_gecmise_yaz(sembol, bilgi, 'HEDEF', hedef, gun['tarih'].date(), getiri)
                kapanan_mesajlari.append(
                    f"🟢 <b>{sembol}</b> — HEDEFE ULAŞTI ({getiri:+.2f}%)\n"
                    f"   Giriş: {giris_fiyat:.2f} → Çıkış: {hedef:.2f}"
                )
                del guncellenmis_pozisyonlar[sembol]
                kapandi = True
                break

            # STOP: sadece gün KAPANIŞI stop'un altındaysa tetiklenir
            if gun['Close'] <= stop:
                cikis_fiyat = float(gun['Close'])
                getiri = (cikis_fiyat / giris_fiyat - 1) * 100
                sonucu_gecmise_yaz(sembol, bilgi, 'STOP', cikis_fiyat, gun['tarih'].date(), getiri)
                kapanan_mesajlari.append(
                    f"🔴 <b>{sembol}</b> — STOP oldu, kapanış onaylı ({getiri:+.2f}%)\n"
                    f"   Giriş: {giris_fiyat:.2f} → Çıkış: {cikis_fiyat:.2f}"
                )
                del guncellenmis_pozisyonlar[sembol]
                kapandi = True
                break

        if not kapandi:
            son_tarih = sonraki_gunler['tarih'].max()
            gecen_gun = (son_tarih - giris_tarihi).days
            if gecen_gun >= MAX_GUN:
                son_fiyat = float(sonraki_gunler.iloc[-1]['Close'])
                getiri = (son_fiyat / giris_fiyat - 1) * 100
                sonucu_gecmise_yaz(sembol, bilgi, 'ZAMAN_ASIMI', son_fiyat, son_tarih.date(), getiri)
                kapanan_mesajlari.append(
                    f"⏱️ <b>{sembol}</b> — Süre doldu, kapatıldı ({getiri:+.2f}%)\n"
                    f"   Giriş: {giris_fiyat:.2f} → Çıkış: {son_fiyat:.2f}"
                )
                del guncellenmis_pozisyonlar[sembol]

    pozisyonlari_kaydet(guncellenmis_pozisyonlar)
    return kapanan_mesajlari


def acik_semboller():
    return set(pozisyonlari_oku().keys())
