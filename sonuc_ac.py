"""
SONUÇ AÇIKLAMA MODÜLÜ (v2 — Hedef1/Stop Bazlı Değerlendirme)
================================================================
Daha önce /sorgu ile loglanan LONG önerilerinin gerçek sonucunu
hesaplar: "Hedef 1'e mi önce ulaşıldı, stop'a mı önce ulaşıldı?"
Risk uyarısı satırları (mod=risk_uyarisi_asagi) değerlendirilmez.
"""

import pandas as pd
import os

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'
MAX_GUN = 40


def onceki_sorgulari_degerlendir(tum_ozellik_df, yeni_hedef_tarih):
    if not os.path.exists(SORGU_GECMISI_DOSYASI):
        return None

    gecmis = pd.read_csv(SORGU_GECMISI_DOSYASI)
    gecmis['tarih'] = pd.to_datetime(gecmis['tarih'], format='mixed')

    if 'gercek_sonuc' not in gecmis.columns:
        gecmis['gercek_sonuc'] = pd.NA
        gecmis['gerceklesen_getiri'] = pd.NA

    degerlendirilenler = []

    for idx, satir in gecmis.iterrows():
        if pd.notna(satir['gercek_sonuc']):
            continue

        if satir.get('mod') == 'risk_uyarisi_asagi' or pd.isna(satir.get('hedef1_fiyat')):
            gecmis.loc[idx, 'gercek_sonuc'] = -1  # değerlendirilmez
            continue

        sorgu_tarihi = satir['tarih']
        sembol = satir['sembol']
        hedef1_fiyat = satir['hedef1_fiyat']
        stop_fiyat = satir.get('stop_fiyat')

        hisse_verisi = tum_ozellik_df[
            (tum_ozellik_df['sembol'] == sembol) &
            (tum_ozellik_df['tarih'] > sorgu_tarihi) &
            (tum_ozellik_df['tarih'] <= sorgu_tarihi + pd.Timedelta(days=MAX_GUN * 1.5))
        ].sort_values('tarih')

        if len(hisse_verisi) < MAX_GUN * 0.5:
            continue  # henüz yeterli gün geçmemiş

        sonuc = 0
        for _, gun in hisse_verisi.iterrows():
            if pd.notna(stop_fiyat) and gun['Low'] <= stop_fiyat:
                sonuc = 0
                break
            if gun['High'] >= hedef1_fiyat:
                sonuc = 1
                break

        gecmis.loc[idx, 'gercek_sonuc'] = sonuc
        giris = satir.get('guncel_fiyat', hedef1_fiyat)
        gecmis.loc[idx, 'gerceklesen_getiri'] = round((hedef1_fiyat - giris) / giris * 100, 2) if sonuc == 1 else None

        olasilik = satir.get('hedef1_olasilik')
        dogru_tahmin = (
            (pd.notna(olasilik) and olasilik >= 0.5 and sonuc == 1) or
            (pd.notna(olasilik) and olasilik < 0.5 and sonuc == 0)
        )
        olasilik_metni = f"%{olasilik*100:.0f}" if pd.notna(olasilik) else "?"
        degerlendirilenler.append(
            f"  {sembol} ({sorgu_tarihi.date()}, {satir.get('mod')}): tahmin {olasilik_metni} "
            f"→ gerçek {'✅ Hedef1' if sonuc else '❌ Stop/zaman aşımı'} "
            f"({'doğru' if dogru_tahmin else 'yanlış'} tahmin)"
        )

    gecmis.to_csv(SORGU_GECMISI_DOSYASI, index=False)

    if not degerlendirilenler:
        return None
    return "\n".join(degerlendirilenler)
