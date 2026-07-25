"""
MARKET STRUCTURE MODÜLÜ (CHoCH / BOS Tespiti)
==============================================
Fraktal pivot yöntemiyle HH/HL/LH/LL noktalarını bulur,
bunlardan CHoCH (Change of Character) ve BOS (Break of Structure)
olaylarını tespit eder.
"""

import pandas as pd
import numpy as np


def pivot_noktalarini_bul(df, sol=3, sag=3):
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
    df = pivot_noktalarini_bul(df, sol=sol, sag=sag)
    n = len(df)

    swing_tip = [None] * n
    yapi_olay = [None] * n
    trend_yonu = [0] * n

    son_pivot_high = None
    son_pivot_low = None
    mevcut_trend = 0
    son_kirilan_high_idx = None
    son_kirilan_low_idx = None

    highs = df['High'].values
    lows = df['Low'].values
    closes = df['Close'].values

    for i in range(n):
        if df['pivot_high'].iloc[i]:
            fiyat = highs[i]
            if son_pivot_high is not None:
                if fiyat > son_pivot_high[1]:
                    swing_tip[i] = 'HH'
                else:
                    swing_tip[i] = 'LH'
            son_pivot_high = (i, fiyat)

        if df['pivot_low'].iloc[i]:
            fiyat = lows[i]
            if son_pivot_low is not None:
                if fiyat > son_pivot_low[1]:
                    swing_tip[i] = 'HL'
                else:
                    swing_tip[i] = 'LL'
            son_pivot_low = (i, fiyat)

        kapanis = closes[i]

        asagi_kirildi = (son_pivot_low is not None and son_pivot_low[0] < i
                          and kapanis < son_pivot_low[1]
                          and son_kirilan_low_idx != son_pivot_low[0])
        yukari_kirildi = (son_pivot_high is not None and son_pivot_high[0] < i
                           and kapanis > son_pivot_high[1]
                           and son_kirilan_high_idx != son_pivot_high[0])

        if asagi_kirildi:
            if mevcut_trend == 1:
                yapi_olay[i] = 'CHOCH_ASAGI'
                mevcut_trend = -1
            elif mevcut_trend == -1:
                yapi_olay[i] = 'BOS_ASAGI'
            elif mevcut_trend == 0:
                mevcut_trend = -1
            son_kirilan_low_idx = son_pivot_low[0]

        elif yukari_kirildi:
            if mevcut_trend == -1:
                yapi_olay[i] = 'CHOCH_YUKARI'
                mevcut_trend = 1
            elif mevcut_trend == 1:
                yapi_olay[i] = 'BOS_YUKARI'
            elif mevcut_trend == 0:
                mevcut_trend = 1
            son_kirilan_high_idx = son_pivot_high[0]

        trend_yonu[i] = mevcut_trend

    df['swing_tip'] = swing_tip
    df['yapi_olay'] = yapi_olay
    df['trend_yonu'] = trend_yonu

    son_pivot_low_fiyat = [None] * n
    guncel_son_low = None
    for i in range(n):
        if df['pivot_low'].iloc[i]:
            guncel_son_low = lows[i]
        son_pivot_low_fiyat[i] = guncel_son_low
    df['son_pivot_low_fiyat'] = son_pivot_low_fiyat

    return df
