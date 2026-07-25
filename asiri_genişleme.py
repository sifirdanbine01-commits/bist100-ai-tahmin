"""
AŞIRI GENİŞLEME (OVEREXTENSION) MODÜLÜ
=========================================
"Son N günde fiyat OLAĞANDIŞI kadar hızlı/büyük hareket etti mi"
sorusuna cevap verir. Sabit bir yüzde eşiği (örn. "%40 = aşırı")
KULLANMIYORUZ - her hissenin KENDİ TARİHSEL normaline göre ne kadar
"olağandışı" olduğunu ölçüyoruz (z-skoru mantığı), böylece model
her hissenin kendi karakterine göre öğreniyor.
"""

import numpy as np
import pandas as pd

PENCERE_GUN = 21          # "son N günde ne kadar hareket etti" ölçüm penceresi
TARIHSEL_KARSILASTIRMA_GUN = 252   # yaklaşık 1 yıl, "normal" neyse onu öğrenmek için


def asiri_genisleme_ekle(df_g):
    closes = df_g['Close'].values
    n = len(df_g)

    # Her gün için: son 21 günün getirisi (bugünden 21 gün önceye göre %)
    getiri_21_gun = np.full(n, np.nan)
    for i in range(PENCERE_GUN, n):
        getiri_21_gun[i] = (closes[i] - closes[i - PENCERE_GUN]) / closes[i - PENCERE_GUN] * 100

    getiri_serisi = pd.Series(getiri_21_gun)

    # Bu hissenin kendi tarihsel 21-günlük getiri dağılımına göre 
    # ortalama ve standart sapma (kayan pencere, sadece GEÇMİŞ veriyle,
    # lookahead olmasın diye .shift(1) ile bugünü dahil etmiyoruz)
    hareketli_ortalama = getiri_serisi.rolling(TARIHSEL_KARSILASTIRMA_GUN, min_periods=60).mean().shift(1)
    hareketli_std = getiri_serisi.rolling(TARIHSEL_KARSILASTIRMA_GUN, min_periods=60).std().shift(1)

    z_skoru = (getiri_serisi - hareketli_ortalama) / hareketli_std.replace(0, np.nan)

    df_g = df_g.copy()
    df_g['son_21_gun_getiri_yuzde'] = getiri_21_gun
    df_g['asiri_genisleme_zskoru'] = z_skoru.values
    # |z| > 2 -> bu hissenin kendi normaline göre "olağandışı" büyük hareket
    df_g['asiri_genisleme_bayragi'] = (z_skoru.abs() > 2).astype(int).values

    return df_g 
