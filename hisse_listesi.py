"""
/hisseler KOMUTU
==================
guncel_veri.csv içinde GERÇEKTEN var olan hisseleri listeler,
ayrıca BIST100_HISSELERI listesinde olup da veride OLMAYANLARI
(çekilememiş olanları) ayrıca gösterir.
"""

import os
import pandas as pd

from veri_cek import BIST100_HISSELERI
from telegram_bildirim import telegram_mesaj_gonder


def hisse_listesi_raporu():
    if not os.path.exists('guncel_veri.csv'):
        return "⚠️ guncel_veri.csv bulunamadı. Önce 'Egit veya Ilerlet' çalıştırılmalı."

    guncel_veri = pd.read_csv('guncel_veri.csv')
    mevcut_hisseler = sorted(guncel_veri['sembol'].unique().tolist())
    beklenen_hisseler = sorted(BIST100_HISSELERI)

    eksik_hisseler = sorted(set(beklenen_hisseler) - set(mevcut_hisseler))

    mesaj = (
        f"📋 <b>Hisse Listesi Durumu</b>\n\n"
        f"Beklenen (BIST100_HISSELERI listesi): {len(beklenen_hisseler)}\n"
        f"Sistemde gerçekten VAR olan: {len(mevcut_hisseler)}\n"
        f"Eksik/çekilememiş: {len(eksik_hisseler)}\n\n"
    )

    if eksik_hisseler:
        mesaj += f"⚠️ <b>Eksik Hisseler:</b>\n{', '.join(eksik_hisseler)}\n\n"

    mesaj += f"✅ <b>Sorgulanabilir Hisseler:</b>\n{', '.join(mevcut_hisseler)}"

    return mesaj


if __name__ == "__main__":
    mesaj = hisse_listesi_raporu()
    print(mesaj)
    telegram_mesaj_gonder(mesaj)
