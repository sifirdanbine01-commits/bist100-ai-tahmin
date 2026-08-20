"""
TOPLU_SORGU_PDF.PY
================
Bugün açılmış pozisyonların sembollerini alır, her biri için sorgu.py'nin
ürettiği TAM mesajı (bağlam, tüm direnç/destek bölgeleri, SHAP, Fibonacci
hedefleri - hiçbir şey kısaltılmadan) küçük fontla 2x2 ızgara düzeninde
(sayfa başına 4 hisse) PDF'e döker. Türkçe karakterler için DejaVuSans.
"""

import os
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


def mesaji_pdf_formatina_cevir(mesaj):
    """Telegram HTML formatındaki mesajı (zaten <b> içeriyor) reportlab
    Paragraph'ın anlayacağı hâle çevirir - sadece satır sonlarını <br/>
    yapar, mevcut <b> etiketlerine dokunmaz."""
    metin = mesaj.replace("&", "&amp;")
    metin = metin.replace("<b>", "@@B_OPEN@@").replace("</b>", "@@B_CLOSE@@")
    metin = metin.replace("<", "&lt;").replace(">", "&gt;")
    metin = metin.replace("@@B_OPEN@@", "<b>").replace("@@B_CLOSE@@", "</b>")
    metin = metin.replace("\n", "<br/>")
    return metin


def pdf_olustur(semboller, egitim_tarihi):
    doc = SimpleDocTemplate(
        CIKTI_DOSYA, pagesize=A4,
        topMargin=0.8 * cm, bottomMargin=0.8 * cm,
        leftMargin=0.8 * cm, rightMargin=0.8 * cm,
    )

    baslik_stili = ParagraphStyle(
        'Baslik', fontName=FONT_BOLD, fontSize=13, leading=16,
        spaceAfter=8,
    )
    kart_stili = ParagraphStyle(
        'Kart', fontName=FONT_NORMAL, fontSize=6.3, leading=8.2,
    )

    icerik = []
    icerik.append(Paragraph(f"Toplu Sorgu Raporu — {egitim_tarihi} durumu", baslik_stili))
    icerik.append(Spacer(1, 0.2 * cm))

    kartlar = []
    for sembol in semboller:
        mesaj = sorgula(sembol, logla=False)
        pdf_metni = mesaji_pdf_formatina_cevir(mesaj)
        kartlar.append(Paragraph(pdf_metni, kart_stili))

    # 2 sütunlu ızgara - her satırda 2 kart, her sayfada 2 satır (4 kart)
    satirlar = []
    for i in range(0, len(kartlar), 2):
        if i + 1 < len(kartlar):
            satirlar.append([kartlar[i], kartlar[i + 1]])
        else:
            satirlar.append([kartlar[i], ""])

    izgara = Table(satirlar, colWidths=[9.6 * cm, 9.6 * cm], repeatRows=0)
    izgara.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1f4e79')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#1f4e79')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7f9fc')),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
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
