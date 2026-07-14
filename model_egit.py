"""
ORTAK MODEL EĞİTİM MODÜLÜ
===========================
Tek bir yerden hem sınıflandırma (başarılı mı) hem regresyon
(ne kadar hareket eder) modelini eğitir. Son 3-4 yıla üstel
olarak daha fazla ağırlık verir (eski veri tamamen atılmaz,
ama güncel "tahtacı karakteri" daha baskın olur).
"""

import numpy as np
import joblib
from lightgbm import LGBMClassifier, LGBMRegressor

from gunluk_ozellik_seti import OZELLIK_KOLONLARI


def yakinlik_agirligi_hesapla(tarihler, referans_tarih, yari_omur_yil=3.5):
    """
    referans_tarih'e ne kadar yakınsa ağırlık o kadar 1'e yaklaşır.
    yari_omur_yil: kaç yılda ağırlık yarıya iner (varsayılan 3.5 yıl)
    """
    gun_farki = (referans_tarih - tarihler).dt.days.values
    agirlik = 0.5 ** (gun_farki / (365 * yari_omur_yil))
    return np.clip(agirlik, 0.05, 1.0)  # çok eski veri de tamamen sıfırlanmasın


def modelleri_egit(egitim_df, referans_tarih):
    """
    egitim_df: 'tarih' kolonu + OZELLIK_KOLONLARI + 'basarili' + 'getiri_yuzde'
    Döndürür: (siniflandirma_model, regresyon_model)
    """
    agirliklar = yakinlik_agirligi_hesapla(egitim_df['tarih'], referans_tarih)

    X = egitim_df[OZELLIK_KOLONLARI]
    y_sinif = egitim_df['basarili']
    y_regresyon = egitim_df['getiri_yuzde']

    siniflandirma_model = LGBMClassifier(
        n_estimators=150, max_depth=5, learning_rate=0.05,
        min_child_samples=20, verbose=-1
    )
    siniflandirma_model.fit(X, y_sinif, sample_weight=agirliklar)

    regresyon_model = LGBMRegressor(
        n_estimators=150, max_depth=5, learning_rate=0.05,
        min_child_samples=20, verbose=-1
    )
    regresyon_model.fit(X, y_regresyon, sample_weight=agirliklar)

    return siniflandirma_model, regresyon_model


def modelleri_kaydet(siniflandirma_model, regresyon_model,
                      yol_siniflandirma='model_siniflandirma.pkl',
                      yol_regresyon='model_regresyon.pkl'):
    joblib.dump(siniflandirma_model, yol_siniflandirma)
    joblib.dump(regresyon_model, yol_regresyon)


def modelleri_yukle(yol_siniflandirma='model_siniflandirma.pkl',
                     yol_regresyon='model_regresyon.pkl'):
    siniflandirma_model = joblib.load(yol_siniflandirma)
    regresyon_model = joblib.load(yol_regresyon)
    return siniflandirma_model, regresyon_model
