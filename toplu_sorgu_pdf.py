"""
TOPLU_SORGU_PDF.PY
================
YENİDEN TARAMA YAPMAZ. Bunun yerine, toplu_sorgu.py'nin BUGÜN
(egitim_tarihi ile aynı gün) açtığı pozisyonları acik_pozisyonlar.json
üzerinden okuyup PDF'e döker. Böylece normal sorgunun gösterdiği
hisselerle PDF'teki hisseler HER ZAMAN birebir aynı olur.
"""

import os
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from durum import durumu_oku
from telegram_bildirim import telegram_dosya_gonder, telegram_mesaj_gonder
from pozisyonlar import pozisyonlari_oku

ciktI_DOSYA = 'toplu_sorgu_raporu.pdf'


def bugun_acilan_pozisyonlari_bul(egitim_tarihi):
    pozisyonlar = pozisyonlari_oku()
    bugunkuler = []

    for sembol, bilgi in pozisyonlar.items():
        if str(bilgi['giris_tarihi']) != str(egitim_tarihi):
            continue

        giris_fiyat = bilgi['giris_fiyat']
        hedef = bilgi['hedef']
        stop = bilgi['stop']
        rr = (hedef - giris_fiyat) / (giris_fiyat - stop) if giris_fiyat > stop else 0

        bugunkuler.append({
            'sembol': sembol,
            'olasilik': bilgi.get('olasilik') or 0,
            'fiyat': giris_fiyat,
            'hedef': hedef,
            'stop': stop,
            'rr': rr,
        })

    bugunkuler.sort(key=lambda x: x['olasilik'], reverse=True)
    return bugunkuler


def pdf_olustur(adaylar, egitim_tarihi):
    doc = SimpleDocTemplate(
        ciktI_DOSYA, pagesize=landscape(A4),
        topMargin=1.5 * cm, bottomMargin=1.5 * cm
    )
    stiller = getSampleStyleSheet()
    icerik = []

    baslik = Paragraph(
        f"Toplu Sorgu Raporu — {egitim_tarihi} durumu",
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

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi']).date()
    adaylar = bugun_acilan_pozisyonlari_bul(egitim_tarihi)

    if not adaylar:
        telegram_mesaj_gonder(
            f"📄 <b>Toplu Sorgu PDF</b>\n\n"
            f"{egitim_tarihi} tarihinde açılmış yeni pozisyon bulunamadı "
            f"(bugün henüz 'Toplu Sorgu (Detayli)' çalışmamış olabilir, "
            f"ya da bugün sinyal çıkmamış olabilir)."
        )
    else:
        dosya = pdf_olustur(adaylar, egitim_tarihi)
        telegram_dosya_gonder(
            dosya,
            caption=f"📄 Toplu Sorgu Raporu ({egitim_tarihi}) — {len(adaylar)} hisse"
        )
        print(f"PDF oluşturuldu ve gönderildi: {dosya}")
