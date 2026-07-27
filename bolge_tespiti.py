"""
DESTEK/DİRENÇ BÖLGE TESPİT MODÜLÜ
====================================
Tek bir sürekli çizgi yerine, fiyatın TEKRAR TEKRAR (%1-2 tolerans 
ile) test ettiği ve KALICI OLARAK KIRMADIĞI ayrı bölgeleri tespit 
eder. Her bölge YATAY (sabit seviye) veya EĞİK (trend çizgisi) 
olabilir - hangisi olduğuna, o bölgedeki noktaların zaman içinde 
ne kadar fiyat değiştirdiğine bakarak karar verilir.

Bu modül SORGU ANINDA çalışır (günlük model özelliği değil) - 
amacı sana raporlama/şeffaflık sağlamak, modelin kendisini eğitmek 
değil.
"""

import numpy as np
import pandas as pd

PENCERE_GUN = 504
TOLERANS_YUZDE = 1.5       # aynı bölge sayılması için yakınlık payı
YATAY_ESIK_YUZDE = 3.0     # bölge içindeki toplam eğim bu değerin altındaysa "yatay"
KIRILMA_TEYIT_GUN = 15     # kapanışla bu kadar gün üstünde/altında kalırsa "kırılmış" say


def _noktalari_kumele(gunler, fiyatlar, tolerans_yuzde=TOLERANS_YUZDE):
    """Birbirine yakın (log ölçekte %tolerans içinde) noktaları aynı 
    bölgeye grupla. En az 2 noktalı gruplar 'bölge' sayılır."""
    log_fiyatlar = np.log(fiyatlar)
    n = len(fiyatlar)
    kullanildi = [False] * n
    kumeler = []

    sirali = np.argsort(log_fiyatlar)

    for i in sirali:
        if kullanildi[i]:
            continue
        kume = [i]
        kullanildi[i] = True
        degisti = True
        while degisti:
            degisti = False
            kume_ortalama = np.mean([log_fiyatlar[k] for k in kume])
            for j in sirali:
                if kullanildi[j]:
                    continue
                fark_yuzde = abs(log_fiyatlar[j] - kume_ortalama) / abs(kume_ortalama) * 100
                if fark_yuzde <= tolerans_yuzde:
                    kume.append(j)
                    kullanildi[j] = True
                    degisti = True
        if len(kume) >= 2:
            kumeler.append(kume)

    return kumeler


def _bolge_kirilmis_mi(df_g, son_temas_gun_index, guncel_gun_index, seviye_fiyat, yon):
    """
    yon='direnc': kapanış seviyenin ÜSTÜNDE en az KIRILMA_TEYIT_GUN 
                   gün kalırsa kırılmış (direnç artık geçersiz) sayılır
    yon='destek': kapanış seviyenin ALTINDA en az KIRILMA_TEYIT_GUN 
                   gün kalırsa kırılmış (destek artık geçersiz) sayılır
    """
    closes = df_g['Close'].values
    baslangic = son_temas_gun_index + 1
    bitis = guncel_gun_index + 1
    if baslangic >= bitis:
        return False

    ardisik_sayac = 0
    for i in range(baslangic, bitis):
        if yon == 'direnc':
            otesinde = closes[i] > seviye_fiyat * (1 + TOLERANS_YUZDE / 100)
        else:
            otesinde = closes[i] < seviye_fiyat * (1 - TOLERANS_YUZDE / 100)

        if otesinde:
            ardisik_sayac += 1
            if ardisik_sayac >= KIRILMA_TEYIT_GUN:
                return True
        else:
            ardisik_sayac = 0
    return False


def bolgeleri_bul(df_g, pencere_gun=PENCERE_GUN):
    """
    df_g: pivot_high, pivot_low, swing_tip, High, Low, Close kolonları 
          olan, tarihe göre sıralı DataFrame (guncel_veri.csv'den bir 
          hissenin tüm satırları).
    Döndürür: {'direnc_bolgeleri': [...], 'destek_bolgeleri': [...]}
    Her bölge: {'tip': 'yatay'/'egik', 'seviye_fiyat': güncel gündeki 
                değer, 'temas_sayisi': N, 'noktalar': [(tarih, fiyat), ...], 
                'kirilmis': bool}
    """
    n = len(df_g)
    guncel_gun_index = n - 1
    pencere_baslangic = max(0, n - pencere_gun)

    highs = df_g['High'].values
    lows = df_g['Low'].values
    closes = df_g['Close'].values
    tarihler = df_g['tarih'].values if 'tarih' in df_g.columns else df_g.index.values

    sonuc = {'direnc_bolgeleri': [], 'destek_bolgeleri': []}

    # ---- DİRENÇ BÖLGELERİ (LH noktalarından) ----
    lh_indeksler = [
        j for j in range(pencere_baslangic, n)
        if df_g['pivot_high'].iloc[j] == True and df_g['swing_tip'].iloc[j] == 'LH'
    ]
    if len(lh_indeksler) >= 2:
        fiyatlar = highs[lh_indeksler]
        kumeler = _noktalari_kumele(np.array(lh_indeksler, dtype=float), fiyatlar)
        for kume in kumeler:
            gercek_indeksler = [lh_indeksler[k] for k in kume]
            x = np.array(gercek_indeksler, dtype=float)
            y = highs[gercek_indeksler]
            try:
                egim, kesisim = np.polyfit(x, np.log(y), 1)
            except (np.linalg.LinAlgError, ValueError):
                continue

            span = x.max() - x.min() if len(x) > 1 else 1
            toplam_degisim_yuzde = abs(np.exp(egim * span) - 1) * 100
            tip = 'yatay' if toplam_degisim_yuzde <= YATAY_ESIK_YUZDE else 'eğik'

            if tip == 'yatay':
                # YATAY bölgede fiyat zaten zamanla değişmiyor demektir -
                # eğim bazlı ekstrapolasyon YAPMA, gerçek noktaların 
                # ortalamasını kullan (aksi halde ufak bir eğim hatası 
                # çok uzağa ekstrapole edilip anlamsız bir sayı üretebilir).
                seviye_fiyat_guncel = np.exp(np.mean(np.log(y)))
            else:
                seviye_fiyat_guncel = np.exp(egim * guncel_gun_index + kesisim)

            son_temas_idx = int(x.max())
            kirilmis = _bolge_kirilmis_mi(df_g, son_temas_idx, guncel_gun_index,
                                            seviye_fiyat_guncel, 'direnc')

            sonuc['direnc_bolgeleri'].append({
                'tip': tip,
                'seviye_fiyat': seviye_fiyat_guncel,
                'temas_sayisi': len(gercek_indeksler),
                'noktalar': [(tarihler[idx], highs[idx]) for idx in gercek_indeksler],
                'kirilmis': kirilmis,
            })

    # ---- DESTEK BÖLGELERİ (HL noktalarından) ----
    hl_indeksler = [
        j for j in range(pencere_baslangic, n)
        if df_g['pivot_low'].iloc[j] == True and df_g['swing_tip'].iloc[j] == 'HL'
    ]
    if len(hl_indeksler) >= 2:
        fiyatlar = lows[hl_indeksler]
        kumeler = _noktalari_kumele(np.array(hl_indeksler, dtype=float), fiyatlar)
        for kume in kumeler:
            gercek_indeksler = [hl_indeksler[k] for k in kume]
            x = np.array(gercek_indeksler, dtype=float)
            y = lows[gercek_indeksler]
            try:
                egim, kesisim = np.polyfit(x, np.log(y), 1)
            except (np.linalg.LinAlgError, ValueError):
                continue

            span = x.max() - x.min() if len(x) > 1 else 1
            toplam_degisim_yuzde = abs(np.exp(egim * span) - 1) * 100
            tip = 'yatay' if toplam_degisim_yuzde <= YATAY_ESIK_YUZDE else 'eğik'

            if tip == 'yatay':
                seviye_fiyat_guncel = np.exp(np.mean(np.log(y)))
            else:
                seviye_fiyat_guncel = np.exp(egim * guncel_gun_index + kesisim)

            son_temas_idx = int(x.max())
            kirilmis = _bolge_kirilmis_mi(df_g, son_temas_idx, guncel_gun_index,
                                            seviye_fiyat_guncel, 'destek')

            sonuc['destek_bolgeleri'].append({
                'tip': tip,
                'seviye_fiyat': seviye_fiyat_guncel,
                'temas_sayisi': len(gercek_indeksler),
                'noktalar': [(tarihler[idx], lows[idx]) for idx in gercek_indeksler],
                'kirilmis': kirilmis,
            })

    # En çok temas alanlar önce gösterilsin
    sonuc['direnc_bolgeleri'].sort(key=lambda b: b['temas_sayisi'], reverse=True)
    sonuc['destek_bolgeleri'].sort(key=lambda b: b['temas_sayisi'], reverse=True)

    return sonuc
