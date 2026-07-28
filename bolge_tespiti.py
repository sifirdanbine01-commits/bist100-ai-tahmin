"""
DESTEK/DİRENÇ BÖLGE TESPİTİ (Pine Script'ten Uyarlanmış)
============================================================
Kullanıcının kendi TradingView Pine Script indikatöründeki mantığın
Python'a birebir uyarlanmış hali:

1) EĞİK ÇİZGİLER: İki pivot noktası birleştirilir, AMA aradaki 
   HİÇBİR MUMUN çizgiyi ihlal etmediği doğrulanır (segment geçerliliği).
   Sadece YAKINSAYAN eğimler kabul edilir (direnç: alçalan zirveler, 
   destek: yükselen dipler - üçgen/takoz tarzı formasyonlar).
   Yeni pivot, mevcut bir çizgiye yakınsa çizgi UZATILIR (temas++).

2) YATAY SEVİYELER: Birbirine yakın (tolerans içinde) pivot noktaları 
   aynı seviyede biriktirilir (kayan ortalama), temas sayısı artar.

3) KIRILMA: Kapanış, çizgiyi/seviyeyi tolerans payıyla geçerse o 
   çizgi/seviye TAMAMEN SİLİNİR. Sonuçta elde kalan liste, ZATEN 
   SADECE KIRILMAMIŞ (hâlâ geçerli) bölgelerden oluşur.
"""

import numpy as np
import pandas as pd

PIVOT_SOL = 10
PIVOT_SAG = 10
PIVOT_HAFIZA = 20
MAX_AKTIF_CIZGI = 4
MAX_YATAY_SEVIYE = 5
TOLERANS_YUZDE_EGIK = 0.3
TOLERANS_YUZDE_YATAY = 0.5


def _pivot_tespit_et(highs, lows, sol, sag):
    n = len(highs)
    pivot_high = np.zeros(n, dtype=bool)
    pivot_low = np.zeros(n, dtype=bool)
    for i in range(sol, n - sag):
        pencere_h = highs[i - sol:i + sag + 1]
        pencere_l = lows[i - sol:i + sag + 1]
        if highs[i] == pencere_h.max() and np.argmax(pencere_h) == sol:
            pivot_high[i] = True
        if lows[i] == pencere_l.min() and np.argmin(pencere_l) == sol:
            pivot_low[i] = True
    return pivot_high, pivot_low


def _cizgi_degeri(baslangic_bar, baslangic_fiyat, bitis_bar, bitis_fiyat, bar):
    if bitis_bar == baslangic_bar:
        return baslangic_fiyat
    return baslangic_fiyat + (bitis_fiyat - baslangic_fiyat) * (bar - baslangic_bar) / (bitis_bar - baslangic_bar)


def _segment_gecerli_mi(highs, lows, eski_bar, eski_fiyat, yeni_bar, yeni_fiyat, direnc_mi, tol):
    span = yeni_bar - eski_bar
    if span <= 1:
        return True
    for i in range(eski_bar + 1, yeni_bar):
        cizgi_deger = _cizgi_degeri(eski_bar, eski_fiyat, yeni_bar, yeni_fiyat, i)
        if direnc_mi:
            if highs[i] > cizgi_deger + tol:
                return False
        else:
            if lows[i] < cizgi_deger - tol:
                return False
    return True


def _yatay_guncelle(seviyeler, yeni_fiyat, yeni_bar, tarihler, tol, max_seviye):
    eslesti = False
    for lvl in seviyeler:
        if abs(yeni_fiyat - lvl['fiyat']) <= tol:
            lvl['temas'] += 1
            lvl['fiyat'] = (lvl['fiyat'] + yeni_fiyat) / 2.0
            lvl['son_bar'] = yeni_bar
            lvl['noktalar'].append((tarihler[yeni_bar], yeni_fiyat))
            eslesti = True
            break
    if not eslesti:
        if len(seviyeler) >= max_seviye:
            min_idx = min(range(len(seviyeler)), key=lambda k: seviyeler[k]['temas'])
            seviyeler.pop(min_idx)
        seviyeler.append({
            'fiyat': yeni_fiyat, 'temas': 1, 'son_bar': yeni_bar,
            'noktalar': [(tarihler[yeni_bar], yeni_fiyat)],
        })


def bolgeleri_bul(df_g, pivot_sol=PIVOT_SOL, pivot_sag=PIVOT_SAG,
                   tolerans_yuzde_egik=TOLERANS_YUZDE_EGIK,
                   tolerans_yuzde_yatay=TOLERANS_YUZDE_YATAY,
                   max_aktif_cizgi=MAX_AKTIF_CIZGI,
                   max_yatay_seviye=MAX_YATAY_SEVIYE):
    n = len(df_g)
    highs = df_g['High'].values
    lows = df_g['Low'].values
    closes = df_g['Close'].values
    tarihler = df_g['tarih'].values if 'tarih' in df_g.columns else df_g.index.values

    pivot_high_mask, pivot_low_mask = _pivot_tespit_et(highs, lows, pivot_sol, pivot_sag)

    aktif_direnc_cizgiler = []
    aktif_destek_cizgiler = []
    pivot_high_hafiza = []
    pivot_low_hafiza = []

    yatay_direnc = []
    yatay_destek = []

    for i in range(n):
        tol_egik = closes[i] * tolerans_yuzde_egik / 100
        tol_yatay = closes[i] * tolerans_yuzde_yatay / 100

        pivot_bar = i - pivot_sag
        if pivot_bar >= 0:
            if pivot_high_mask[pivot_bar]:
                yeni_fiyat = highs[pivot_bar]
                yeni_bar = pivot_bar
                uzatildi = False

                for cizgi in reversed(aktif_direnc_cizgiler):
                    if yeni_bar > cizgi['bitis_bar']:
                        lineval = _cizgi_degeri(cizgi['baslangic_bar'], cizgi['baslangic_fiyat'],
                                                  cizgi['bitis_bar'], cizgi['bitis_fiyat'], yeni_bar)
                        if (abs(yeni_fiyat - lineval) <= tol_egik and
                                _segment_gecerli_mi(highs, lows, cizgi['bitis_bar'], cizgi['bitis_fiyat'],
                                                      yeni_bar, yeni_fiyat, True, tol_egik)):
                            cizgi['bitis_bar'] = yeni_bar
                            cizgi['bitis_fiyat'] = yeni_fiyat
                            cizgi['temas'] += 1
                            cizgi['noktalar'].append((tarihler[yeni_bar], yeni_fiyat))
                            uzatildi = True
                            break

                if not uzatildi:
                    for eski_bar, eski_fiyat in reversed(pivot_high_hafiza):
                        if yeni_fiyat < eski_fiyat and _segment_gecerli_mi(
                                highs, lows, eski_bar, eski_fiyat, yeni_bar, yeni_fiyat, True, tol_egik):
                            if len(aktif_direnc_cizgiler) >= max_aktif_cizgi:
                                min_idx = min(range(len(aktif_direnc_cizgiler)),
                                              key=lambda k: aktif_direnc_cizgiler[k]['temas'])
                                aktif_direnc_cizgiler.pop(min_idx)
                            aktif_direnc_cizgiler.append({
                                'baslangic_bar': eski_bar, 'baslangic_fiyat': eski_fiyat,
                                'bitis_bar': yeni_bar, 'bitis_fiyat': yeni_fiyat,
                                'temas': 2,
                                'noktalar': [(tarihler[eski_bar], eski_fiyat), (tarihler[yeni_bar], yeni_fiyat)],
                            })
                            uzatildi = True
                            break

                _yatay_guncelle(yatay_direnc, yeni_fiyat, yeni_bar, tarihler, tol_yatay, max_yatay_seviye)

                pivot_high_hafiza.append((yeni_bar, yeni_fiyat))
                if len(pivot_high_hafiza) > PIVOT_HAFIZA:
                    pivot_high_hafiza.pop(0)

            if pivot_low_mask[pivot_bar]:
                yeni_fiyat = lows[pivot_bar]
                yeni_bar = pivot_bar
                uzatildi = False

                for cizgi in reversed(aktif_destek_cizgiler):
                    if yeni_bar > cizgi['bitis_bar']:
                        lineval = _cizgi_degeri(cizgi['baslangic_bar'], cizgi['baslangic_fiyat'],
                                                  cizgi['bitis_bar'], cizgi['bitis_fiyat'], yeni_bar)
                        if (abs(yeni_fiyat - lineval) <= tol_egik and
                                _segment_gecerli_mi(highs, lows, cizgi['bitis_bar'], cizgi['bitis_fiyat'],
                                                      yeni_bar, yeni_fiyat, False, tol_egik)):
                            cizgi['bitis_bar'] = yeni_bar
                            cizgi['bitis_fiyat'] = yeni_fiyat
                            cizgi['temas'] += 1
                            cizgi['noktalar'].append((tarihler[yeni_bar], yeni_fiyat))
                            uzatildi = True
                            break

                if not uzatildi:
                    for eski_bar, eski_fiyat in reversed(pivot_low_hafiza):
                        if yeni_fiyat > eski_fiyat and _segment_gecerli_mi(
                                highs, lows, eski_bar, eski_fiyat, yeni_bar, yeni_fiyat, False, tol_egik):
                            if len(aktif_destek_cizgiler) >= max_aktif_cizgi:
                                min_idx = min(range(len(aktif_destek_cizgiler)),
                                              key=lambda k: aktif_destek_cizgiler[k]['temas'])
                                aktif_destek_cizgiler.pop(min_idx)
                            aktif_destek_cizgiler.append({
                                'baslangic_bar': eski_bar, 'baslangic_fiyat': eski_fiyat,
                                'bitis_bar': yeni_bar, 'bitis_fiyat': yeni_fiyat,
                                'temas': 2,
                                'noktalar': [(tarihler[eski_bar], eski_fiyat), (tarihler[yeni_bar], yeni_fiyat)],
                            })
                            uzatildi = True
                            break

                _yatay_guncelle(yatay_destek, yeni_fiyat, yeni_bar, tarihler, tol_yatay, max_yatay_seviye)

                pivot_low_hafiza.append((yeni_bar, yeni_fiyat))
                if len(pivot_low_hafiza) > PIVOT_HAFIZA:
                    pivot_low_hafiza.pop(0)

        aktif_direnc_cizgiler[:] = [
            c for c in aktif_direnc_cizgiler
            if closes[i] <= _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'],
                                            c['bitis_bar'], c['bitis_fiyat'], i) + tol_egik
        ]
        aktif_destek_cizgiler[:] = [
            c for c in aktif_destek_cizgiler
            if closes[i] >= _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'],
                                            c['bitis_bar'], c['bitis_fiyat'], i) - tol_egik
        ]
        yatay_direnc[:] = [lvl for lvl in yatay_direnc if closes[i] <= lvl['fiyat'] + tol_yatay]
        yatay_destek[:] = [lvl for lvl in yatay_destek if closes[i] >= lvl['fiyat'] - tol_yatay]

    guncel_bar = n - 1

    def _cizgileri_formatla(cizgiler):
        sonuc = []
        for c in cizgiler:
            seviye = _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'],
                                     c['bitis_bar'], c['bitis_fiyat'], guncel_bar)
            sonuc.append({
                'tip': 'eğik', 'seviye_fiyat': seviye, 'temas_sayisi': c['temas'],
                'noktalar': c['noktalar'], 'kirilmis': False,
            })
        sonuc.sort(key=lambda b: b['temas_sayisi'], reverse=True)
        return sonuc

    def _yatay_formatla(seviyeler):
        sonuc = []
        for lvl in seviyeler:
            sonuc.append({
                'tip': 'yatay', 'seviye_fiyat': lvl['fiyat'], 'temas_sayisi': lvl['temas'],
                'noktalar': lvl['noktalar'], 'kirilmis': False,
            })
        sonuc.sort(key=lambda b: b['temas_sayisi'], reverse=True)
        return sonuc

    return {
        'direnc_bolgeleri': _cizgileri_formatla(aktif_direnc_cizgiler) + _yatay_formatla(yatay_direnc),
        'destek_bolgeleri': _cizgileri_formatla(aktif_destek_cizgiler) + _yatay_formatla(yatay_destek),
    }
