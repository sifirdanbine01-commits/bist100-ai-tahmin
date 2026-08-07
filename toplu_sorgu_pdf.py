"""
TOPLU_SORGU_PDF.PY
=====================
toplu_sorgu.py ile aynı adayları bulur, ama her birini ayrı Telegram
mesajı olarak göndermek yerine hepsini TEK BİR PDF dosyasında
birleştirip Telegram'a dosya (document) olarak gönderir.
Baskı almak için uygundur.
"""

import os
import re
from datetime import datetime

from fpdf import FPDF
import matplotlib

from durum import durumu_oku
from telegram_bildirim import telegram_mesaj_gonder, telegram_dosya_gonder
from sorgu import sorgula
from toplu_sorgu import adaylari_bul

ESIK = float(os.environ.get("TARAMA_ESIK", "0.55"))

HTML_TAG_RE = re.compile(r"<[^>]+>")
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


def metni_temizle(mesaj):
    metin = HTML_TAG_RE.sub("", mesaj)
    metin = EMOJI_RE.sub("", metin)
    return metin.strip()


class RaporPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Sayfa {self.page_no()}", align="C")


def pdf_olustur(adaylar_ve_mesajlar, egitim_tarihi, dosya_adi):
    font_dir = os.path.join(
        os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"
    )

    pdf = RaporPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("DejaVu", "", os.path.join(font_dir, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(font_dir, "DejaVuSans-Bold.ttf"))

    pdf.add_page()
    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, "BIST100 Toplu Sorgu Raporu", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        0, 6,
        f"Eğitim/veri tarihi: {egitim_tarihi} | "
        f"Oluşturulma: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    for sembol, olasilik, mesaj in adaylar_ve_mesajlar:
        temiz_metin = metni_temizle(mesaj)

        pdf.set_font("DejaVu", "B", 12)
        pdf.set_fill_color(235, 235, 235)
        pdf.cell(0, 9, f"{sembol} - %{olasilik*100:.0f}", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(1)

        pdf.set_font("DejaVu", "", 9.5)
        pdf.multi_cell(0, 5, temiz_metin)
        pdf.ln(4)

    pdf.output(dosya_adi)
    return dosya_adi


if __name__ == "__main__":
    durum = durumu_oku()
    egitim_tarihi = durum["egitim_tarihi"] if durum else "bilinmiyor"

    adaylar, hata = adaylari_bul()

    if hata:
        telegram_mesaj_gonder(hata)
        print(hata)
    elif not adaylar:
        mesaj = f"📊 <b>Toplu Sorgu (PDF)</b>\n\nBugün eşiği (%{ESIK*100:.0f}) geçen yeni hisse yok."
        telegram_mesaj_gonder(mesaj)
        print(mesaj)
    else:
        baslik = (
            f"📄 <b>Toplu Sorgu (PDF) hazırlanıyor...</b>\n"
            f"{len(adaylar)} hisse için detaylı analiz tek PDF'te birleştiriliyor."
        )
        telegram_mesaj_gonder(baslik)
        print(baslik)

        adaylar_ve_mesajlar = []
        for sembol, olasilik in adaylar:
            try:
                mesaj = sorgula(sembol)
                adaylar_ve_mesajlar.append((sembol, olasilik, mesaj))
                print(f"✅ {sembol} eklendi (%{olasilik*100:.0f})")
            except Exception as e:
                print(f"⚠️ {sembol} için sorgu başarısız: {e}")
                continue

        if not adaylar_ve_mesajlar:
            telegram_mesaj_gonder("⚠️ PDF oluşturulamadı, hiçbir hisse başarıyla sorgulanamadı.")
        else:
            dosya_adi = f"toplu_sorgu_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            pdf_olustur(adaylar_ve_mesajlar, egitim_tarihi, dosya_adi)
            print(f"PDF oluşturuldu: {dosya_adi}")

            caption = (
                f"📊 Toplu Sorgu Raporu ({egitim_tarihi} durumu)\n"
                f"{len(adaylar_ve_mesajlar)} hisse | Eşik: %{ESIK*100:.0f}"
            )
            telegram_dosya_gonder(dosya_adi, caption=caption)
