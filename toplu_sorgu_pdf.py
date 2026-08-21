"""
TOPLU_SORGU_PDF.PY
================
Bugün açılan pozisyonlar için analiz_bilesenleri() ile veri üretir.
İÇERİK: bağlam (renklendirilmiş direnç=kırmızı/destek=yeşil) + başarı
olasılığı + beklenen hareket + güncel/hedef/stop/R:R.
SHAP (destekleyen/azaltan etkenler) ve Fibonacci bölümleri YOK.
Sayfa başına 4 hisse (2x2 ızgara).
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
from sorgu import analiz_bilesenleri

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

RENK_DIRENC = "#c0392b"   # kırmızı
RENK_DESTEK = "#1e8449"   # yeşil
RENK_NORMAL = "#222222"


def kacisli(metin):
    return metin.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bugun_acilan_sembolleri_bul(egitim_tarihi):
    pozisyonlar = pozisyonlari_oku()
    semboller = [
        sembol for sembol, bilgi in pozisyonlar.items()
        if str(bilgi['giris_tarihi']) == str(egitim_tarihi)
    ]
    return sorted(semboller)


def kart_html_uret(veri):
    parcalar = [f"<b>{kacisli(veri['sembol'])}</b> ({veri['tarih']})<br/>"]

    if veri['baglam']:
        for satir in veri['baglam']:
            renk = {'direnc': RENK_DIRENC, 'destek': RENK_DESTEK, 'normal': RENK_NORMAL}[satir['tip']]
            parcalar.append(f'<font color="{renk}">{kacisli(satir["metin"])}</font><br/>')
    else:
        parcalar.append("Belirgin ek yapısal bağlam yok<br/>")

    parcalar.append("<br/>")
    parcalar.append(f"Başarı Olasılığı: %{veri['olasilik']*100:.0f}<br/>")
    parcalar.append(f"Beklenen Hareket: %{veri['beklenen_hareket']:.1f}<br/>")
    parcalar.append("<br/>")
    parcalar.append(f"Güncel: {veri['guncel_fiyat']:.2f} TL<br/>")
    parcalar.append(f"Hedef: {veri['hedef']:.2f} TL<br/>")
    parcalar.append(f"Stop: {veri['stop']:.2f} TL<br/>")
    rr_renk = RENK_NORMAL if veri['rr'] >= 1.5 else RENK_DIRENC
    parcalar.append(f'<font color="{rr_renk}">R/R: 1:{veri["rr"]:.2f}</font><br/>')

    if veri.get('direnc_uyarisi'):
        parcalar.append(f'<font color="{RENK_DIRENC}">{kacisli(veri["direnc_uyarisi"])}</font><br/>')

    return "".join(parcalar)


def pdf_olustur(semboller, egitim_tarihi):
    doc = SimpleDocTemplate(
        CIKTI_DOSYA, pagesize=A4,
        topMargin=0.8 * cm, bottomMargin=0.8 * cm,
        leftMargin=0.8 * cm, rightMargin=0.8 * cm,
    )

    baslik_stili = ParagraphStyle('Baslik', fontName=FONT_BOLD, fontSize=13, leading=16, spaceAfter=8)
    kart_stili = ParagraphStyle('Kart', fontName=FONT_NORMAL, fontSize=7.2, leading=9.6)

    icerik = [Paragraph(f"Toplu Sorgu Raporu — {egitim_tarihi} durumu", baslik_stili), Spacer(1, 0.2 * cm)]

    kartlar = []
    for sembol in semboller:
        veri = analiz_bilesenleri(sembol, logla=False)
        if veri.get('hata'):
            kartlar.append(Paragraph(f"<b>{sembol}</b><br/>{kacisli(veri['hata'])}", kart_stili))
            continue
        if veri['veto']:
            kartlar.append(Paragraph(
                f"<b>{sembol}</b> ({veri['tarih']})<br/>"
                f'<font color="{RENK_DIRENC}">Trend AŞAĞI - LONG için riskli, sinyal verilmedi.</font>',
                kart_stili
            ))
            continue
        kartlar.append(Paragraph(kart_html_uret(veri), kart_stili))

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
        telegram_mesaj_gonder(f"📄 <b>Toplu Sorgu PDF</b>\n\n{egitim_tarihi} tarihinde açılmış pozisyon bulunamadı.")
    else:
        dosya = pdf_olustur(semboller, egitim_tarihi)
        telegram_dosya_gonder(dosya, caption=f"📄 Toplu Sorgu Raporu ({egitim_tarihi}) — {len(semboller)} hisse")
        print(f"PDF oluşturuldu ve gönderildi: {dosya}")
