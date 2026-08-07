"""
TOPLU_SORGU_PDF.PY
=====================
toplu_sorgu.py ile aynı adayları bulur, her biri için sorgu.py'deki
tam analizi çalıştırır, ÖZETİNİ çıkarıp sayfa başına 4 kart (2x2
grid) halinde tek bir PDF'e basar ve Telegram'a dosya olarak gönderir.
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

MARGIN = 10
GAP = 8
CARD_W = 91
CARD_H = 128

# DejaVu Sans'ta bulunmayan renkli emojileri temizler (📍🎯🛑💰🔍📐📊🔮 vb.)
# ✓ (U+2713), ℹ (U+2139), ⚠ (U+26A0) fontta VAR, bunlar korunuyor.
DESTEKLENMEYEN_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F1E0-\U0001F1FF]+",
    flags=re.UNICODE,
)


def emoji_temizle(metin):
    return DESTEKLENMEYEN_EMOJI_RE.sub("", metin).strip()


def ozet_cikar(sembol, mesaj):
    """Tam sorgu mesajından PDF kartı için özet alanları çıkarır."""
    if "LONG İÇİN RİSKLİ" in mesaj:
        return {
            "sembol": sembol,
            "riskli": True,
            "not_": "Trend yönü şu an AŞAĞI. Sistem sadece LONG fırsat önerir, bu hissede şu an risk var.",
        }

    def bul(pattern, varsayilan="-"):
        m = re.search(pattern, mesaj)
        return m.group(1) if m else varsayilan

    olasilik = bul(r"Başarı Olasılığı: %(\d+)")
    hareket = bul(r"Beklenen Hareket: %([\d.]+)")
    guncel = bul(r"Güncel: ([\d.]+) TL")
    hedef = bul(r"Hedef: ([\d.]+) TL")
    stop = bul(r"Stop: ([\d.]+) TL")
    rr = bul(r"R/R: 1:([\d.]+)")

    # Tüm "Bağlam" bloğunu (direnç/destek bölgeleri dahil) tek parça al
    baglam_match = re.search(
        r"Bağlam:\n(.*?)\n\nBaşarı Olasılığı", mesaj, flags=re.DOTALL
    )
    baglam_metni = emoji_temizle(baglam_match.group(1)) if baglam_match else ""

    return {
        "sembol": sembol,
        "riskli": False,
        "olasilik": olasilik,
        "hareket": hareket,
        "guncel": guncel,
        "hedef": hedef,
        "stop": stop,
        "rr": rr,
        "baglam": baglam_metni,
    }


class RaporPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Sayfa {self.page_no()}", align="C")


def kart_ciz(pdf, ozet, x, y):
    pdf.set_draw_color(180, 180, 180)
    pdf.rect(x, y, CARD_W, CARD_H)

    ic_x = x + 4
    ic_w = CARD_W - 8
    pdf.set_xy(ic_x, y + 4)

    pdf.set_font("DejaVu", "B", 13)
    if ozet["riskli"]:
        pdf.set_text_color(180, 0, 0)
        pdf.multi_cell(ic_w, 7, f"{ozet['sembol']} - RISKLI")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9.5)
        pdf.set_xy(ic_x, pdf.get_y() + 2)
        pdf.multi_cell(ic_w, 5, ozet["not_"])
        return

    pdf.multi_cell(ic_w, 7, f"{ozet['sembol']}  (%{ozet['olasilik']})")

    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_xy(ic_x, pdf.get_y() + 1)
    pdf.multi_cell(ic_w, 5, f"Beklenen Hareket: %{ozet['hareket']}")

    pdf.set_xy(ic_x, pdf.get_y() + 2)
    pdf.set_font("DejaVu", "B", 10)
    pdf.multi_cell(ic_w, 5.5,
        f"Guncel: {ozet['guncel']} TL\n"
        f"Hedef:  {ozet['hedef']} TL\n"
        f"Stop:   {ozet['stop']} TL\n"
        f"R/R:    1:{ozet['rr']}"
    )

    # Kalan alanı doldurmak icin butun baglami (direnc/destek dahil) yaz
    baglam_baslangic_y = pdf.get_y() + 2
    kalan_yukseklik = (y + CARD_H - 3) - baglam_baslangic_y

    if ozet["baglam"] and kalan_yukseklik > 8:
        pdf.set_font("DejaVu", "", 7.8)
        pdf.set_text_color(60, 60, 60)
        pdf.set_xy(ic_x, baglam_baslangic_y)

        satir_yuksekligi = 3.6
        maks_satir = max(1, int(kalan_yukseklik / satir_yuksekligi))
        # Yaklasik karakter butcesi: satir basi ~62 karakter
        maks_karakter = maks_satir * 62

        metin = ozet["baglam"]
        if len(metin) > maks_karakter:
            metin = metin[:maks_karakter - 3].rstrip() + "..."

        pdf.multi_cell(ic_w, satir_yuksekligi, metin)
        pdf.set_text_color(0, 0, 0)


def pdf_olustur(ozetler, egitim_tarihi, dosya_adi):
    font_dir = os.path.join(
        os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"
    )

    pdf = RaporPDF(format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_font("DejaVu", "", os.path.join(font_dir, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(font_dir, "DejaVuSans-Bold.ttf"))

    # Kapak sayfası
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_xy(MARGIN, 20)
    pdf.multi_cell(0, 10, "BIST100 Toplu Sorgu Raporu")
    pdf.set_font("DejaVu", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.set_xy(MARGIN, pdf.get_y() + 2)
    pdf.multi_cell(
        0, 6,
        f"Eğitim/veri tarihi: {egitim_tarihi}\n"
        f"Oluşturulma: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"Toplam hisse: {len(ozetler)} | Eşik: %{ESIK*100:.0f}"
    )
    pdf.set_text_color(0, 0, 0)

    # 2x2 grid, sayfa basi 4 kart
    for i, ozet in enumerate(ozetler):
        pozisyon = i % 4
        if pozisyon == 0:
            pdf.add_page()

        col = pozisyon % 2
        row = pozisyon // 2
        x = MARGIN + col * (CARD_W + GAP)
        y = MARGIN + row * (CARD_H + GAP)
        kart_ciz(pdf, ozet, x, y)

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
            f"{len(adaylar)} hisse için özet PDF oluşturuluyor (sayfa başı 4 hisse)."
        )
        telegram_mesaj_gonder(baslik)
        print(baslik)

        ozetler = []
        for sembol, olasilik in adaylar:
            try:
                mesaj = sorgula(sembol)
                ozetler.append(ozet_cikar(sembol, mesaj))
                print(f"✅ {sembol} eklendi (%{olasilik*100:.0f})")
            except Exception as e:
                print(f"⚠️ {sembol} için sorgu başarısız: {e}")
                continue

        if not ozetler:
            telegram_mesaj_gonder("⚠️ PDF oluşturulamadı, hiçbir hisse başarıyla sorgulanamadı.")
        else:
            dosya_adi = f"toplu_sorgu_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            pdf_olustur(ozetler, egitim_tarihi, dosya_adi)
            print(f"PDF oluşturuldu: {dosya_adi}")

            sayfa_sayisi = 1 + -(-len(ozetler) // 4)
            caption = (
                f"📊 Toplu Sorgu Raporu ({egitim_tarihi} durumu)\n"
                f"{len(ozetler)} hisse | {sayfa_sayisi} sayfa | Eşik: %{ESIK*100:.0f}"
            )
            telegram_dosya_gonder(dosya_adi, caption=caption)
