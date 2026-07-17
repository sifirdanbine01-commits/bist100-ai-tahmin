"""
GÜNLÜK ÖZELLİK SETİ OLUŞTURUCU (v2 — Trend Çizgisi + Fibonacci Kademeli Hedef)
================================================================================
Her hissenin HER GÜNÜ için:
  - Teknik göstergeler
  - Yapısal sinyal durumu (BOS/CHoCH, trend_yonu)
  - Trend çizgisi durumu (direnç/destek, kırılım bilgisi)
  - Son YUKARI swing'in fiyatları (Fibonacci hedef hesaplaması için)
  - İKİ AYRI ETİKET SETİ:
      1) Genel regresyon/sınıflandırma etiketi (yapısal referans yokken
         fallback olarak kullanılır - eski sistemle aynı)
      2) Fibonacci uzantı hedeflerine (1.272/1.618/2.0) göre ÜÇLÜ
         BARİYER etiketleri (hedef1/2/3_basarili) - yapısal/çizgi
         modunda kullanılır
"""

import pandas as pd
import numpy as np

from market_structure import market_structure_tespit_et
from gostergeler import gostergeleri_ekle
from trend_cizgisi import trend_cizgilerini_hesapla

TAKIP_GUN = 10          # genel mod etiketi için (eski sistem)
BASARI_ESIGI = 0.03
MAX_GUN_HEDEF = 40       # Fibonacci hedefleri için üçlü bariyer süresi
FIB_ORANLARI = {1: 1.272, 2: 1.618, 3: 2.0}


def hisse_icin_gunluk_ozellik_seti(sembol, df, takip_gun=TAKIP_GUN, basari_esigi=BASARI_ESIGI):
    df_g = gostergeleri_ekle(df)
    ms_df = market_structure_tespit_et(df_g)
    df_g = df_g.join(ms_df[['pivot_high', 'pivot_low', 'swing_tip',
                             'yapi_olay', 'trend_yonu', 'son_pivot_low_fiyat']])
    df_g = trend_cizgilerini_hesapla(df_g)

    n = len(df_g)
    closes = df_g['Close'].values
    lows = df_g['Low'].values
    yapi_olaylari = df_g['yapi_olay'].values

    # ---- Yapısal (BOS) takip: yön, geçerlilik, gün farkı ----
    son_bos_gun_index = np.full(n, -1)
    son_bos_yonu = np.zeros(n)
    son_bos_gecerli = np.zeros(n)

    # ---- Son YUKARI swing referansı (Fibonacci hedefleri için) ----
    # BOS_YUKARI oluştuğunda: giriş fiyatı = o günün kapanışı,
    # swing başlangıcı = ondan önceki en yakın pivot_low fiyatı.
    son_yukari_giris_fiyat = np.full(n, np.nan)
    son_yukari_swing_baslangic = np.full(n, np.nan)

    aktif_bos_index = None
    aktif_bos_yonu = 0
    guncel_yukari_giris = np.nan
    guncel_yukari_baslangic = np.nan

    for i in range(n):
        olay = yapi_olaylari[i]
        if olay == 'BOS_YUKARI':
            aktif_bos_index = i
            aktif_bos_yonu = 1
            guncel_yukari_giris = closes[i]
            onceki_lowlar = df_g['Low'][max(0, i - 60):i][df_g['pivot_low'][max(0, i - 60):i]]
            guncel_yukari_baslangic = onceki_lowlar.iloc[-1] if len(onceki_lowlar) > 0 else np.nan
        elif olay == 'BOS_ASAGI':
            aktif_bos_index = i
            aktif_bos_yonu = -1
        elif olay == 'CHOCH_YUKARI':
            if aktif_bos_yonu == -1:
                aktif_bos_index = None
                aktif_bos_yonu = 0
            aktif_bos_index = i
            aktif_bos_yonu = 0
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

        son_yukari_giris_fiyat[i] = guncel_yukari_giris
        son_yukari_swing_baslangic[i] = guncel_yukari_baslangic

    df_g['son_bos_gun_farki'] = [
        (i - son_bos_gun_index[i]) if son_bos_gun_index[i] >= 0 else -1
        for i in range(n)
    ]
    df_g['son_bos_yonu'] = son_bos_yonu
    df_g['son_bos_gecerli'] = son_bos_gecerli
    df_g['son_yukari_giris_fiyat'] = son_yukari_giris_fiyat
    df_g['son_yukari_swing_baslangic'] = son_yukari_swing_baslangic
    df_g['sembol'] = sembol

    # ============================================================
    # ETİKET SETİ 1: Genel mod (eski sistem, fallback için)
    # ============================================================
    basarili = np.full(n, np.nan)
    getiri_yuzde = np.full(n, np.nan)
    for i in range(n - takip_gun):
        giris = closes[i]
        takip = closes[i + 1: i + takip_gun + 1]
        yon_varsayim = son_bos_yonu[i] if son_bos_yonu[i] != 0 else 1
        if yon_varsayim == 1:
            getiri = (takip.max() - giris) / giris
        else:
            getiri = (giris - takip.min()) / giris
        getiri_yuzde[i] = getiri * 100
        basarili[i] = int(getiri >= basari_esigi)
    df_g['basarili'] = basarili
    df_g['getiri_yuzde'] = getiri_yuzde

    # ============================================================
    # ETİKET SETİ 2: Fibonacci kademeli hedef (üçlü bariyer)
    # Sadece geçerli bir "son yukarı swing" varsa hesaplanır.
    # ============================================================
    for hedef_no, oran in FIB_ORANLARI.items():
        df_g[f'hedef{hedef_no}_basarili'] = np.nan

    for i in range(n - 1):
        giris = son_yukari_giris_fiyat[i]
        baslangic = son_yukari_swing_baslangic[i]
        stop_ref = df_g['son_pivot_low_fiyat'].iloc[i]

        if pd.isna(giris) or pd.isna(baslangic) or pd.isna(stop_ref):
            continue
        if stop_ref >= closes[i]:
            continue  # anlamsız stop (fiyatın üstünde), atla

        hareket = giris - baslangic
        if hareket <= 0:
            continue

        bitis_idx = min(i + MAX_GUN_HEDEF, n - 1)
        if bitis_idx <= i:
            continue
        takip_high = df_g['High'].values[i + 1: bitis_idx + 1]
        takip_low = lows[i + 1: bitis_idx + 1]
        if len(takip_high) == 0:
            continue

        for hedef_no, oran in FIB_ORANLARI.items():
            hedef_fiyat = giris + hareket * (oran - 1)
            # gün gün ilerleyip önce hedefe mi stop'a mı dokunulmuş bak
            sonuc = None
            for g in range(len(takip_high)):
                if takip_low[g] <= stop_ref:
                    sonuc = 0
                    break
                if takip_high[g] >= hedef_fiyat:
                    sonuc = 1
                    break
            if sonuc is None:
                sonuc = 0  # zaman aşımı = başarısız sayılır
            df_g.loc[df_g.index[i], f'hedef{hedef_no}_basarili'] = sonuc

    return df_g


OZELLIK_KOLONLARI = [
    'rsi_14', 'macd_hist', 'adx', 'hacim_orani', 'bb_genislik',
    'stoch_k', 'fiyat_ma200_ustu', 'ema_kesisim_yukari',
    'son_bos_gun_farki', 'son_bos_yonu', 'son_bos_gecerli',
    'trend_yonu', 'direnc_mesafe_yuzde', 'direnc_gucu', 'direnc_kac_gun_otesinde',
    'destek_mesafe_yuzde', 'destek_gucu', 'destek_kac_gun_altinda',
    'cizgi_kirildi_choch_bekleniyor', 'cizgi_de_onayladi',
]

FIB_OZELLIK_KOLONLARI = OZELLIK_KOLONLARI  # aynı özellik seti, farklı etiketle eğitilecek


def tum_hisseler_icin_gunluk_ozellik_seti(veri_sozlugu):
    tum_df = []
    for sembol, df in veri_sozlugu.items():
        try:
            g = hisse_icin_gunluk_ozellik_seti(sembol, df)
            tum_df.append(g.reset_index().rename(columns={'index': 'tarih', 'Date': 'tarih'}))
        except Exception as e:
            print(f"  ⚠️ {sembol} için özellik hesaplanamadı: {e}")
    birlesik = pd.concat(tum_df, ignore_index=True)
    # Genel mod etiketleri için satırları at, ama Fibonacci etiketleri NaN
    # olabilir (yapısal referans yoksa) - o satırları TAMAMEN atmıyoruz,
    # sadece genel mod eğitimi için ayrı filtreleme model_egit.py'de yapılacak.
    birlesik = birlesik.dropna(subset=OZELLIK_KOLONLARI)
    birlesik['tarih'] = pd.to_datetime(birlesik['tarih'])
    return birlesik
