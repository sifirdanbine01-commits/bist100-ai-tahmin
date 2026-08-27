"""
AYLIK_RAPOR.PY
================
pozisyon_gecmisi.csv içindeki KAPANMIŞ işlemleri (çıkış tarihine göre,
belirtilen ay/yıl için) özetler + o ay İÇİNDE AÇILMIŞ ama henüz
sonuçlanmamış (hâlâ açık) pozisyonları ayrı bir bölümde gösterir +
BIST100/BIST30 endekslerinin o ay ne kadar hareket ettiğini kıyaslama
olarak ekler.
"""

import os
import calendar
from datetime import datetime
import pandas as pd
import yfinance as yf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from telegram_bildirim import telegram_dosya_gonder, telegram_mesaj_gonder
from pozisyonlar import pozisyonlari_oku

GECMIS_DOSYASI = 'pozisyon_gecmisi.csv'
CIKTI_DOSYA = 'aylik_rapor.pdf'

AY_ISIMLERI = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}

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


def kapanan_ay_verisini_getir(yil, ay):
    if not os.path.exists(GECMIS_DOSYASI):
        return pd.DataFrame()
    df = pd.read_csv(GECMIS_DOSYASI)
    df['cikis_tarihi'] = pd.to_datetime(df['cikis_tarihi'])
    df_ay = df[(df['cikis_tarihi'].dt.year == yil) & (df['cikis_tarihi'].dt.month == ay)]
    return df_ay.sort_values('cikis_tarihi')


def acik_ay_verisini_getir(yil, ay):
    pozisyonlar = pozisyonlari_oku()
    satirlar = []
    for sembol, bilgi in pozisyonlar.items():
        giris_tarihi = pd.Timestamp(bilgi['giris_tarihi'])
        if giris_tarihi.year == yil and giris_tarihi.month == ay:
            satirlar.append({
                'sembol': sembol,
                'giris_tarihi': giris_tarihi,
                'giris_fiyat': bilgi['giris_fiyat'],
                'hedef': bilgi['hedef'],
                'stop': bilgi['stop'],
            })
    df_acik = pd.DataFrame(satirlar)
    if not df_acik.empty:
        df_acik = df_acik.sort_values('giris_tarihi')
    return df_acik


def endeks_degisimini_hesapla(sembol, yil, ay):
    """Bir ayın ilk ve son işlem gününün kapanışına göre yüzde değişim
    hesaplar. Veri yoksa None döner."""
    try:
        ay_baslangic = f"{yil}-{ay:02d}-01"
        son_gun = calendar.monthrange(yil, ay)[1]
        ay_bitis = f"{yil}-{ay:02d}-{son_gun:02d}"

        df = yf.download(sembol, start=ay_baslangic, end=ay_bitis, interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 2:
            return None

        ilk_kapanis = float(df['Close'].iloc[0])
        son_kapanis = float(df['Close'].iloc[-1])
        return (son_kapanis / ilk_kapanis - 1) * 100
    except Exception as e:
        print(f"  ⚠️ {sembol} endeks verisi alınamadı: {e}")
        return None


def pdf_olustur(df_kapanan, df_acik, yil, ay, bist100_degisim, bist30_degisim):
    doc = SimpleDocTemplate(
        CIKTI_DOSYA, pagesize=A4,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
    )
    baslik_stili = ParagraphStyle('Baslik', fontName=FONT_BOLD, fontSize=15, leading=19, spaceAfter=10)
    altbaslik_stili = ParagraphStyle('AltBaslik', fontName=FONT_BOLD, fontSize=11, leading=14, spaceAfter=6, spaceBefore=10)
    ozet_stili = ParagraphStyle('Ozet', fontName=FONT_NORMAL, fontSize=10, leading=15)
    not_stili = ParagraphStyle('Not', fontName=FONT_NORMAL, fontSize=8, leading=11, textColor=colors.HexColor('#555555'))

    icerik = []
    icerik.append(Paragraph(f"Aylık İşlem Raporu — {AY_ISIMLERI[ay]} {yil}", baslik_stili))

    # --- PİYASA KARŞILAŞTIRMASI ---
    icerik.append(Paragraph("Piyasa Karşılaştırması", altbaslik_stili))

    bist100_metni = f"%{bist100_degisim:+.2f}" if bist100_degisim is not None else "veri alınamadı"
    bist30_metni = f"%{bist30_degisim:+.2f}" if bist30_degisim is not None else "veri alınamadı"

    ortalama_getiri_kapanan = df_kapanan['getiri_yuzde'].mean() if len(df_kapanan) > 0 else None
    ort_metni = f"%{ortalama_getiri_kapanan:+.2f}" if ortalama_getiri_kapanan is not None else "kapanan işlem yok"

    piyasa_metni = (
        f"<b>BIST100 (XU100) bu ay:</b> {bist100_metni}<br/>"
        f"<b>BIST30 (XU030) bu ay:</b> {bist30_metni}<br/>"
        f"<b>Sistemin ortalama işlem getirisi:</b> {ort_metni}"
    )
    icerik.append(Paragraph(piyasa_metni, ozet_stili))
    icerik.append(Spacer(1, 0.3 * cm))

    # --- KAPANAN İŞLEMLER ---
    toplam = len(df_kapanan)
    icerik.append(Paragraph(f"Kapanan İşlemler ({toplam})", altbaslik_stili))

    if toplam > 0:
        hedef_sayisi = int((df_kapanan['sonuc'] == 'HEDEF').sum())
        stop_sayisi = int((df_kapanan['sonuc'] == 'STOP').sum())
        zaman_asimi_sayisi = int((df_kapanan['sonuc'] == 'ZAMAN_ASIMI').sum())
        basari_orani = (hedef_sayisi / toplam * 100)
        en_iyi = df_kapanan['getiri_yuzde'].max()
        en_kotu = df_kapanan['getiri_yuzde'].min()
        kazanan_oran = (df_kapanan['getiri_yuzde'] > 0).mean() * 100

        ozet_metni = (
            f"<b>Hedefe ulaşan:</b> {hedef_sayisi} &nbsp;&nbsp; "
            f"<b>Stop olan:</b> {stop_sayisi} &nbsp;&nbsp; "
            f"<b>Süre dolan:</b> {zaman_asimi_sayisi}<br/>"
            f"<b>Hedef başarı oranı:</b> %{basari_orani:.1f} &nbsp;&nbsp; "
            f"<b>Kazanan işlem oranı:</b> %{kazanan_oran:.1f}<br/>"
            f"<b>Ortalama getiri:</b> {ort_metni} &nbsp;&nbsp; "
            f"<b>En iyi:</b> %{en_iyi:.2f} &nbsp;&nbsp; "
            f"<b>En kötü:</b> %{en_kotu:.2f}"
        )
        icerik.append(Paragraph(ozet_metni, ozet_stili))
        icerik.append(Spacer(1, 0.3 * cm))

        tablo_veri = [["Sembol", "Giriş T.", "Giriş", "Çıkış T.", "Çıkış", "Sonuç", "Getiri %"]]
        for _, row in df_kapanan.iterrows():
            tablo_veri.append([
                row['sembol'],
                pd.Timestamp(row['giris_tarihi']).strftime('%d.%m.%Y'),
                f"{row['giris_fiyat']:.2f}",
                row['cikis_tarihi'].strftime('%d.%m.%Y'),
                f"{row['cikis_fiyat']:.2f}",
                row['sonuc'],
                f"{row['getiri_yuzde']:+.2f}",
            ])

        tablo = Table(tablo_veri, repeatRows=1)
        stil_komutlari = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NORMAL),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
        ]
        for i, (_, row) in enumerate(df_kapanan.iterrows(), start=1):
            renk = colors.HexColor('#1e8449') if row['getiri_yuzde'] > 0 else colors.HexColor('#c0392b')
            stil_komutlari.append(('TEXTCOLOR', (6, i), (6, i), renk))
        tablo.setStyle(TableStyle(stil_komutlari))
        icerik.append(tablo)
    else:
        icerik.append(Paragraph("Bu ay kapanmış işlem bulunmuyor.", ozet_stili))

    # --- HÂLÂ AÇIK OLAN POZİSYONLAR ---
    icerik.append(Paragraph(f"Hâlâ Açık Olan Pozisyonlar ({len(df_acik)})", altbaslik_stili))

    if not df_acik.empty:
        icerik.append(Paragraph(
            "Bu pozisyonlar bu ay içinde açıldı, henüz hedefe/stop'a ulaşmadı veya "
            "süresi dolmadı. İstatistiklere dahil edilmemiştir - sonuçlandıklarında, "
            "kapandıkları ayın raporunda görünecekler.",
            ozet_stili
        ))
        icerik.append(Spacer(1, 0.2 * cm))

        tablo_veri2 = [["Sembol", "Giriş T.", "Giriş", "Hedef", "Stop"]]
        for _, row in df_acik.iterrows():
            tablo_veri2.append([
                row['sembol'],
                row['giris_tarihi'].strftime('%d.%m.%Y'),
                f"{row['giris_fiyat']:.2f}",
                f"{row['hedef']:.2f}",
                f"{row['stop']:.2f}",
            ])
        tablo2 = Table(tablo_veri2, repeatRows=1)
        tablo2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8a6d00')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NORMAL),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fdf6e3')]),
        ]))
        icerik.append(tablo2)
    else:
        icerik.append(Paragraph("Bu ay açılmış, hâlâ bekleyen pozisyon bulunmuyor.", ozet_stili))

    icerik.append(Spacer(1, 0.4 * cm))
    icerik.append(Paragraph(
        "Not: Piyasa karşılaştırması BIST100/BIST30 endekslerinin ayın ilk ve son "
        "işlem gününün kapanış fiyatına göre basit yüzde değişimidir. 'Kapanan "
        "İşlemler' istatistikleri sadece sonuçlanmış işlemleri kapsar, sermaye "
        "büyüklüğü/pozisyon boyutlandırma dikkate alınmamıştır. Bu geçmişe dönük "
        "bir simülasyondur, yatırım tavsiyesi değildir.",
        not_stili
    ))

    doc.build(icerik)
    return CIKTI_DOSYA


if __name__ == "__main__":
    simdi = datetime.now()
    yil_env = os.environ.get("RAPOR_YIL", "").strip()
    ay_env = os.environ.get("RAPOR_AY", "").strip()
    yil = int(yil_env) if yil_env else simdi.year
    ay = int(ay_env) if ay_env else simdi.month

    df_kapanan = kapanan_ay_verisini_getir(yil, ay)
    df_acik = acik_ay_verisini_getir(yil, ay)

    print("BIST100 endeks verisi çekiliyor...")
    bist100_degisim = endeks_degisimini_hesapla("XU100.IS", yil, ay)
    print("BIST30 endeks verisi çekiliyor...")
    bist30_degisim = endeks_degisimini_hesapla("XU030.IS", yil, ay)

    if df_kapanan.empty and df_acik.empty:
        telegram_mesaj_gonder(f"📄 {AY_ISIMLERI[ay]} {yil} için ne kapanmış ne de açık pozisyon bulundu.")
    else:
        dosya = pdf_olustur(df_kapanan, df_acik, yil, ay, bist100_degisim, bist30_degisim)
        telegram_dosya_gonder(
            dosya,
            caption=f"📄 Aylık İşlem Raporu — {AY_ISIMLERI[ay]} {yil} "
                    f"({len(df_kapanan)} kapandı, {len(df_acik)} hâlâ açık)"
        )
        print(f"Aylık rapor oluşturuldu: {dosya}")
