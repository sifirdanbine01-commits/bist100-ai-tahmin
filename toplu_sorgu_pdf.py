"""
TOPLU_SORGU_PDF.PY
================
Bugün açılmış pozisyonların (acik_pozisyonlar.json, bugünün tarihi)
sembollerini alır, her biri için sorgu.py'deki TAM metin analizini
(logla=False ile, tekrar kayıt yazmadan) yeniden üretir ve bunları
sayfa başına 4 hisse sığacak şekilde PDF'e döker.
"""

import os
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from durum import durumu_oku
from telegram_bildirim import telegram_dosya_gonder, telegram_mesaj_gonder
from pozisyonlar import pozisyonlari_oku
from sorgu import sorgula

CIKTI_DOSYA = 'toplu_sorgu_raporu.pdf'
SAYFA_BASINA_HISSE = 4


def bugun_acilan_sembolleri_bul(egitim_tarihi):
    pozisyonlar = pozisyonlari_oku()
    semboller = [
        sembol for sembol, bilgi in pozisyonlar.items()
        if str(bilgi['giris_tarihi']) == str(egitim_tarihi)
    ]
    return sorted(semboller)


def mesaji_pdf_formatina_cevir(mesaj):
    """Telegram HTML formatındaki mesajı (bold + \n) reportlab Paragraph'ın
    anlayacağı hâle çevirir (<b> zaten uyumlu, \n -> <br/>)."""
    return mesaj.replace("\n", "<br/>")


def pdf_olustur(semboller, egitim_tarihi):
    doc = SimpleDocTemplate(
        CIKTI_DOSYA, pagesize=A4,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
    )
    stiller = getSampleStyleSheet()
    kutu_stili = ParagraphStyle(
        'Kutu', parent=stiller['Normal'], fontSize=9, leading=12,
    )

    icerik = []
    baslik = Paragraph(f"Toplu Sorgu Raporu — {egitim_tarihi} durumu", stiller['Title'])
    icerik.append(baslik)
    icerik.append(Spacer(1, 0.4 * cm))

    for i, sembol in enumerate(semboller):
        mesaj = sorgula(sembol, logla=False)
        pdf_metni = mesaji_pdf_formatina_cevir(mesaj)

        hisse_paragrafi = Paragraph(pdf_metni, kutu_stili)
        kutu_tablosu = Table([[hisse_paragrafi]], colWidths=[17 * cm])
        kutu_tablosu.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1f4e79')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7f9fc')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        icerik.append(kutu_tablosu)
        icerik.append(Spacer(1, 0.4 * cm))

        # Sayfa başına SAYFA_BASINA_HISSE tane sığdır
        if (i + 1) % SAYFA_BASINA_HISSE == 0 and (i + 1) < len(semboller):
            icerik.append(PageBreak())

    doc.build(icerik)
    return CIKTI_DOSYA


if __name__ == "__main__":
    durum = durumu_oku()
    if durum is None:
        telegram_mesaj_gonder("⚠️ Henüz hiç model eğitilmedi.")
        exit(0)

    egitim_tarihi = pd.Timestamp(durum['egitim_tarihi']).date()
    semboller = bugun_acilan_sembolleri_bul(egitim_tarihi)

    if not semboller:
        telegram_mesaj_gonder(
            f"📄 <b>Toplu Sorgu PDF</b>\n\n"
            f"{egitim_tarihi} tarihinde açılmış pozisyon bulunamadı."
        )
    else:
        dosya = pdf_olustur(semboller, egitim_tarihi)
        telegram_dosya_gonder(
            dosya,
            caption=f"📄 Toplu Sorgu Raporu ({egitim_tarihi}) — {len(semboller)} hisse, detaylı analizlerle"
        )
        print(f"PDF oluşturuldu ve gönderildi: {dosya}")
