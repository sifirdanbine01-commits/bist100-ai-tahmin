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

3) KIRILMA + ROL DEĞİŞİMİ: Kapanış bir çizgiyi/seviyeyi tolerans 
   payıyla geçince o çizgi/seviye ANINDA silinmez; ROL_ONAY_PENCERE 
   (5 bar) boyunca "rol değişimi adayı" olarak izlenir. Bu süre 
   içinde fiyat eski tarafına geri dönerse SAHTE KIRILIM sayılır ve 
   tamamen elenir. Dönmezse ROL DEĞİŞİMİ ONAYLANIR: kırılan direnç 
   artık gerçek bir destek (ya da kırılan destek gerçek bir direnç) 
   olarak, temas geçmişiyle birlikte, listede kalmaya devam eder 
   ('rolu_degisti' bayrağıyla işaretlenir). Ayrıca artık aktif çizgi/
   seviye sayısına ZORLA bir üst sınır uygulanmıyor - kırılmamış 
   (veya rolü onaylı şekilde değişmiş) HER bölge takip edilir.

4) ÖLÇEK: Eğik çizgiler LOGARİTMİK fiyat ölçeğinde hesaplanır (iki 
   temas noktası arasında log(fiyat) uzayında doğrusal interpolasyon) 
   - TradingView'daki log-scale grafik görünümüyle tutarlı.

5) PRICE ACTION KAYNAĞI: df_g içinde market_structure.py'nin ürettiği
   'pivot_high'/'pivot_low'/'swing_tip' kolonları varsa, eğik çizgiler
   SADECE gerçek LH (alçalan tepe) ve HL (yükselen dip) noktalarından
   kurulur - bolge_tespiti'nin kendi bağımsız pivot tespiti yerine,
   BOS/CHoCH yapısal bağlamında zaten onaylanmış swing noktaları
   kullanılır. Bu kolonlar yoksa (örn. ham OHLC ile bağımsız çağrı),
   eski bağımsız pivot tespitine (PIVOT_SOL/PIVOT_SAG) geri dönülür.
"""

import numpy as np
import pandas as pd

PIVOT_SOL = 10
PIVOT_SAG = 10
MS_PIVOT_SAG = 3  # market_structure.py'nin varsayılan sağ pencere değeriyle aynı
PIVOT_HAFIZA = 20
ROL_ONAY_PENCERE = 5  # kırılmadan sonra rol değişiminin onaylanması için beklenen bar sayısı
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
    """
    LOGARİTMİK fiyat ölçeğinde doğrusal interpolasyon.
    İki temas noktası arasında LOG(fiyat) uzayında düz bir çizgi çekilir,
    sonra gerçek fiyata çevrilir - tıpkı TradingView'da log-scale
    grafikte görülen çizginin, doğrusal fiyat uzayında üstel bir eğri
    olarak görünmesi gibi. Yüzdesel hareketleri fiyat seviyesinden
    bağımsız (ölçekten bağımsız) şekilde temsil eder.
    """
    if bitis_bar == baslangic_bar:
        return baslangic_fiyat
    log_baslangic = np.log(baslangic_fiyat)
    log_bitis = np.log(bitis_fiyat)
    log_deger = log_baslangic + (log_bitis - log_baslangic) * (bar - baslangic_bar) / (bitis_bar - baslangic_bar)
    return np.exp(log_deger)


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


def _seviye_hesapla(obj, tip, bar):
    """Bir eğik çizginin ya da yatay seviyenin, verilen bar'daki fiyat değeri."""
    if tip == 'eğik':
        return _cizgi_degeri(obj['baslangic_bar'], obj['baslangic_fiyat'],
                               obj['bitis_bar'], obj['bitis_fiyat'], bar)
    return obj['fiyat']


def _yatay_guncelle(seviyeler, yeni_fiyat, yeni_bar, tarihler, tol, max_seviye=None):
    eslesti = False
    for lvl in reversed(seviyeler):
        if abs(yeni_fiyat - lvl['fiyat']) <= tol:
            lvl['temas'] += 1
            lvl['fiyat'] = (lvl['fiyat'] + yeni_fiyat) / 2.0
            lvl['son_bar'] = yeni_bar
            lvl['noktalar'].append((tarihler[yeni_bar], yeni_fiyat))
            eslesti = True
            break
    if not eslesti:
        seviyeler.append({
            'fiyat': yeni_fiyat, 'temas': 1, 'son_bar': yeni_bar,
            'noktalar': [(tarihler[yeni_bar], yeni_fiyat)],
        })


def _bolge_simulasyonu_adimlari(df_g, pivot_sol=PIVOT_SOL, pivot_sag=PIVOT_SAG,
                                  tolerans_yuzde_egik=TOLERANS_YUZDE_EGIK,
                                  tolerans_yuzde_yatay=TOLERANS_YUZDE_YATAY,
                                  max_aktif_cizgi=MAX_AKTIF_CIZGI,
                                  max_yatay_seviye=MAX_YATAY_SEVIYE):
    """
    Pine Script'ten uyarlanan bar-bar simülasyonun ORTAK çekirdeği.
    Her bar (i) işlendikten SONRA o barın GÜNCEL aktif bölge durumunu
    yield eder. Böylece hem 'bolgeleri_bul' (sadece son bar) hem de
    'gunluk_bolge_ozellikleri' (HER bar - model eğitimi için) aynı
    mantığı kullanır, kod tekrarı ve sapma riski olmaz.

    ÖNEMLİ (look-ahead yok): Bir pivot, ancak pivot_sag kadar bar
    geçtikten SONRA (bar i = pivot_bar + pivot_sag'da) işleniyor - yani
    bar i'deki durum, gelecekten bilgi sızdırmaz.
    """
    n = len(df_g)
    highs = df_g['High'].values
    lows = df_g['Low'].values
    closes = df_g['Close'].values
    tarihler = df_g['tarih'].values if 'tarih' in df_g.columns else df_g.index.values

    ms_kolonlari_var = all(c in df_g.columns for c in ('pivot_high', 'pivot_low', 'swing_tip'))

    if ms_kolonlari_var:
        # PRICE ACTION: market_structure.py'nin zaten onayladığı pivotlar
        # kaynak alınır. Eğik çizgi ADAYLARI sadece gerçek LH/HL noktaları
        # olabilir; yatay seviyeler ve "eski nokta" hafızası için ise tüm
        # pivot noktaları (HH/LH ya da LL/HL fark etmez) kullanılır.
        pivot_high_mask = df_g['pivot_high'].fillna(False).values.astype(bool)
        pivot_low_mask = df_g['pivot_low'].fillna(False).values.astype(bool)
        swing_tip_arr = df_g['swing_tip'].values
        direnc_aday_mask = pivot_high_mask & (swing_tip_arr == 'LH')
        destek_aday_mask = pivot_low_mask & (swing_tip_arr == 'HL')
        gecikme = MS_PIVOT_SAG
    else:
        pivot_high_mask, pivot_low_mask = _pivot_tespit_et(highs, lows, pivot_sol, pivot_sag)
        direnc_aday_mask = pivot_high_mask
        destek_aday_mask = pivot_low_mask
        gecikme = pivot_sag

    aktif_direnc_cizgiler = []
    aktif_destek_cizgiler = []
    pivot_high_hafiza = []
    pivot_low_hafiza = []

    yatay_direnc = []
    yatay_destek = []

    direnc_rol_adaylari = []
    destek_rol_adaylari = []

    for i in range(n):
        tol_egik = closes[i] * tolerans_yuzde_egik / 100
        tol_yatay = closes[i] * tolerans_yuzde_yatay / 100

        pivot_bar = i - gecikme
        if pivot_bar >= 0:
            if pivot_high_mask[pivot_bar]:
                yeni_fiyat = highs[pivot_bar]
                yeni_bar = pivot_bar
                uzatildi = False

                if direnc_aday_mask[pivot_bar]:
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

                if destek_aday_mask[pivot_bar]:
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

        # KIRILMA + ROL DEĞİŞİMİ TESTİ
        # Kırılan bir bölge artık ANINDA silinmiyor; ROL_ONAY_PENCERE kadar
        # bar boyunca "rol değişimi adayı" olarak izleniyor. Bu süre içinde
        # fiyat tekrar eski tarafına geçerse SAHTE KIRILIM (tamamen elenir);
        # geçmezse ROL DEĞİŞİMİ ONAYLANIR ve eski direnç artık gerçek bir
        # destek (ya da eski destek gerçek bir direnç) olarak devam eder.
        kalan_direnc, kirilan_direnc = [], []
        for c in aktif_direnc_cizgiler:
            seviye = _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'], c['bitis_bar'], c['bitis_fiyat'], i)
            (kalan_direnc if closes[i] <= seviye + tol_egik else kirilan_direnc).append(c)
        aktif_direnc_cizgiler[:] = kalan_direnc
        for c in kirilan_direnc:
            direnc_rol_adaylari.append({'obj': c, 'tip': 'eğik', 'kirilma_bar': i})

        kalan_destek, kirilan_destek = [], []
        for c in aktif_destek_cizgiler:
            seviye = _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'], c['bitis_bar'], c['bitis_fiyat'], i)
            (kalan_destek if closes[i] >= seviye - tol_egik else kirilan_destek).append(c)
        aktif_destek_cizgiler[:] = kalan_destek
        for c in kirilan_destek:
            destek_rol_adaylari.append({'obj': c, 'tip': 'eğik', 'kirilma_bar': i})

        kalan_yd, kirilan_yd = [], []
        for lvl in yatay_direnc:
            (kalan_yd if closes[i] <= lvl['fiyat'] + tol_yatay else kirilan_yd).append(lvl)
        yatay_direnc[:] = kalan_yd
        for lvl in kirilan_yd:
            direnc_rol_adaylari.append({'obj': lvl, 'tip': 'yatay', 'kirilma_bar': i})

        kalan_yde, kirilan_yde = [], []
        for lvl in yatay_destek:
            (kalan_yde if closes[i] >= lvl['fiyat'] - tol_yatay else kirilan_yde).append(lvl)
        yatay_destek[:] = kalan_yde
        for lvl in kirilan_yde:
            destek_rol_adaylari.append({'obj': lvl, 'tip': 'yatay', 'kirilma_bar': i})

        kalan_adaylar = []
        for aday in direnc_rol_adaylari:
            seviye = _seviye_hesapla(aday['obj'], aday['tip'], i)
            tol = tol_egik if aday['tip'] == 'eğik' else tol_yatay
            if closes[i] < seviye - tol:
                continue  # sahte kırılım - aday tamamen elendi
            if i - aday['kirilma_bar'] >= ROL_ONAY_PENCERE:
                aday['obj']['rolu_degisti'] = True
                (aktif_destek_cizgiler if aday['tip'] == 'eğik' else yatay_destek).append(aday['obj'])
                continue
            kalan_adaylar.append(aday)
        direnc_rol_adaylari[:] = kalan_adaylar

        kalan_adaylar = []
        for aday in destek_rol_adaylari:
            seviye = _seviye_hesapla(aday['obj'], aday['tip'], i)
            tol = tol_egik if aday['tip'] == 'eğik' else tol_yatay
            if closes[i] > seviye + tol:
                continue  # sahte kırılım - aday tamamen elendi
            if i - aday['kirilma_bar'] >= ROL_ONAY_PENCERE:
                aday['obj']['rolu_degisti'] = True
                (aktif_direnc_cizgiler if aday['tip'] == 'eğik' else yatay_direnc).append(aday['obj'])
                continue
            kalan_adaylar.append(aday)
        destek_rol_adaylari[:] = kalan_adaylar

        yield i, aktif_direnc_cizgiler, aktif_destek_cizgiler, yatay_direnc, yatay_destek


def bolgeleri_bul(df_g, pivot_sol=PIVOT_SOL, pivot_sag=PIVOT_SAG,
                   tolerans_yuzde_egik=TOLERANS_YUZDE_EGIK,
                   tolerans_yuzde_yatay=TOLERANS_YUZDE_YATAY,
                   max_aktif_cizgi=MAX_AKTIF_CIZGI,
                   max_yatay_seviye=MAX_YATAY_SEVIYE,
                   ilgi_esik_yuzde=20):
    """
    ilgi_esik_yuzde: Güncel fiyattan bu yüzdeden UZAK bölgeler artık
    "ilgisiz" sayılıp sonuçtan ÇIKARILIR. "Kırılmamış" olmak, "hâlâ 
    ilgili" olmak demek değil - fiyat bir bölgeden uzaklaşıp bir daha 
    hiç dönmediyse (kırılmadan, sadece terk ederek), o bölge artık 
    pratikte anlamsızdır.
    """
    n = len(df_g)
    closes = df_g['Close'].values

    aktif_direnc_cizgiler = aktif_destek_cizgiler = yatay_direnc = yatay_destek = []
    for i, ad, ade, yd, yde in _bolge_simulasyonu_adimlari(
            df_g, pivot_sol, pivot_sag, tolerans_yuzde_egik, tolerans_yuzde_yatay,
            max_aktif_cizgi, max_yatay_seviye):
        aktif_direnc_cizgiler, aktif_destek_cizgiler, yatay_direnc, yatay_destek = ad, ade, yd, yde

    guncel_bar = n - 1
    guncel_fiyat = closes[-1]

    def _ilgili_mi(seviye_fiyat):
        fark_yuzde = abs(guncel_fiyat - seviye_fiyat) / seviye_fiyat * 100
        return fark_yuzde <= ilgi_esik_yuzde

    def _cizgileri_formatla(cizgiler):
        sonuc = []
        for c in cizgiler:
            seviye = _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'],
                                     c['bitis_bar'], c['bitis_fiyat'], guncel_bar)
            if not _ilgili_mi(seviye):
                continue
            sonuc.append({
                'tip': 'eğik', 'seviye_fiyat': seviye, 'temas_sayisi': c['temas'],
                'noktalar': c['noktalar'], 'kirilmis': False,
                'rolu_degisti': c.get('rolu_degisti', False),
            })
        sonuc.sort(key=lambda b: b['temas_sayisi'], reverse=True)
        return sonuc

    def _yatay_formatla(seviyeler):
        sonuc = []
        for lvl in seviyeler:
            if not _ilgili_mi(lvl['fiyat']):
                continue
            sonuc.append({
                'tip': 'yatay', 'seviye_fiyat': lvl['fiyat'], 'temas_sayisi': lvl['temas'],
                'noktalar': lvl['noktalar'], 'kirilmis': False,
                'rolu_degisti': lvl.get('rolu_degisti', False),
            })
        sonuc.sort(key=lambda b: b['temas_sayisi'], reverse=True)
        return sonuc

    return {
        'direnc_bolgeleri': _cizgileri_formatla(aktif_direnc_cizgiler) + _yatay_formatla(yatay_direnc),
        'destek_bolgeleri': _cizgileri_formatla(aktif_destek_cizgiler) + _yatay_formatla(yatay_destek),
    }


def gunluk_bolge_ozellikleri(df_g, pivot_sol=PIVOT_SOL, pivot_sag=PIVOT_SAG,
                               tolerans_yuzde_egik=TOLERANS_YUZDE_EGIK,
                               tolerans_yuzde_yatay=TOLERANS_YUZDE_YATAY,
                               max_aktif_cizgi=MAX_AKTIF_CIZGI,
                               max_yatay_seviye=MAX_YATAY_SEVIYE):
    """
    MODEL EĞİTİMİ İÇİN: bolgeleri_bul() sadece son bar için sonuç
    verirken, bu fonksiyon HER GÜN için o günkü aktif (kırılmamış)
    bölgelere göre 4 sayısal özellik üretir:

      - bolge_direnc_mesafe_yuzde: üstteki en yakın direncin uzaklığı (%)
      - bolge_direnc_temas: o direncin temas sayısı
      - bolge_destek_mesafe_yuzde: alttaki en yakın desteğin uzaklığı (%)
      - bolge_destek_temas: o desteğin temas sayısı

    O gün yakında bir bölge yoksa mesafe=999 (pratikte "sonsuz uzak"),
    temas=0 verilir (NaN yerine - dropna ile satır kaybını önlemek için).

    Look-ahead YOK: _bolge_simulasyonu_adimlari zaten pivot_sag kadar
    gecikmeli işliyor, yani bar i'deki değer sadece o ana kadar
    BİLİNEBİLECEK bilgiyi kullanır.
    """
    n = len(df_g)
    closes = df_g['Close'].values

    direnc_mesafe = np.full(n, 999.0)
    direnc_temas = np.zeros(n)
    destek_mesafe = np.full(n, 999.0)
    destek_temas = np.zeros(n)

    for i, ad, ade, yd, yde in _bolge_simulasyonu_adimlari(
            df_g, pivot_sol, pivot_sag, tolerans_yuzde_egik, tolerans_yuzde_yatay,
            max_aktif_cizgi, max_yatay_seviye):
        fiyat = closes[i]

        direnc_adaylari = []
        for c in ad:
            seviye = _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'],
                                     c['bitis_bar'], c['bitis_fiyat'], i)
            if seviye > fiyat:
                direnc_adaylari.append((seviye, c['temas']))
        for lvl in yd:
            if lvl['fiyat'] > fiyat:
                direnc_adaylari.append((lvl['fiyat'], lvl['temas']))
        if direnc_adaylari:
            en_yakin_seviye, en_yakin_temas = min(direnc_adaylari, key=lambda t: t[0])
            direnc_mesafe[i] = (en_yakin_seviye - fiyat) / fiyat * 100
            direnc_temas[i] = en_yakin_temas

        destek_adaylari = []
        for c in ade:
            seviye = _cizgi_degeri(c['baslangic_bar'], c['baslangic_fiyat'],
                                     c['bitis_bar'], c['bitis_fiyat'], i)
            if seviye < fiyat:
                destek_adaylari.append((seviye, c['temas']))
        for lvl in yde:
            if lvl['fiyat'] < fiyat:
                destek_adaylari.append((lvl['fiyat'], lvl['temas']))
        if destek_adaylari:
            en_yakin_seviye, en_yakin_temas = max(destek_adaylari, key=lambda t: t[0])
            destek_mesafe[i] = (fiyat - en_yakin_seviye) / fiyat * 100
            destek_temas[i] = en_yakin_temas

    return pd.DataFrame({
        'bolge_direnc_mesafe_yuzde': direnc_mesafe,
        'bolge_direnc_temas': direnc_temas,
        'bolge_destek_mesafe_yuzde': destek_mesafe,
        'bolge_destek_temas': destek_temas,
    }, index=df_g.index)
