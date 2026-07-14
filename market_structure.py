"""
MARKET STRUCTURE MODÜLÜ (CHoCH / BOS Tespiti)
==============================================
Fraktal pivot yöntemiyle HH/HL/LH/LL noktalarını bulur,
bunlardan CHoCH (Change of Character) ve BOS (Break of Structure)
olaylarını tespit eder.

Mantık:
- Pivot High: kendinden önceki ve sonraki N mumdan daha yüksek olan mum
- Pivot Low: kendinden önceki ve sonraki N mumdan daha düşük olan mum
- Trend YUKARI iken bir önceki Pivot Low kırılırsa -> CHoCH (trend değişim uyarısı)
- Trend AŞAĞI iken bir önceki Pivot High kırılırsa -> CHoCH
- CHoCH sonrası trend teyit olup devam ederse (bir sonraki pivotu da kırarsa) -> BOS
"""

import pandas as pd
import numpy as np


def pivot_noktalarini_bul(df, sol=3, sag=3):
    """
    Fraktal pivot high/low tespiti.
    sol/sag: pivotun solundan ve sağından kaç mum karşılaştırılacak.
    Daha büyük sol/sag = daha az ama daha 'anlamlı' pivotlar.
    """
    high = df['High'].values
    low = df['Low'].values
    n = len(df)

    pivot_high = np.zeros(n, dtype=bool)
    pivot_low = np.zeros(n, dtype=bool)

    for i in range(sol, n - sag):
        pencere_high = high[i - sol:i + sag + 1]
        pencere_low = low[i - sol:i + sag + 1]

        if high[i] == pencere_high.max() and np.argmax(pencere_high) == sol:
            pivot_high[i] = True
        if low[i] == pencere_low.min() and np.argmin(pencere_low) == sol:
            pivot_low[i] = True

    df = df.copy()
    df['pivot_high'] = pivot_high
    df['pivot_low'] = pivot_low
    return df


def market_structure_tespit_et(df, sol=3, sag=3):
    """
    Pivot noktalarından HH/HL/LH/LL etiketleme + CHoCH/BOS tespiti.

    Dönen kolonlar:
    - swing_tip: 'HH','HL','LH','LL' veya None
    - yapi_olay: 'CHOCH_YUKARI','CHOCH_ASAGI','BOS_YUKARI','BOS_ASAGI' veya None
    - trend_yonu: o andaki bilinen trend yönü (1=yukarı, -1=aşağı, 0=belirsiz)
    """
    df = pivot_noktalarini_bul(df, sol=sol, sag=sag)
    n = len(df)

    swing_tip = [None] * n
    yapi_olay = [None] * n
    trend_yonu = [0] * n

    son_pivot_high = None       # (index, fiyat)
    son_pivot_low = None
    onceki_pivot_high = None
    onceki_pivot_low = None
    mevcut_trend = 0            # 0 belirsiz, 1 yukarı, -1 aşağı
    son_kirilan_high_idx = None  # tekrar tetiklenmeyi önlemek için
    son_kirilan_low_idx = None

    highs = df['High'].values
    lows = df['Low'].values
    closes = df['Close'].values

    for i in range(n):
        # --- Yeni pivot high oluştuysa HH/LH etiketle ---
        if df['pivot_high'].iloc[i]:
            fiyat = highs[i]
            if son_pivot_high is not None:
                if fiyat > son_pivot_high[1]:
                    swing_tip[i] = 'HH'
                else:
                    swing_tip[i] = 'LH'
            onceki_pivot_high = son_pivot_high
            son_pivot_high = (i, fiyat)

        # --- Yeni pivot low oluştuysa HL/LL etiketle ---
        if df['pivot_low'].iloc[i]:
            fiyat = lows[i]
            if son_pivot_low is not None:
                if fiyat > son_pivot_low[1]:
                    swing_tip[i] = 'HL'
                else:
                    swing_tip[i] = 'LL'
            onceki_pivot_low = son_pivot_low
            son_pivot_low = (i, fiyat)

        # --- CHoCH / BOS kontrolü: kapanış fiyatı önceki pivotu kırdı mı ---
        # NOT: Aynı anda hem yukarı hem aşağı kırılım kontrolü yapılır,
        # hangisinin CHoCH hangisinin BOS olduğu mevcut trende göre belirlenir.
        kapanis = closes[i]

        asagi_kirildi = (son_pivot_low is not None and son_pivot_low[0] < i
                          and kapanis < son_pivot_low[1]
                          and son_kirilan_low_idx != son_pivot_low[0])
        yukari_kirildi = (son_pivot_high is not None and son_pivot_high[0] < i
                           and kapanis > son_pivot_high[1]
                           and son_kirilan_high_idx != son_pivot_high[0])

        if asagi_kirildi:
            if mevcut_trend == 1:
                yapi_olay[i] = 'CHOCH_ASAGI'   # trend yukarıydı, şimdi bozuldu
                mevcut_trend = -1
            elif mevcut_trend == -1:
                yapi_olay[i] = 'BOS_ASAGI'     # trend zaten aşağıydı, devam ediyor
            elif mevcut_trend == 0:
                mevcut_trend = -1
            son_kirilan_low_idx = son_pivot_low[0]

        elif yukari_kirildi:
            if mevcut_trend == -1:
                yapi_olay[i] = 'CHOCH_YUKARI'  # trend aşağıydı, şimdi bozuldu
                mevcut_trend = 1
            elif mevcut_trend == 1:
                yapi_olay[i] = 'BOS_YUKARI'    # trend zaten yukarıydı, devam ediyor
            elif mevcut_trend == 0:
                mevcut_trend = 1
            son_kirilan_high_idx = son_pivot_high[0]

        # İlk trend ataması (başlangıçta belirsizse basitçe yön ver)
        if mevcut_trend == 0 and (son_pivot_high or son_pivot_low):
            mevcut_trend = 1  # varsayılan başlangıç, veriye göre ilk BOS ile netleşir

        trend_yonu[i] = mevcut_trend

    df['swing_tip'] = swing_tip
    df['yapi_olay'] = yapi_olay
    df['trend_yonu'] = trend_yonu
    return df


if __name__ == "__main__":
    df = pd.read_csv('/home/claude/bist_ai_tahmin/ornek_thyao.csv', index_col=0, parse_dates=True)
    sonuc = market_structure_tespit_et(df)

    olaylar = sonuc[sonuc['yapi_olay'].notna()]
    print(f"Toplam mum: {len(sonuc)}")
    print(f"Tespit edilen yapısal olay sayısı: {len(olaylar)}")
    print("\nOlay dağılımı:")
    print(olaylar['yapi_olay'].value_counts())
    print("\nSon 10 olay:")
    print(olaylar[['Close', 'yapi_olay', 'trend_yonu']].tail(10))

    sonuc.to_csv('/home/claude/bist_ai_tahmin/thyao_market_structure.csv')
