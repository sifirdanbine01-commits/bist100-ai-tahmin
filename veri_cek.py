"""
VERİ ÇEKME MODÜLÜ
==================
BIST100 hisselerinin geçmiş fiyat verisini çeker.
"""

import time
import pandas as pd
import yfinance as yf

BIST100_HISSELERI = [
    "THYAO", "ASELS", "EREGL", "GARAN", "AKBNK", "ISCTR", "SISE",
    "KCHOL", "SAHOL", "TUPRS", "BIMAS", "FROTO", "TOASO", "PGSUS",
    "TCELL", "TTKOM", "ARCLK", "PETKM", "KOZAL", "KOZAA", "EKGYO",
    "HALKB", "VAKBN", "YKBNK", "SASA", "ALARK", "AEFES", "MGROS",
    "ENKAI", "TAVHL", "ULKER", "VESTL", "OTKAR", "DOAS", "KRDMD",
    "CIMSA", "OYAKC", "TSKB", "AKSA", "AKSEN", "ISGYO", "SOKM",
    "TKFEN", "ODAS", "GUBRF", "ALBRK", "ISMEN", "KONTR", "SMRTG",
    "ASTOR", "HEKTS",
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
