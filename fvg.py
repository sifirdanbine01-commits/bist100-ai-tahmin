"""
FVG (FAIR VALUE GAP) MODÜLÜ
=============================
Klasik 3-mumluk FVG tanımı:
  Boğa FVG: 3. mumun düşüğü (Low), 1. mumun yükseğinden (High) 
            YUKARIDA kalırsa, aradaki boşluk bir "Fair Value Gap"tır.
  
Bu boşluk, fiyatın ileride "doldurmak" için geri gelebileceği bir
bölge olarak yorumlanır (SMC teorisi). Net matematiksel kural,
sübjektif SMC kavramlarından farklı olarak.
"""

import numpy as np

DOLUM_ARAMA_PENCERE = 20  # FVG oluştuktan sonra kaç gün içinde "dolduruldu" sayılsın


def fvg_ekle(df_g):
    highs = df_g['High'].values
    lows = df_g['Low'].values
    n = len(df_g)

    yakin_bogaFVG_var = np.zeros(n)
    guncel_fvg_ust = None
    guncel_fvg_alt = None
    fvg_olusma_index = None

    for i in range(2, n):
        if lows[i] > highs[i - 2]:
            guncel_fvg_alt = highs[i - 2]
            guncel_fvg_ust = lows[i]
            fvg_olusma_index = i

        if guncel_fvg_alt is not None:
            if lows[i] <= guncel_fvg_ust and i > fvg_olusma_index:
                guncel_fvg_alt = None
                guncel_fvg_ust = None
                fvg_olusma_index = None
            elif i - fvg_olusma_index > DOLUM_ARAMA_PENCERE:
                guncel_fvg_alt = None
                guncel_fvg_ust = None
                fvg_olusma_index = None

        yakin_bogaFVG_var[i] = 1 if guncel_fvg_alt is not None else 0

    df_g = df_g.copy()
    df_g['yakin_bogaFVG_var'] = yakin_bogaFVG_var
    return df_g
