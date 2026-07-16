"""
SONUÇ AÇIKLAMA MODÜLÜ
=======================
Daha önce /sorgu ile yapılan LONG tahminlerinin gerçek sonucunu
hesaplar. "Risk uyarısı" olarak loglanan satırlar (mod=risk_uyarisi_asagi)
bir trade önerisi olmadığı için DEĞERLENDİRİLMEZ, atlanır.
"""

import pandas as pd
import os

SORGU_GECMISI_DOSYASI = 'sorgu_gecmisi.csv'
TAKIP_GUN = 10
BASARI_ESIGI = 0.03


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
            continue  # zaten değerlendirilmiş

        # Risk uyarısı satırları bir trade önerisi değil, değerlendirilmez
        if satir.get('mod') == 'risk_uyarisi_asagi' or pd.isna(satir['tahmin_basari_olasiligi']):
            gecmis.loc[idx, 'gercek_sonuc'] = -1  # -1: "değerlendirilmez" özel değeri
            continue

        sorgu_tarihi = satir['tarih']
        sembol = satir['sembol']

        hisse_verisi = tum_ozellik_df[
            (tum_ozellik_df['sembol'] == sembol) &
            (tum_ozellik_df['tarih'] > sorgu_tarihi) &
            (tum_ozellik_df['tarih'] <= sorgu_tarihi + pd.Timedelta(days=TAKIP_GUN * 1.5))
        ].sort_values('tarih')

        if len(hisse_verisi) < TAKIP_GUN * 0.6:
            continue  # henüz yeterli gün geçmemiş, bekle

        giris_satiri = tum_ozellik_df[
            (tum_ozellik_df['sembol'] == sembol) & (tum_ozellik_df['tarih'] == sorgu_tarihi)
        ]
        if giris_satiri.empty:
            continue
        giris_fiyat = giris_satiri.iloc[0]['Close']

        # Bu sistem artık sadece LONG önerdiği için getiri hep yukarı yönlü ölçülür
        getiri = (hisse_verisi['Close'].max() - giris_fiyat) / giris_fiyat

        basarili = int(getiri >= BASARI_ESIGI)
        gecmis.loc[idx, 'gercek_sonuc'] = basarili
        gecmis.loc[idx, 'gerceklesen_getiri'] = round(getiri * 100, 2)

        dogru_tahmin = (
            (satir['tahmin_basari_olasiligi'] >= 0.5 and basarili == 1) or
            (satir['tahmin_basari_olasiligi'] < 0.5 and basarili == 0)
        )
        degerlendirilenler.append(
            f"  {sembol} ({sorgu_tarihi.date()}): tahmin %{satir['tahmin_basari_olasiligi']*100:.0f} "
            f"→ gerçek {'✅ başarılı' if basarili else '❌ başarısız'} "
            f"({'doğru' if dogru_tahmin else 'yanlış'} tahmin)"
        )

    gecmis.to_csv(SORGU_GECMISI_DOSYASI, index=False)

    if not degerlendirilenler:
        return None
    return "\n".join(degerlendirilenler)
