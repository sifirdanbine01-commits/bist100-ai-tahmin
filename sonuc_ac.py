"""
SONUÇ AÇIKLAMA MODÜLÜ (Fitil Düzeltmeli)
==========================================
Genel hedef/stop bazlı değerlendirme. Sadece KAPANIŞ fiyatı sayılır
(fitil sayılmaz). Veto satırları değerlendirilmez.
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

        if satir.get('veto') == 1 or pd.isna(satir.get('genel_hedef')):
            gecmis.loc[idx, 'gercek_sonuc'] = -1
            continue

        sorgu_tarihi = satir['tarih']
        sembol = satir['sembol']
        hedef_fiyat = satir['genel_hedef']
        stop_fiyat = satir.get('stop_fiyat')

        hisse_verisi = tum_ozellik_df[
            (tum_ozellik_df['sembol'] == sembol) &
            (tum_ozellik_df['tarih'] > sorgu_tarihi) &
            (tum_ozellik_df['tarih'] <= sorgu_tarihi + pd.Timedelta(days=MAX_GUN * 1.5))
        ].sort_values('tarih')

        if len(hisse_verisi) < MAX_GUN * 0.5:
            continue

        sonuc = 0
        for _, gun in hisse_verisi.iterrows():
            # ASİMETRİK KURAL: Stop -> sadece kapanış, Hedef -> fitil yeterli
            if pd.notna(stop_fiyat) and gun['Close'] <= stop_fiyat:
                sonuc = 0
                break
            if gun['High'] >= hedef_fiyat:
                sonuc = 1
                break

        gecmis.loc[idx, 'gercek_sonuc'] = sonuc
        giris = satir.get('guncel_fiyat', hedef_fiyat)
        gecmis.loc[idx, 'gerceklesen_getiri'] = round((hedef_fiyat - giris) / giris * 100, 2) if sonuc == 1 else None

        olasilik = satir.get('genel_olasilik')
        dogru_tahmin = (
            (pd.notna(olasilik) and olasilik >= 0.5 and sonuc == 1) or
            (pd.notna(olasilik) and olasilik < 0.5 and sonuc == 0)
        )
        olasilik_metni = f"%{olasilik*100:.0f}" if pd.notna(olasilik) else "?"
        degerlendirilenler.append(
            f"  {sembol} ({sorgu_tarihi.date()}): tahmin {olasilik_metni} "
            f"→ gerçek {'✅ Hedef' if sonuc else '❌ Stop/zaman aşımı'} "
            f"({'doğru' if dogru_tahmin else 'yanlış'} tahmin)"
        )

    gecmis.to_csv(SORGU_GECMISI_DOSYASI, index=False)

    if not degerlendirilenler:
        return None
    return "\n".join(degerlendirilenler)