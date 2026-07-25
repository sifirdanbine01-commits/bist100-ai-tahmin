"""
TEKNİK GÖSTERGELER MODÜLÜ
=========================
RSI, MACD, ADX, Bollinger, ATR, Hacim oranı gibi tüm klasik
göstergeleri tek fonksiyonda hesaplayıp DataFrame'e ekler.
"""

import pandas as pd
import pandas_ta_classic as ta


def gostergeleri_ekle(df):
    df = df.copy()

    df['rsi_14'] = ta.rsi(df['Close'], length=14)

    macd = ta.macd(df['Close'])
    df['macd'] = macd['MACD_12_26_9']
    df['macd_sinyal'] = macd['MACDs_12_26_9']
    df['macd_hist'] = macd['MACDh_12_26_9']
    df['macd_kesisim_yukari'] = (
        (df['macd'] > df['macd_sinyal']) &
        (df['macd'].shift(1) <= df['macd_sinyal'].shift(1))
    ).astype(int)
    df['macd_kesisim_asagi'] = (
        (df['macd'] < df['macd_sinyal']) &
        (df['macd'].shift(1) >= df['macd_sinyal'].shift(1))
    ).astype(int)

    adx = ta.adx(df['High'], df['Low'], df['Close'])
    df['adx'] = adx['ADX_14']

    df['ma20'] = ta.sma(df['Close'], length=20)
    df['ma50'] = ta.sma(df['Close'], length=50)
    df['ma200'] = ta.sma(df['Close'], length=200)
    df['ema5'] = ta.ema(df['Close'], length=5)
    df['ema19'] = ta.ema(df['Close'], length=19)
    df['ema_kesisim_yukari'] = (
        (df['ema5'] > df['ema19']) &
        (df['ema5'].shift(1) <= df['ema19'].shift(1))
    ).astype(int)

    bbands = ta.bbands(df['Close'], length=20)
    bbu_col = [c for c in bbands.columns if c.startswith('BBU')][0]
    bbl_col = [c for c in bbands.columns if c.startswith('BBL')][0]
    bbm_col = [c for c in bbands.columns if c.startswith('BBM')][0]
    df['bb_genislik'] = (bbands[bbu_col] - bbands[bbl_col]) / bbands[bbm_col]

    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

    df['hacim_ort20'] = df['Volume'].rolling(20).mean()
    df['hacim_orani'] = df['Volume'] / df['hacim_ort20']

    stoch = ta.stoch(df['High'], df['Low'], df['Close'])
    df['stoch_k'] = stoch['STOCHk_14_3_3']
    df['stoch_d'] = stoch['STOCHd_14_3_3']

    df['fiyat_ma200_ustu'] = (df['Close'] > df['ma200']).astype(int)

    return df
