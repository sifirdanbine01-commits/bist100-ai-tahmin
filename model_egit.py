"""
ORTAK MODEL EĞİTİM MODÜLÜ (5 Model)
=====================================
1) Genel Mod Sınıflandırma + Regresyon (fallback)
2) Hedef 1/2/3 Sınıflandırma (Fibonacci kademeli hedefler)
Son 3-4 yıla üstel ağırlık verir.
"""

import numpy as np
import joblib
from lightgbm import LGBMClassifier, LGBMRegressor

from gunluk_ozellik_seti import OZELLIK_KOLONLARI

MODEL_DOSYALARI = {
    'genel_siniflandirma': 'model_siniflandirma.pkl',
    'genel_regresyon': 'model_regresyon.pkl',
    'hedef1': 'model_hedef1.pkl',
    'hedef2': 'model_hedef2.pkl',
    'hedef3': 'model_hedef3.pkl',
}


def yakinlik_agirligi_hesapla(tarihler, referans_tarih, yari_omur_yil=3.5):
    gun_farki = (referans_tarih - tarihler).dt.days.values
    agirlik = 0.5 ** (gun_farki / (365 * yari_omur_yil))
    return np.clip(agirlik, 0.05, 1.0)


def modelleri_egit(egitim_df, referans_tarih):
    modeller = {}

    genel_veri = egitim_df.dropna(subset=['basarili', 'getiri_yuzde'])
    agirliklar = yakinlik_agirligi_hesapla(genel_veri['tarih'], referans_tarih)
    X = genel_veri[OZELLIK_KOLONLARI]

    siniflandirma = LGBMClassifier(
        n_estimators=150, max_depth=5, learning_rate=0.05,
        min_child_samples=20, verbose=-1
    )
    siniflandirma.fit(X, genel_veri['basarili'], sample_weight=agirliklar)
    modeller['genel_siniflandirma'] = siniflandirma

    regresyon = LGBMRegressor(
        n_estimators=150, max_depth=5, learning_rate=0.05,
        min_child_samples=20, verbose=-1
    )
    regresyon.fit(X, genel_veri['getiri_yuzde'], sample_weight=agirliklar)
    modeller['genel_regresyon'] = regresyon

    for hedef_no in [1, 2, 3]:
        kolon = f'hedef{hedef_no}_basarili'
        hedef_veri = egitim_df.dropna(subset=[kolon])

        if len(hedef_veri) < 50 or hedef_veri[kolon].nunique() < 2:
            print(f"  ⚠️ Hedef {hedef_no} için yeterli veri yok "
                  f"({len(hedef_veri)} örnek) - bu model atlanıyor.")
            modeller[f'hedef{hedef_no}'] = None
            continue

        Xh = hedef_veri[OZELLIK_KOLONLARI]
        agirliklar_h = yakinlik_agirligi_hesapla(hedef_veri['tarih'], referans_tarih)

        model_h = LGBMClassifier(
            n_estimators=150, max_depth=5, learning_rate=0.05,
            min_child_samples=20, verbose=-1
        )
        model_h.fit(Xh, hedef_veri[kolon], sample_weight=agirliklar_h)
        modeller[f'hedef{hedef_no}'] = model_h
        print(f"  ✅ Hedef {hedef_no} modeli eğitildi ({len(hedef_veri)} örnek)")

    return modeller


def modelleri_kaydet(modeller):
    for anahtar, dosya_adi in MODEL_DOSYALARI.items():
        if modeller.get(anahtar) is not None:
            joblib.dump(modeller[anahtar], dosya_adi)


def modelleri_yukle():
    modeller = {}
    for anahtar, dosya_adi in MODEL_DOSYALARI.items():
        try:
            modeller[anahtar] = joblib.load(dosya_adi)
        except FileNotFoundError:
            modeller[anahtar] = None
    return modeller
