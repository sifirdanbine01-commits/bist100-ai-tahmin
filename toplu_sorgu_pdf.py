"""
TOPLU_SORGU_PDF.PY
================
Bugün açılmış pozisyonların sembollerini alır, her biri için sorgu.py'nin
ürettiği metinden ÖZET bir kart çıkarır (bağlam + temel metrikler),
2x2 ızgara düzeninde (sayfa başına 4 hisse) PDF'e döker.
Türkçe karakterler için DejaVuSans fontu kullanılır.
"""

import os
import re
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from durum import durumu_oku
from telegram_bildirim import telegram_dosya_gonder, telegram_mesaj_gonder
from pozisyonlar import pozisyonlari_oku
from sorgu import sorgula

CIKTI_DOSYA = 'toplu_sorgu_raporu.pdf'

FONT_YOLLARI = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]

FONT_NORMAL = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

for normal_yol, bold_yol in FONT_YOLLARI:
    if os.path.exists(normal_yol) and os.path.exists(bold_yol):
        pdfmetrics.registerFont(TTFont("TRFont", normal_yol))
        pdfmetrics.registerFont(TTFont("TRFont-Bold", bold_yol))
        FONT_NORMAL = "TRFont"
        FONT_BOLD = "TRFont-Bold"
        break


def bugun_acilan_sembolleri_bul(egitim_tarihi):
    pozisyonlar = pozisyonlari_oku()
    semboller = [
        sembol for sembol, bilgi in pozisyonlar.items()
        if str(bilgi['giris_tarihi']) == str(egitim_tarihi)
    ]
    return sorted(semboller)


def ozet_cikar(sembol, mesaj):
    """Tam sorgu mesajından kısa bir özet çıkarır: ilk 2 bağlam satırı +
    temel metrikler (olasılık, hedef, stop, R/R). SHAP ve Fibonacci
    detaylarını atlar, kompakt kalması için."""

    baglam_satirlari = []
    m = re.search(r"📊 Bağlam:\n(.*?)\n\n", mesaj, re.DOTALL)
    if m:
        tum_satirlar = [s.strip() for s in m.group(1).split("\n") if s.strip()]
        baglam_satirlari = tum_satirlar[:2]

    metrik_satirlari = []
    for etiket in ["Başarı Olasılığı:", "💰 Güncel:", "🎯 Hedef:", "🛑 Stop:", "⚖️ R/R:"]:
        m2 = re.search(re.escape(etiket) + r"([^\n]*)", mesaj)
        if m2:
            metrik_satirlari.append(f"{etiket}{m2.group(1).strip()}")

    parcalar = [f"<b>{sembol}</b>"]
    parcalar.extend(metrik_satirlari)
    if baglam_satirlari:
        parcalar.append("—")
        parcalar.extend(baglam_satirlari)

    return "<br/>".join(parcalar)


def pdf_olustur(semboller, egitim_tarihi):
    doc = SimpleDocTemplate(
        CIKTI_DOSYA, pagesize=A4,
        topMargin=1 * cm, bottomMargin=1 * cm,
        leftMargin=1 * cm, rightMargin=1 * cm,
    )

    baslik_stili = ParagraphStyle(
        'Baslik', fontName=FONT_BOLD, fontSize=14, leading=18,
        spaceAfter=10,
    )
    kart_stili = ParagraphStyle(
        'Kart', fontName=FONT_NORMAL, fontSize=8, leading=11,
    )

    icerik = []
    icerik.append(Paragraph(f"Toplu Sorgu Raporu — {egitim_tarihi} durumu", baslik_stili))
    icerik.append(Spacer(1, 0.3 * cm))

    kartlar = []
    for sembol in semboller:
        mesaj = sorgula(sembol, logla=False)
        ozet = ozet_cikar(sembol, mesaj)
        kartlar.append(Paragraph(ozet, kart_stili))

    # 2 sütunlu ızgara - her satırda 2 kart, her sayfada 2 satır (4 kart)
    satirlar = []
    for i in range(0, len(kartlar), 2):
        if i + 1 < len(kartlar):
            satirlar.append([kartlar[i], kartlar[i + 1]])
        else:
            satirlar.append([kartlar[i], ""])

    izgara = Table(satirlar, colWidths=[9.2 * cm, 9.2 * cm], repeatRows=0)
    izgara.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1f4e79')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#1f4e79')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7f9fc')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    icerik.append(izgara)

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
            caption=f"📄 Toplu Sorgu Raporu ({egitim_tarihi}) — {len(semboller)} hisse"
        )
        print(f"PDF oluşturuldu ve gönderildi: {dosya}")
