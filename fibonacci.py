"""
FIBONACCI RETRACEMENT / EXTENSION MODÜLÜ
=========================================
Her BOS olayı için, o hareketin başlangıç-bitiş swing'ine göre
Fibonacci seviyelerini hesaplar ve sonraki günlerde fiyatın
hangi seviyeye dokunup dönüş yaptığını (varsa) tespit eder.
"""

import pandas as pd
import numpy as np

FIB_RETRACEMENT_SEVIYELERI = [0.382, 0.5, 0.618, 0.786]
FIB_EXTENSION_SEVIYELERI = [1.272, 1.618, 2.0]


def fib_seviyelerini_hesapla(swing_baslangic_fiyat, swing_bitis_fiyat, yon):
    """
    yon: 1 (yukarı BOS) veya -1 (aşağı BOS)
    Yukarı BOS'ta retracement, swing'in üstünden aşağı doğru çekilir.
    """
    hareket = swing_bitis_fiyat - swing_baslangic_fiyat
    seviyeler = {}
    for f in FIB_RETRACEMENT_SEVIYELERI:
        if yon == 1:
            seviyeler[f'ret_{f}'] = swing_bitis_fiyat - hareket * f
        else:
            seviyeler[f'ret_{f}'] = swing_bitis_fiyat + abs(hareket) * f

    for f in FIB_EXTENSION_SEVIYELERI:
        if yon == 1:
            seviyeler[f'ext_{f}'] = swing_bitis_fiyat + hareket * (f - 1)
        else:
            seviyeler[f'ext_{f}'] = swing_bitis_fiyat - abs(hareket) * (f - 1)
    return seviyeler


def bos_sonrasi_fib_analizi(df, ms_df, takip_gun=20, tolerans=0.01):
    """
    Her BOS olayından sonra:
    - hangi Fib seviyesine dokunuldu (varsa)
    - o seviyeden dönüş oldu mu (pozitif/negatif mumla teyit)
    - sonraki takip_gun içinde ulaşılan max extension seviyesi
    döndürür (backtest/model eğitimi için satır satır kayıt).
    """
    sonuclar = []
    closes = df['Close'].values
    highs = df['High'].values
    lows = df['Low'].values
    n = len(df)

    bos_indexleri = ms_df.index[ms_df['yapi_olay'].isin(['BOS_YUKARI', 'BOS_ASAGI'])]

    for bos_tarihi in bos_indexleri:
        i = df.index.get_loc(bos_tarihi)
        olay = ms_df.loc[bos_tarihi, 'yapi_olay']
        yon = 1 if olay == 'BOS_YUKARI' else -1

        # Swing başlangıcı: BOS'tan önceki son karşıt pivotu bul
        onceki_kesit = ms_df.iloc[max(0, i - 60):i]
        if yon == 1:
            pivotlar = onceki_kesit[onceki_kesit['pivot_low']]
            if pivotlar.empty:
                continue
            swing_baslangic_fiyat = pivotlar['Low'].iloc[-1]
        else:
            pivotlar = onceki_kesit[onceki_kesit['pivot_high']]
            if pivotlar.empty:
                continue
            swing_baslangic_fiyat = pivotlar['High'].iloc[-1]

        swing_bitis_fiyat = closes[i]
        seviyeler = fib_seviyelerini_hesapla(swing_baslangic_fiyat, swing_bitis_fiyat, yon)

        # Takip penceresi: BOS sonrası N gün
        bitis_idx = min(i + takip_gun, n - 1)
        takip = df.iloc[i + 1: bitis_idx + 1]
        if takip.empty:
            continue

        # Hangi retracement seviyesine dokunuldu (en derin dokunulan seviye)
        donus_seviyesi = None
        donus_hacim_onayli = False
        for f in sorted(FIB_RETRACEMENT_SEVIYELERI):
            seviye_fiyat = seviyeler[f'ret_{f}']
            if yon == 1:
                dokundu = (takip['Low'] <= seviye_fiyat * (1 + tolerans)).any()
            else:
                dokundu = (takip['High'] >= seviye_fiyat * (1 - tolerans)).any()
            if dokundu:
                donus_seviyesi = f
                dokunma_idx = takip.index[
                    (takip['Low'] <= seviye_fiyat * (1 + tolerans)) if yon == 1
                    else (takip['High'] >= seviye_fiyat * (1 - tolerans))
                ][0]
                dokunma_pos = df.index.get_loc(dokunma_idx)
                if dokunma_pos < n - 1:
                    ort_hacim = df['Volume'].iloc[max(0, dokunma_pos - 20):dokunma_pos].mean()
                    donus_hacim_onayli = df['Volume'].iloc[dokunma_pos] > ort_hacim * 1.5

        # Ulaşılan max extension (başarı ölçütü / regresyon hedefi)
        if yon == 1:
            max_fiyat = takip['High'].max()
            hareket_yuzdesi = (max_fiyat - swing_bitis_fiyat) / swing_bitis_fiyat * 100
        else:
            min_fiyat = takip['Low'].min()
            hareket_yuzdesi = (swing_bitis_fiyat - min_fiyat) / swing_bitis_fiyat * 100

        ulasilan_extension = 1.0
        for f in sorted(FIB_EXTENSION_SEVIYELERI):
            hedef = seviyeler[f'ext_{f}']
            if yon == 1 and max_fiyat >= hedef:
                ulasilan_extension = f
            elif yon == -1 and takip['Low'].min() <= hedef:
                ulasilan_extension = f

        sonuclar.append({
            'tarih': bos_tarihi,
            'yon': yon,
            'bos_fiyati': swing_bitis_fiyat,
            'donus_fib_seviyesi': donus_seviyesi,
            'donus_hacim_onayli': donus_hacim_onayli,
            'ulasilan_extension': ulasilan_extension,
            'hareket_yuzdesi': round(hareket_yuzdesi, 2),
        })

    return pd.DataFrame(sonuclar)


if __name__ == "__main__":
    from market_structure import market_structure_tespit_et

    df = pd.read_csv('/home/claude/bist_ai_tahmin/ornek_thyao.csv', index_col=0, parse_dates=True)
    ms_df = market_structure_tespit_et(df)
    fib_sonuc = bos_sonrasi_fib_analizi(df, ms_df)

    print(f"Analiz edilen BOS olayı sayısı: {len(fib_sonuc)}")
    print("\nDönüş seviyesi dağılımı:")
    print(fib_sonuc['donus_fib_seviyesi'].value_counts(dropna=False))
    print("\nUlaşılan extension dağılımı:")
    print(fib_sonuc['ulasilan_extension'].value_counts())
    print("\nOrtalama hareket yüzdesi (yön bazlı):")
    print(fib_sonuc.groupby('yon')['hareket_yuzdesi'].mean())
    print("\nÖrnek satırlar:")
    print(fib_sonuc.head(10))

    fib_sonuc.to_csv('/home/claude/bist_ai_tahmin/thyao_fib_analizi.csv', index=False)
