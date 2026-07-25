"""
TREND ÇİZGİSİ MODÜLÜ
======================
Son 504 işlem günündeki LH noktalarından DİRENÇ, HL noktalarından
DESTEK çizgisi çizer (logaritmik regresyon). Kırılım SADECE KAPANIŞ
fiyatıyla sayılır (fitil sayılmaz).

YENİ: Somut fiyat seviyeleri, temas sayısı ve BAŞARISIZ KIRILIM 
SAYISI da (kullanıcının istediği gibi) takip ediliyor.
"""

import numpy as np
import pandas as pd

PENCERE_GUN = 504


def _log_regresyon_egim_kesisim(x_gunler, y_fiyatlar):
    log_y = np.log(y_fiyatlar)
    egim, kesisim = np.polyfit(x_gunler, log_y, 1)
    return egim, kesisim


def _cizgi_degeri(egim, kesisim, gun):
    return np.exp(egim * gun + kesisim)


def trend_cizgilerini_hesapla(df_g):
    n = len(df_g)
    closes = df_g['Close'].values
    highs = df_g['High'].values
    lows = df_g['Low'].values
    pivot_high_mask = df_g['pivot_high'].values
    pivot_low_mask = df_g['pivot_low'].values

    direnc_mesafe_yuzde = np.full(n, np.nan)
    direnc_gucu = np.zeros(n)
    direnc_kac_gun_otesinde = np.zeros(n)
    direnc_seviye_fiyat = np.full(n, np.nan)
    direnc_temas_sayisi = np.zeros(n)
    direnc_basarisiz_kirilim_sayisi = np.zeros(n)

    destek_mesafe_yuzde = np.full(n, np.nan)
    destek_gucu = np.zeros(n)
    destek_kac_gun_altinda = np.zeros(n)
    destek_seviye_fiyat = np.full(n, np.nan)
    destek_temas_sayisi = np.zeros(n)
    destek_basarisiz_kirilim_sayisi = np.zeros(n)

    gun_otesinde_sayaci = 0
    gun_altinda_sayaci = 0
    direnc_onceki_otesinde_mi = False
    direnc_basarisiz_sayac = 0
    destek_onceki_altinda_mi = False
    destek_basarisiz_sayac = 0

    for i in range(n):
        pencere_baslangic = max(0, i - PENCERE_GUN)

        lh_indeksler = [
            j for j in range(pencere_baslangic, i)
            if pivot_high_mask[j] and df_g['swing_tip'].iloc[j] == 'LH'
        ]
        if len(lh_indeksler) >= 2:
            x = np.array(lh_indeksler, dtype=float)
            y = highs[lh_indeksler]
            try:
                egim, kesisim = _log_regresyon_egim_kesisim(x, y)
                cizgi_deger = _cizgi_degeri(egim, kesisim, i)
                mesafe = (closes[i] - cizgi_deger) / cizgi_deger * 100
                direnc_mesafe_yuzde[i] = mesafe
                direnc_gucu[i] = 2 if len(lh_indeksler) >= 3 else 1
                direnc_seviye_fiyat[i] = cizgi_deger
                direnc_temas_sayisi[i] = len(lh_indeksler)

                simdi_otesinde = closes[i] > cizgi_deger
                if simdi_otesinde:
                    gun_otesinde_sayaci += 1
                else:
                    if direnc_onceki_otesinde_mi:
                        direnc_basarisiz_sayac += 1
                    gun_otesinde_sayaci = 0
                direnc_onceki_otesinde_mi = simdi_otesinde
                direnc_kac_gun_otesinde[i] = gun_otesinde_sayaci
                direnc_basarisiz_kirilim_sayisi[i] = direnc_basarisiz_sayac
            except (np.linalg.LinAlgError, ValueError):
                pass

        hl_indeksler = [
            j for j in range(pencere_baslangic, i)
            if pivot_low_mask[j] and df_g['swing_tip'].iloc[j] == 'HL'
        ]
        if len(hl_indeksler) >= 2:
            x = np.array(hl_indeksler, dtype=float)
            y = lows[hl_indeksler]
            try:
                egim, kesisim = _log_regresyon_egim_kesisim(x, y)
                cizgi_deger = _cizgi_degeri(egim, kesisim, i)
                mesafe = (closes[i] - cizgi_deger) / cizgi_deger * 100
                destek_mesafe_yuzde[i] = mesafe
                destek_gucu[i] = 2 if len(hl_indeksler) >= 3 else 1
                destek_seviye_fiyat[i] = cizgi_deger
                destek_temas_sayisi[i] = len(hl_indeksler)

                simdi_altinda = closes[i] < cizgi_deger
                if simdi_altinda:
                    gun_altinda_sayaci += 1
                else:
                    if destek_onceki_altinda_mi:
                        destek_basarisiz_sayac += 1
                    gun_altinda_sayaci = 0
                destek_onceki_altinda_mi = simdi_altinda
                destek_kac_gun_altinda[i] = gun_altinda_sayaci
                destek_basarisiz_kirilim_sayisi[i] = destek_basarisiz_sayac
            except (np.linalg.LinAlgError, ValueError):
                pass

    df_g = df_g.copy()
    df_g['direnc_mesafe_yuzde'] = direnc_mesafe_yuzde
    df_g['direnc_gucu'] = direnc_gucu
    df_g['direnc_kac_gun_otesinde'] = direnc_kac_gun_otesinde
    df_g['direnc_seviye_fiyat'] = direnc_seviye_fiyat
    df_g['direnc_temas_sayisi'] = direnc_temas_sayisi
    df_g['direnc_basarisiz_kirilim_sayisi'] = direnc_basarisiz_kirilim_sayisi

    df_g['destek_mesafe_yuzde'] = destek_mesafe_yuzde
    df_g['destek_gucu'] = destek_gucu
    df_g['destek_kac_gun_altinda'] = destek_kac_gun_altinda
    df_g['destek_seviye_fiyat'] = destek_seviye_fiyat
    df_g['destek_temas_sayisi'] = destek_temas_sayisi
    df_g['destek_basarisiz_kirilim_sayisi'] = destek_basarisiz_kirilim_sayisi

    trend_yonu = df_g['trend_yonu'].values
    cizgi_kirildi_choch_bekleniyor = np.zeros(n)
    cizgi_de_onayladi = np.zeros(n)
    for i in range(n):
        direnc_kirik = direnc_kac_gun_otesinde[i] > 0
        if direnc_kirik and trend_yonu[i] != 1:
            cizgi_kirildi_choch_bekleniyor[i] = 1
        if direnc_kirik and trend_yonu[i] == 1:
            cizgi_de_onayladi[i] = 1

    df_g['cizgi_kirildi_choch_bekleniyor'] = cizgi_kirildi_choch_bekleniyor
    df_g['cizgi_de_onayladi'] = cizgi_de_onayladi

    return df_g
