"""
VERİ ÇEKME MODÜLÜ
==================
BIST hisselerinin geçmiş fiyat verisini çeker (104 hisse).
"""

import time
import pandas as pd
import yfinance as yf

BIST100_HISSELERI = [
    'AEFES', 'AKBNK', 'AKSA', 'AKSEN', 'ALARK', 'ALBRK', 'ALTNY', 'ANSGR',
    'ARCLK', 'ASELS', 'ASTOR', 'BALSU', 'BERA', 'BIMAS', 'BRSAN', 'BRYAT',
    'BSOKE', 'BTCIM', 'CANTE', 'CCOLA', 'CIMSA', 'CVKMD', 'CWENE', 'DAPGM',
    'DOAS', 'DOHOL', 'DSTKF', 'ECILC', 'EFOR', 'EKGYO', 'ENERY', 'ENJSA',
    'ENKAI', 'EREGL', 'ESEN', 'EUPWR', 'EUREN', 'FENER', 'FROTO', 'GARAN',
    'GENIL', 'GESAN', 'GLRMK', 'GRSEL', 'GRTHO', 'GSRAY', 'GUBRF', 'HALKB',
    'HEKTS', 'IEYHO', 'ISCTR', 'ISGYO', 'ISMEN', 'IZENR', 'KCHOL', 'KLRHO',
    'KONTR', 'KRDMD', 'KTLEV', 'KUYAS', 'MAGEN', 'MAVI', 'MGROS', 'MIATK',
    'MPARK', 'OBAMS', 'ODAS', 'ODINE', 'OTKAR', 'OYAKC', 'PAHOL', 'PASEU',
    'PATEK', 'PETKM', 'PGSUS', 'PSGYO', 'QUAGR', 'RALYH', 'REEDR', 'SAHOL',
    'SARKY', 'SASA', 'SISE', 'SKBNK', 'SMRTG', 'SOKM', 'TAVHL', 'TCELL',
    'THYAO', 'TKFEN', 'TOASO', 'TRALT', 'TRENJ', 'TRMET', 'TSKB', 'TTKOM',
    'TUKAS', 'TUPRS', 'TURSG', 'ULKER', 'VAKBN', 'VESTL', 'YKBNK', 'ZOREN',
]


def hisse_verisi_cek(sembol, baslangic="2018-01-01"):
    try:
        ticker = f"{sembol}.IS"
        df = yf.download(ticker, start=baslangic, progress=False, auto_adjust=True)
        if df.empty or len(df) < 300:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    except Exception as e:
        print(f"  ⚠️ {sembol} çekilemedi: {e}")
        return None


def tum_bist100_verisini_cek(hisseler=BIST100_HISSELERI, baslangic="2018-01-01"):
    veri = {}
    cekilemeyenler = []
    for i, sembol in enumerate(hisseler):
        print(f"[{i+1}/{len(hisseler)}] {sembol}...")
        df = hisse_verisi_cek(sembol, baslangic)
        if df is not None:
            veri[sembol] = df
        else:
            cekilemeyenler.append(sembol)
        time.sleep(0.5)
    print(f"✅ {len(veri)} hisse | ⚠️ {len(cekilemeyenler)} çekilemedi: {cekilemeyenler}")
    return veri, cekilemeyenler
