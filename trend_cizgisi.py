"""
TREND ÇİZGİSİ MODÜLÜ
======================
Son 504 işlem günündeki LH (Lower High) noktalarından DİRENÇ çizgisi,
HL (Higher Low) noktalarından DESTEK çizgisi çizer. Logaritmik
regresyon kullanır (yüzdesel hareketleri doğru oranlamak için).

Kırılım tanımı: SADECE KAPANIŞ fiyatı çizgiyi geçerse sayılır,
fitil (High/Low) ile geçici aşımlar sayılmaz.

"Kaç gündür çizginin ötesinde" sabit bir eşikle "geçersiz" sayılmaz -
ham sayı olarak modele verilir, model her hissenin kendi davranışına
göre bunu öğrenir.
"""

import numpy as np
import pandas as pd

PENCERE_GUN = 504


def _log_regresyon_egim_kesisim(x_gunler, y_fiyatlar):
    """log(fiyat) = egim * gun + kesisim şeklinde en küçük kareler fit."""
    log_y = np.log(y_fiyatlar)
    egim, kesisim = np.polyfit(x_gunler, log_y, 1)
    return egim, kesisim


def _cizgi_degeri(egim, kesisim, gun):
    return np.exp(egim * gun + kesisim)


def trend_cizgilerini_hesapla(df_g):
    """
    df_g: market_structure_tespit_et sonrası df (pivot_high, pivot_low,
          swing_tip kolonları olmalı).
    Döndürür: df_g'ye eklenen yeni kolonlarla birlikte kopya.
    """
    n = len(df_g)
    closes = df_g['Close'].values
    highs = df_g['High'].values
    lows = df_g['Low'].values
    pivot_high_mask = df_g['pivot_high'].values
    pivot_low_mask = df_g['pivot_low'].values

    direnc_mesafe_yuzde = np.full(n, np.nan)
    direnc_gucu = np.zeros(n)
    direnc_kac_gun_otesinde = np.zeros(n)

    destek_mesafe_yuzde = np.full(n, np.nan)
    destek_gucu = np.zeros(n)
    destek_kac_gun_altinda = np.zeros(n)

    gun_otesinde_sayaci = 0
    gun_altinda_sayaci = 0

    for i in range(n):
        pencere_baslangic = max(0, i - PENCERE_GUN)

        # ---- DİRENÇ ÇİZGİSİ (LH noktalarından) ----
        lh_indeksler = [
            j for j in range(pencere_baslangic, i)
            if pivot_high_mask[j] and df_g['swing_tip'].iloc[j] == 'LH'
        ]
        if len(lh_indeksler) >= 2:
            x = np.array(lh_indeksler, dtype=float)
            y = highs[lh_indeksler]
            try:
                egim, kesisim = _log_regresyon_egim_kesisim(x, y)
                cizgi_deger = _cizgi_degeri(egim, kesisim, i)
                mesafe = (closes[i] - cizgi_deger) / cizgi_deger * 100
                direnc_mesafe_yuzde[i] = mesafe
                direnc_gucu[i] = 2 if len(lh_indeksler) >= 3 else 1

                if closes[i] > cizgi_deger:
                    gun_otesinde_sayaci += 1
                else:
                    gun_otesinde_sayaci = 0
                direnc_kac_gun_otesinde[i] = gun_otesinde_sayaci
            except (np.linalg.LinAlgError, ValueError):
                pass

        # ---- DESTEK ÇİZGİSİ (HL noktalarından) ----
        hl_indeksler = [
            j for j in range(pencere_baslangic, i)
            if pivot_low_mask[j] and df_g['swing_tip'].iloc[j] == 'HL'
        ]
        if len(hl_indeksler) >= 2:
            x = np.array(hl_indeksler, dtype=float)
            y = lows[hl_indeksler]
            try:
                egim, kesisim = _log_regresyon_egim_kesisim(x, y)
                cizgi_deger = _cizgi_degeri(egim, kesisim, i)
                mesafe = (closes[i] - cizgi_deger) / cizgi_deger * 100
                destek_mesafe_yuzde[i] = mesafe
                destek_gucu[i] = 2 if len(hl_indeksler) >= 3 else 1

                if closes[i] < cizgi_deger:
                    gun_altinda_sayaci += 1
                else:
                    gun_altinda_sayaci = 0
                destek_kac_gun_altinda[i] = gun_altinda_sayaci
            except (np.linalg.LinAlgError, ValueError):
                pass

    df_g = df_g.copy()
    df_g['direnc_mesafe_yuzde'] = direnc_mesafe_yuzde
    df_g['direnc_gucu'] = direnc_gucu
    df_g['direnc_kac_gun_otesinde'] = direnc_kac_gun_otesinde
    df_g['destek_mesafe_yuzde'] = destek_mesafe_yuzde
    df_g['destek_gucu'] = destek_gucu
    df_g['destek_kac_gun_altinda'] = destek_kac_gun_altinda

    # İki özel bayrak: "kırıldı ama CHoCH henüz gelmedi" / "CHoCH de onayladı"
    trend_yonu = df_g['trend_yonu'].values
    cizgi_kirildi_choch_bekleniyor = np.zeros(n)
    cizgi_de_onayladi = np.zeros(n)
    for i in range(n):
        direnc_kirik = direnc_kac_gun_otesinde[i] > 0
        if direnc_kirik and trend_yonu[i] != 1:
            cizgi_kirildi_choch_bekleniyor[i] = 1
        if direnc_kirik and trend_yonu[i] == 1:
            cizgi_de_onayladi[i] = 1

    df_g['cizgi_kirildi_choch_bekleniyor'] = cizgi_kirildi_choch_bekleniyor
    df_g['cizgi_de_onayladi'] = cizgi_de_onayladi

    return df_g
