"""
DURUM YÖNETİMİ
===============
"Model şu an hangi tarihe kadar öğrendi" bilgisini bir dosyada saklar.
Bu dosya her /egit veya /ilerlet sonrası güncellenir ve git commit
ile repoya geri yazılır - böylece bir sonraki çalıştırmada hatırlanır.
"""

import json
import os

DURUM_DOSYASI = 'durum.json'


def durumu_oku():
    if not os.path.exists(DURUM_DOSYASI):
        return None
    with open(DURUM_DOSYASI, 'r') as f:
        return json.load(f)


def durumu_kaydet(egitim_tarihi, ornek_sayisi=None):
    durum = {
        'egitim_tarihi': str(egitim_tarihi),
        'ornek_sayisi': ornek_sayisi,
    }
    with open(DURUM_DOSYASI, 'w') as f:
        json.dump(durum, f, indent=2)
    return durum
