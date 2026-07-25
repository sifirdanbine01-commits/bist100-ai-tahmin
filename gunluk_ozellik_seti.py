"""
GÜNLÜK ÖZELLİK SETİ OLUŞTURUCU (v3 — Fitil Düzeltmeli + Genişletilmiş)
========================================================================
Her hissenin HER GÜNÜ için teknik göstergeler, yapısal sinyal durumu,
trend çizgisi, haftalık uyum, likidite avı, düzeltme derinliği,
aşırı genişleme ve FVG bilgisini birleştirir.

FİTİL DÜZELTMESİ: Hedef1/2/3 etiketlemesinde artık SADECE KAPANIŞ 
fiyatı sayılıyor (High/Low fitilleri tetikleyici değil).
"""

import pandas as pd
import numpy as np

from market_structure import market_structure_tespit_et
from gostergeler import gostergeleri_ekle
from trend_cizgisi import trend_cizgilerini_hesapla
from asiri_genisleme import asiri_genisleme_ekle
from fvg import fvg_ekle

TAKIP_GUN = 10
BASARI_ESIGI = 0.03
MAX_GUN_HEDEF = 40
FIB_ORANLARI = {1: 1.272, 2: 1.618, 3: 2.0}


def haftalik_trend_ekle(df_g):
    haftalik = df_g[['Open', 'High', 'Low', 'Close', 'Volume']].resample('W-FRI').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()

    if len(haftalik) < 10:
        df_g = df_g.copy()
        df_g['haftalik_trend_yonu'] = 0
        return df_g

    haftalik_ms = market_structure_tespit_et(haftalik)
    haftalik_trend = haftalik_ms['trend_yonu'].copy()
    haftalik_trend.index = haftalik_trend.index + pd.Timedelta(days=7)

    gunluk_tarihler = pd.DataFrame({'tarih': pd.DatetimeIndex(df_g.index).astype('datetime64[ns]')}).sort_values('tarih')
    haftalik_df = pd.DataFrame({
        'tarih': pd.DatetimeIndex(haftalik_trend.index).astype('datetime64[ns]'),
        'haftalik_trend_yonu': haftalik_trend.values
    })
    haftalik_df = haftalik_df.sort_values('tarih')

    birlesik = pd.merge_asof(gunluk_tarihler, haftalik_df, on='tarih', direction='backward')
    birlesik['haftalik_trend_yonu'] = birlesik['haftalik_trend_yonu'].fillna(0)

    df_g = df_g.copy()
    df_g['haftalik_trend_yonu'] = birlesik['haftalik_trend_yonu'].values
    return df_g


def hisse_icin_gunluk_ozellik_seti(sembol, df, takip_gun=TAKIP_GUN, basari_esigi=BASARI_ESIGI):
    df_g = gostergeleri_ekle(df)
    ms_df = market_structure_tespit_et(df_g)
    df_g = df_g.join(ms_df[['pivot_high', 'pivot_low', 'swing_tip',
                             'yapi_olay', 'trend_yonu', 'son_pivot_low_fiyat']])
    df_g = trend_cizgilerini_hesapla(df_g)
    df_g = haftalik_trend_ekle(df_g)
    df_g = asiri_genisleme_ekle(df_g)
    df_g = fvg_ekle(df_g)

    n = len(df_g)
    closes = df_g['Close'].values
    lows = df_g['Low'].values
    yapi_olaylari = df_g['yapi_olay'].values

    son_bos_gun_index = np.full(n, -1)
    son_bos_yonu = np.zeros(n)
    son_bos_gecerli = np.zeros(n)

    son_yukari_giris_fiyat = np.full(n, np.nan)
    son_yukari_swing_baslangic = np.full(n, np.nan)

    aktif_bos_index = None
    aktif_bos_yonu = 0
    guncel_yukari_giris = np.nan
    guncel_yukari_baslangic = np.nan

    aktif_A_fiyati = np.nan
    duzeltme_derinlik_yuzde = np.full(n, np.nan)
    guncel_derinlik = np.nan

    for i in range(n):
        olay = yapi_olaylari[i]
        if olay == 'CHOCH_ASAGI':
            onceki_highlar = df_g['High'][max(0, i - 60):i][df_g['pivot_high'][max(0, i - 60):i]]
            aktif_A_fiyati = onceki_highlar.iloc[-1] if len(onceki_highlar) > 0 else np.nan
        if olay == 'CHOCH_YUKARI' and pd.notna(aktif_A_fiyati) and aktif_A_fiyati > 0:
            B = closes[i]
            guncel_derinlik = (aktif_A_fiyati - B) / aktif_A_fiyati * 100
        duzeltme_derinlik_yuzde[i] = guncel_derinlik

    df_g['duzeltme_derinlik_yuzde'] = duzeltme_derinlik_yuzde

    haftalik_trend_arr = df_g['haftalik_trend_yonu'].values
    guncel_coklu_uyum = 0
    coklu_zaman_uyumu = np.zeros(n)

    SWEEP_PENCERE = 5
    likidite_avi_teyitli = np.zeros(n)
    son_pivot_low_arr = df_g['son_pivot_low_fiyat'].values
    guncel_likidite_avi = 0

    for i in range(n):
        if yapi_olaylari[i] == 'CHOCH_YUKARI':
            baslangic = max(0, i - SWEEP_PENCERE)
            referans = son_pivot_low_arr[baslangic] if baslangic < i else np.nan
            if pd.notna(referans):
                dip_oldu = any(lows[j] < referans for j in range(baslangic, i + 1))
                if dip_oldu and closes[i] > referans:
                    guncel_likidite_avi = 1
                else:
                    guncel_likidite_avi = 0
        elif yapi_olaylari[i] in ('CHOCH_ASAGI', 'BOS_ASAGI'):
            guncel_likidite_avi = 0
        likidite_avi_teyitli[i] = guncel_likidite_avi

    df_g['likidite_avi_teyitli'] = likidite_avi_teyitli

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
            guncel_coklu_uyum = 0
        elif olay == 'CHOCH_YUKARI':
            if aktif_bos_yonu == -1:
                aktif_bos_index = None
                aktif_bos_yonu = 0
            aktif_bos_index = i
            aktif_bos_yonu = 0
            guncel_coklu_uyum = 1 if haftalik_trend_arr[i] == 1 else 0
        elif olay == 'CHOCH_ASAGI':
            if aktif_bos_yonu == 1:
                aktif_bos_index = None
                aktif_bos_yonu = 0
            aktif_bos_index = i
            aktif_bos_yonu = 0
            guncel_coklu_uyum = 0

        coklu_zaman_uyumu[i] = guncel_coklu_uyum

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
    df_g['coklu_zaman_uyumu'] = coklu_zaman_uyumu
    df_g['sembol'] = sembol

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

    for hedef_no, oran in FIB_ORANLARI.items():
        df_g[f'hedef{hedef_no}_basarili'] = np.nan

    for i in range(n - 1):
        giris = son_yukari_giris_fiyat[i]
        baslangic = son_yukari_swing_baslangic[i]
        stop_ref = df_g['son_pivot_low_fiyat'].iloc[i]

        if pd.isna(giris) or pd.isna(baslangic) or pd.isna(stop_ref):
            continue
        if stop_ref >= closes[i]:
            continue

        hareket = giris - baslangic
        if hareket <= 0:
            continue

        bitis_idx = min(i + MAX_GUN_HEDEF, n - 1)
        if bitis_idx <= i:
            continue
        # ASİMETRİK KURAL: Hedef (kâr-al) için FİTİL (gün içi High) yeterli
        # sayılır - gerçek trading'de limit emri gibi çalışır, fiyat 
        # dokunur dokunmaz gerçekleşir. STOP için ise hâlâ SADECE 
        # KAPANIŞ sayılır - geçici fitil dokunuşları stop'u tetiklemez.
        takip_high = df_g['High'].values[i + 1: bitis_idx + 1]
        takip_close = closes[i + 1: bitis_idx + 1]
        if len(takip_high) == 0:
            continue

        for hedef_no, oran in FIB_ORANLARI.items():
            hedef_fiyat = giris + hareket * (oran - 1)
            sonuc = None
            for g in range(len(takip_high)):
                if takip_close[g] <= stop_ref:
                    sonuc = 0
                    break
                if takip_high[g] >= hedef_fiyat:
                    sonuc = 1
                    break
            if sonuc is None:
                sonuc = 0
            df_g.loc[df_g.index[i], f'hedef{hedef_no}_basarili'] = sonuc

    return df_g


OZELLIK_KOLONLARI = [
    'rsi_14', 'macd_hist', 'adx', 'hacim_orani', 'bb_genislik',
    'stoch_k', 'fiyat_ma200_ustu', 'ema_kesisim_yukari',
    'son_bos_gun_farki', 'son_bos_yonu', 'son_bos_gecerli',
    'trend_yonu', 'direnc_mesafe_yuzde', 'direnc_gucu', 'direnc_kac_gun_otesinde',
    'destek_mesafe_yuzde', 'destek_gucu', 'destek_kac_gun_altinda',
    'cizgi_kirildi_choch_bekleniyor', 'cizgi_de_onayladi',
    'duzeltme_derinlik_yuzde',
    'haftalik_trend_yonu', 'coklu_zaman_uyumu',
    'likidite_avi_teyitli',
    'direnc_temas_sayisi', 'direnc_basarisiz_kirilim_sayisi',
    'destek_temas_sayisi', 'destek_basarisiz_kirilim_sayisi',
    'son_21_gun_getiri_yuzde', 'asiri_genisleme_zskoru', 'asiri_genisleme_bayragi',
    'yakin_bogaFVG_var',
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
    birlesik = birlesik.dropna(subset=OZELLIK_KOLONLARI)
    birlesik['tarih'] = pd.to_datetime(birlesik['tarih'])
    return birlesik