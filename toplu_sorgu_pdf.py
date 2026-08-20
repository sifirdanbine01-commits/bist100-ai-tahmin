"""
TOPLU_SORGU_PDF.PY
================
toplu_sorgu.py ile AYNI filtreleme mantığını (eşik + açık pozisyon
atlama + R/R >= MIN_RR) kullanarak adayları bulur, tek bir PDF
raporunda toplayıp Telegram'a dosya olarak gönderir.
NOT: Pozisyon açmaz, sadece rapor üretir - pozisyon açma işini
toplu_sorgu.py yapıyor. İkisini aynı gün art arda çalıştırırsan
aynı listeyi görürsün.
"""

import os
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from durum import durumu_oku
from model_egit import modelleri_yukle
from telegram_bildirim import telegram_dosya_gonder, telegram_mesaj_gonder
from toplu_sorgu import adaylari_bul, MIN_RR, ESIK

ciktI_DOSYA = 'toplu_sorgu_raporu.pdf'


def pdf_olustur(adaylar, egitim_tarihi):
    doc = SimpleDocTemplate(
        ciktI_DOSYA, pagesize=landscape(A4),
        topMargin=1.5 * cm, bottomMargin=1.5 * cm
    )
    stiller = getSampleStyleSheet()
    icerik = []

    baslik = Paragraph(
        f"Toplu Sorgu Raporu — {egitim_tarihi} durumu "
        f"(Eşik: %{ESIK*100:.0f}, Min R/R: 1:{MIN_RR})",
        stiller['Title']
    )
    icerik.append(baslik)
    icerik.append(Spacer(1, 0.5 * cm))

    tablo_veri = [["Sembol", "Olasılık", "Fiyat", "Hedef", "Stop", "R/R", "Hedef %"]]
    for aday in adaylar:
        hedef_yuzde = (aday['hedef'] / aday['fiyat'] - 1) * 100
        tablo_veri.append([
            aday['sembol'],
            f"%{aday['olasilik']*100:.0f}",
            f"{aday['fiyat']:.2f}",
            f"{aday['hedef']:.2f}",
            f"{aday['stop']:.2f}",
            f"1:{aday['rr']:.2f}",
            f"+%{hedef_yuzde:.1f}",
        ])

    tablo = Table(tablo_veri, repeatRows=1)
    tablo.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
    ]))
    icerik.append(tablo)

    icerik.append(Spacer(1, 0.5 * cm))
    not_metni = Paragraph(
        "⚠️ Bu geçmişe dönük bir simülasyondur, yatırım tavsiyesi değildir.",
        stiller['Normal']
    )
    icerik.append(not_metni)

    doc.build(icerik)
    return ciktI_DOSYA


if __name__ == "__main__":
    durum = durumu_oku()
    if durum is None:
        telegram_mesaj_gonder("⚠️ Henüz hiç model eğitilmedi.")
        exit(0)

    if not os.path.exists('guncel_veri.parquet'):
        telegram_mesaj_gonder("⚠️ guncel_veri.parquet bulunamadı.")
        exit(0)

    guncel_veri = pd.read_parquet('guncel_veri.parquet')
    guncel_veri['tarih'] = pd.to_datetime(guncel_veri['tarih'])

    modeller = modelleri_yukle()
    if modeller.get('genel_siniflandirma') is None or modeller.get('genel_regresyon') is None:
        telegram_mesaj_gonder("⚠️ Model bulunamadı.")
        exit(0)

    adaylar, rr_elenen = adaylari_bul(guncel_veri, modeller)
    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi']).date()

    if not adaylar:
        telegram_mesaj_gonder(
            f"📄 <b>Toplu Sorgu PDF</b>\n\n"
            f"Bugün eşiği (%{ESIK*100:.0f}) ve R/R şartını (1:{MIN_RR}) "
            f"birlikte geçen hisse yok, PDF oluşturulmadı."
        )
    else:
        dosya = pdf_olustur(adaylar, egitim_tarihi)
        telegram_dosya_gonder(
            dosya,
            caption=f"📄 Toplu Sorgu Raporu ({egitim_tarihi}) — {len(adaylar)} hisse"
        )
        print(f"PDF oluşturuldu ve gönderildi: {dosya}")
