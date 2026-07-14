"""
GÜNLÜK ÖZELLİK SETİ OLUŞTURUCU
================================
Her hissenin HER GÜNÜ için (sadece BOS anlarında değil) şu bilgiyi
tek satırda birleştirir:
  - O günkü teknik göstergeler (RSI, MACD, ADX, hacim vb.)
  - Yapısal sinyal durumu (son BOS ne zaman oldu, yönü, hâlâ geçerli mi)
  - Hisse kimliği
  - Hedef (label): N gün sonra fiyat ne kadar hareket etti

Bu, "Mod A + Mod B birleşik model" tasarımının veri katmanıdır.
"""

import pandas as pd
import numpy as np

from market_structure import market_structure_tespit_et
from gostergeler import gostergeleri_ekle

TAKIP_GUN = 10
BASARI_ESIGI = 0.03


def hisse_icin_gunluk_ozellik_seti(sembol, df, takip_gun=TAKIP_GUN, basari_esigi=BASARI_ESIGI):
    df_g = gostergeleri_ekle(df)
    ms_df = market_structure_tespit_et(df_g)
    df_g = df_g.join(ms_df[['yapi_olay', 'trend_yonu']])

    n = len(df_g)
    closes = df_g['Close'].values
    yapi_olaylari = df_g['yapi_olay'].values

    # Her gün için "son BOS'a kadar geçen gün" ve "son BOS yönü/geçerliliği"
    son_bos_gun_index = np.full(n, -1)
    son_bos_yonu = np.zeros(n)
    son_bos_gecerli = np.zeros(n)  # sonrasında ters CHoCH olmadıysa 1

    aktif_bos_index = None
    aktif_bos_yonu = 0

    for i in range(n):
        olay = yapi_olaylari[i]
        if olay == 'BOS_YUKARI':
            aktif_bos_index = i
            aktif_bos_yonu = 1
        elif olay == 'BOS_ASAGI':
            aktif_bos_index = i
            aktif_bos_yonu = -1
        elif olay == 'CHOCH_YUKARI':
            # Aşağı yönlü BOS artık geçersiz
            if aktif_bos_yonu == -1:
                aktif_bos_index = None
                aktif_bos_yonu = 0
            aktif_bos_index = i
            aktif_bos_yonu = 0  # CHoCH henüz BOS değil, ama trend döndü
        elif olay == 'CHOCH_ASAGI':
            if aktif_bos_yonu == 1:
                aktif_bos_index = None
                aktif_bos_yonu = 0
            aktif_bos_index = i
            aktif_bos_yonu = 0

        if aktif_bos_index is not None:
            son_bos_gun_index[i] = aktif_bos_index
            son_bos_yonu[i] = aktif_bos_yonu
            son_bos_gecerli[i] = 1 if aktif_bos_yonu != 0 else 0

    df_g['son_bos_gun_farki'] = [
        (i - son_bos_gun_index[i]) if son_bos_gun_index[i] >= 0 else -1
        for i in range(n)
    ]
    df_g['son_bos_yonu'] = son_bos_yonu
    df_g['son_bos_gecerli'] = son_bos_gecerli
    df_g['sembol'] = sembol

    # Hedef (label): bugünden N gün sonra en iyi hareket ne kadar oldu
    basarili = np.full(n, np.nan)
    getiri_yuzde = np.full(n, np.nan)
    for i in range(n - takip_gun):
        giris = closes[i]
        takip = closes[i + 1: i + takip_gun + 1]
        yon_varsayim = son_bos_yonu[i] if son_bos_yonu[i] != 0 else 1  # sinyal yoksa varsayılan yukarı bak
        if yon_varsayim == 1:
            getiri = (takip.max() - giris) / giris
        else:
            getiri = (giris - takip.min()) / giris
        getiri_yuzde[i] = getiri * 100
        basarili[i] = int(getiri >= basari_esigi)

    df_g['basarili'] = basarili
    df_g['getiri_yuzde'] = getiri_yuzde

    return df_g


OZELLIK_KOLONLARI = [
    'rsi_14', 'macd_hist', 'adx', 'hacim_orani', 'bb_genislik',
    'stoch_k', 'fiyat_ma200_ustu', 'ema_kesisim_yukari',
    'son_bos_gun_farki', 'son_bos_yonu', 'son_bos_gecerli',
]


def tum_hisseler_icin_gunluk_ozellik_seti(veri_sozlugu):
    tum_df = []
    for sembol, df in veri_sozlugu.items():
        try:
            g = hisse_icin_gunluk_ozellik_seti(sembol, df)
            tum_df.append(g.reset_index().rename(columns={'index': 'tarih', 'Date': 'tarih'}))
        except Exception as e:
            print(f"  ⚠️ {sembol} için özellik hesaplanamadı: {e}")
    birlesik = pd.concat(tum_df, ignore_index=True)
    birlesik = birlesik.dropna(subset=OZELLIK_KOLONLARI + ['basarili', 'getiri_yuzde'])
    birlesik['tarih'] = pd.to_datetime(birlesik['tarih'])
    return birlesik
