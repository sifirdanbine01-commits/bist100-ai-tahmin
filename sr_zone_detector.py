"""
sr_zone_detector.py
====================================================================
Destek / Direnç Zone Tespit Sistemi (hisse-alarm botu için)

KAYNAK: Hasan'ın TradingView Pine Script'i (eğimli trend çizgileri +
yatay S/R seviyeleri, pivot bazlı, temas sayacı).

BU MODÜLÜN EKLEDİĞİ YENİ MANTIK (Pine kodunda YOKTU):
    Pine kodu bir seviye kırılır kırılmaz onu SİLİYORDU.
    Burada artık:
        1) Seviye kırıldığında hemen silinmiyor, "BROKEN" olarak işaretleniyor.
        2) Kırılma sonrası TÜM barlar boyunca (veri sonuna kadar, sınırsız)
           fiyatın o seviyeye geri gelip gelmediği izleniyor.
        3) Geri gelip tepki verdiyse (rol değişimi / polarite flip) ->
           status = "FLIPPED"  (örn. eski direnç artık destek oldu ve
           gerçekten destek gibi davrandı)
        4) Veri sonuna kadar hiç geri gelmediyse -> status = "INVALID"
           (senin dediğin: "hiç tepki almadıysa geçersiz say")
        5) Kırılma sonrası fiyatın o seviyeden en fazla ne kadar
           uzaklaştığı (max_excursion, % olarak) da kaydediliyor ->
           "kırılımda nereye kadar gitmiş" sorusunun cevabı bu.

Bu modül hem EĞİMLİ (slanted) trend çizgilerini hem de YATAY (horizontal)
seviyeleri aynı state-machine mantığıyla işler.

Çıktı: her zone için bir sözlük (dict) listesi -> SQLite'a yazılabilir,
       LightGBM feature'larına dönüştürülebilir.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd
import numpy as np


# ====================================================================
# 1. PIVOT TESPİTİ  (Pine: ta.pivothigh / ta.pivotlow karşılığı)
# ====================================================================

def find_pivots(df: pd.DataFrame, left: int = 10, right: int = 10) -> pd.DataFrame:
    """
    df: 'high', 'low' kolonlarını içeren, index'i 0..n-1 sıralı OHLC dataframe.
    Pine mantığı: bar[i] pivot high ise, high[i] soldaki 'left' bar ve
    sağdaki 'right' bar içindeki en yüksek değerdir (Pine'da pivot,
    right kadar bar sonra "confirm" olur - repaint yoktur, biz de aynı
    şekilde confirm_bar = i, ama bilgi bar_index = i + right'ta netleşir).
    """
    df = df.reset_index(drop=True).copy()
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)

    pivot_high = np.full(n, np.nan)
    pivot_low = np.full(n, np.nan)

    for i in range(left, n - right):
        window_h = highs[i - left:i + right + 1]
        if highs[i] == window_h.max() and np.sum(window_h == highs[i]) == 1:
            pivot_high[i] = highs[i]
        window_l = lows[i - left:i + right + 1]
        if lows[i] == window_l.min() and np.sum(window_l == lows[i]) == 1:
            pivot_low[i] = lows[i]

    df['pivot_high'] = pivot_high
    df['pivot_low'] = pivot_low
    return df


# ====================================================================
# 2. VERİ YAPILARI
# ====================================================================

@dataclass
class Zone:
    """Hem eğimli hem yatay zone'lar için ortak yapı."""
    kind: str                      # "SLANTED" | "HORIZONTAL"
    is_resistance: bool
    start_bar: int
    start_price: float
    end_bar: int                   # yatayda = son temas bar'ı, eğimlide = çizginin son ucu
    end_price: float
    touches: int = 2
    status: str = "ACTIVE"         # ACTIVE -> BROKEN_WATCH -> FLIPPED | INVALID
    break_bar: Optional[int] = None
    break_price: Optional[float] = None
    max_excursion_pct: float = 0.0     # kırılma sonrası en uzak gidiş (fiyatın %kaçı)
    flip_bar: Optional[int] = None
    flip_price: Optional[float] = None
    touch_bars: List[int] = field(default_factory=list)

    def line_value_at(self, bar: int) -> float:
        """Eğimli çizginin belirli bir bar'daki değeri (yatayda sabit fiyat)."""
        if self.kind == "HORIZONTAL":
            return self.end_price
        span = self.end_bar - self.start_bar
        if span <= 0:
            return self.end_price
        return self.start_price + (self.end_price - self.start_price) * (bar - self.start_bar) / span

    def to_dict(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "kind": self.kind,
            "role": "resistance" if self.is_resistance else "support",
            "status": self.status,
            "start_bar": self.start_bar,
            "start_price": round(self.start_price, 4),
            "end_bar": self.end_bar,
            "end_price": round(self.end_price, 4),
            "touches": self.touches,
            "break_bar": self.break_bar,
            "break_price": round(self.break_price, 4) if self.break_price else None,
            "max_excursion_pct": round(self.max_excursion_pct, 2),
            "flip_bar": self.flip_bar,
            "flip_price": round(self.flip_price, 4) if self.flip_price else None,
        }


# ====================================================================
# 3. EĞİMLİ ÇİZGİ SEGMENT GEÇERLİLİK KONTROLÜ (Pine: isSegmentValid)
# ====================================================================

def is_segment_valid(df, old_bar, old_price, new_bar, new_price, is_resistance, tol) -> bool:
    span = new_bar - old_bar
    if span <= 1:
        return True
    for i in range(old_bar + 1, new_bar):
        line_val = old_price + (new_price - old_price) * (i - old_bar) / span
        if is_resistance:
            if df['high'].iloc[i] > line_val + tol:
                return False
        else:
            if df['low'].iloc[i] < line_val - tol:
                return False
    return True


# ====================================================================
# 4. KIRILMA SONRASI SINIRSIZ İLERİ TAKİP
#    (Pine kodunda olmayan, senin istediğin yeni katman)
# ====================================================================

def track_post_break(df: pd.DataFrame, zone: Zone, break_bar: int, tol: float,
                      react_lookahead: int = 3, react_min_move_pct: float = 0.5):
    """
    Bir zone kırıldıktan sonra, veri sonuna kadar (sınırsız ileri) her bar'ı tarar:
      - Fiyat zone seviyesine tekrar dokunmuş mu?
      - Dokunduysa, sonraki birkaç bar içinde zone'dan uzaklaşarak (rejection/tepki)
        tersi yönde hareket etmiş mi? (bu "FLIPPED" için gereken tepki şartı)
      - Kırılma sonrası fiyatın zone'dan en uzak gittiği mesafeyi (max_excursion_pct) kaydeder.

    Not: bu fonksiyon zone.status'u NİHAİ olarak burada belirlemez;
    çağıran ana döngü (process_symbol) her yeni bar geldikçe bu fonksiyonu
    tekrar tekrar çağırıp durumu günceller. Veri biterse ve hâlâ
    "BROKEN_WATCH" ise -> INVALID olarak sonlandırılır (ana döngüde).
    """
    n = len(df)
    level_price = zone.line_value_at(break_bar)

    for i in range(break_bar + 1, n):
        current_level = zone.line_value_at(i) if zone.kind == "SLANTED" else zone.end_price
        # kırılma sonrası max excursion (yüzde olarak) güncelle
        dist_pct = abs(df['close'].iloc[i] - current_level) / current_level * 100
        if zone.is_resistance:
            # kırılma yukarı yönde olmuştu, excursion = ne kadar yükseğe gitti
            excursion = (df['high'].iloc[i] - current_level) / current_level * 100
        else:
            excursion = (current_level - df['low'].iloc[i]) / current_level * 100
        zone.max_excursion_pct = max(zone.max_excursion_pct, excursion)

        touched = (df['low'].iloc[i] <= current_level + tol) and (df['high'].iloc[i] >= current_level - tol)
        if touched:
            # tepki var mı diye react_lookahead bar sonrasına bak
            end_check = min(i + react_lookahead, n - 1)
            if end_check > i:
                future_close = df['close'].iloc[end_check]
                move_pct = (future_close - current_level) / current_level * 100
                if zone.is_resistance:
                    # kırılan direnç artık destek rolünde -> tepki = yukarı sekmesi
                    reacted = move_pct >= react_min_move_pct
                else:
                    reacted = move_pct <= -react_min_move_pct
                if reacted:
                    zone.status = "FLIPPED"
                    zone.flip_bar = i
                    zone.flip_price = float(df['close'].iloc[i])
                    zone.touches += 1
                    zone.touch_bars.append(i)
                    return zone  # flip bulundu, döngüyü bitir

    # veri sonuna kadar hiç geçerli tepki bulunamadı
    zone.status = "INVALID"
    return zone


# ====================================================================
# 5. ANA İŞLEM FONKSİYONU
# ====================================================================

def process_symbol(df: pd.DataFrame, symbol: str,
                    pivot_left: int = 10, pivot_right: int = 10,
                    tolerance_pct: float = 0.3,
                    h_tolerance_pct: float = 0.5,
                    max_active_slanted: int = 4,
                    max_active_horizontal: int = 5) -> List[dict]:
    """
    df: 'high','low','close' kolonlarını içeren OHLC verisi (kronolojik sıralı).
    Dönüş: tüm zone'ların (aktif + kırılmış + flipped + invalid) dict listesi.
    """
    df = find_pivots(df, pivot_left, pivot_right)
    n = len(df)

    slanted_res: List[Zone] = []
    slanted_sup: List[Zone] = []
    horiz_res: List[Zone] = []
    horiz_sup: List[Zone] = []

    ph_prices, ph_bars = [], []
    pl_prices, pl_bars = [], []

    resolved_zones: List[Zone] = []   # FLIPPED / INVALID olarak kesinleşmiş zone'lar

    def tol_at(i):
        return df['close'].iloc[i] * tolerance_pct / 100.0

    def htol_at(i):
        return df['close'].iloc[i] * h_tolerance_pct / 100.0

    # ---- ana bar döngüsü ----
    for i in range(n):
        ph = df['pivot_high'].iloc[i]
        pl = df['pivot_low'].iloc[i]
        tol = tol_at(i)
        htol = htol_at(i)

        # --- EĞİMLİ: yeni pivot high -> direnç çizgisi güncelle/oluştur ---
        if not np.isnan(ph):
            extended = False
            for z in reversed(slanted_res):
                if z.status == "ACTIVE" and i > z.end_bar:
                    line_val = z.line_value_at(i)
                    if abs(ph - line_val) <= tol and is_segment_valid(df, z.end_bar, z.end_price, i, ph, True, tol):
                        z.end_bar, z.end_price = i, ph
                        z.touches += 1
                        z.touch_bars.append(i)
                        extended = True
                        break
            if not extended:
                for j in reversed(range(len(ph_prices))):
                    old_price, old_bar = ph_prices[j], ph_bars[j]
                    if ph < old_price and is_segment_valid(df, old_bar, old_price, i, ph, True, tol):
                        if len(slanted_res) >= max_active_slanted:
                            weakest = min(slanted_res, key=lambda z: z.touches)
                            slanted_res.remove(weakest)
                        slanted_res.append(Zone("SLANTED", True, old_bar, old_price, i, ph))
                        break
            ph_prices.append(ph); ph_bars.append(i)
            if len(ph_prices) > 60:
                ph_prices.pop(0); ph_bars.pop(0)

            # --- YATAY DİRENÇ ---
            matched = False
            for z in horiz_res:
                if z.status == "ACTIVE" and abs(ph - z.end_price) <= htol:
                    z.end_price = (z.end_price + ph) / 2.0
                    z.end_bar = i
                    z.touches += 1
                    z.touch_bars.append(i)
                    matched = True
                    break
            if not matched:
                if len(horiz_res) >= max_active_horizontal:
                    weakest = min([z for z in horiz_res if z.status == "ACTIVE"],
                                  key=lambda z: z.touches, default=None)
                    if weakest:
                        horiz_res.remove(weakest)
                horiz_res.append(Zone("HORIZONTAL", True, i, ph, i, ph, touches=1))

        # --- EĞİMLİ: yeni pivot low -> destek çizgisi güncelle/oluştur ---
        if not np.isnan(pl):
            extended = False
            for z in reversed(slanted_sup):
                if z.status == "ACTIVE" and i > z.end_bar:
                    line_val = z.line_value_at(i)
                    if abs(pl - line_val) <= tol and is_segment_valid(df, z.end_bar, z.end_price, i, pl, False, tol):
                        z.end_bar, z.end_price = i, pl
                        z.touches += 1
                        z.touch_bars.append(i)
                        extended = True
                        break
            if not extended:
                for j in reversed(range(len(pl_prices))):
                    old_price, old_bar = pl_prices[j], pl_bars[j]
                    if pl > old_price and is_segment_valid(df, old_bar, old_price, i, pl, False, tol):
                        if len(slanted_sup) >= max_active_slanted:
                            weakest = min(slanted_sup, key=lambda z: z.touches)
                            slanted_sup.remove(weakest)
                        slanted_sup.append(Zone("SLANTED", False, old_bar, old_price, i, pl))
                        break
            pl_prices.append(pl); pl_bars.append(i)
            if len(pl_prices) > 60:
                pl_prices.pop(0); pl_bars.pop(0)

            # --- YATAY DESTEK ---
            matched = False
            for z in horiz_sup:
                if z.status == "ACTIVE" and abs(pl - z.end_price) <= htol:
                    z.end_price = (z.end_price + pl) / 2.0
                    z.end_bar = i
                    z.touches += 1
                    z.touch_bars.append(i)
                    matched = True
                    break
            if not matched:
                if len(horiz_sup) >= max_active_horizontal:
                    weakest = min([z for z in horiz_sup if z.status == "ACTIVE"],
                                  key=lambda z: z.touches, default=None)
                    if weakest:
                        horiz_sup.remove(weakest)
                horiz_sup.append(Zone("HORIZONTAL", False, i, pl, i, pl, touches=1))

        # --- KIRILMA KONTROLÜ (silme yerine BROKEN_WATCH'a al) ---
        close_i = df['close'].iloc[i]
        for pool, is_res in [(slanted_res, True), (slanted_sup, False),
                              (horiz_res, True), (horiz_sup, False)]:
            for z in list(pool):
                if z.status != "ACTIVE":
                    continue
                lvl = z.line_value_at(i)
                broke = (close_i > lvl + tol) if is_res else (close_i < lvl - tol)
                if broke:
                    z.status = "BROKEN_WATCH"
                    z.break_bar = i
                    z.break_price = float(close_i)
                    track_post_break(df, z, i, tol if z.kind == "SLANTED" else htol)
                    pool.remove(z)
                    resolved_zones.append(z)

    # --- döngü bitti: hâlâ ACTIVE olanlar + resolved olanlar birleştir ---
    all_zones = slanted_res + slanted_sup + horiz_res + horiz_sup + resolved_zones
    return [z.to_dict(symbol) for z in all_zones]


# ====================================================================
# 6. LightGBM İÇİN FEATURE ÇIKARIMI
# ====================================================================

def zones_to_features(zones: List[dict], current_price: float) -> dict:
    """
    Zone listesinden, en güncel bar için LightGBM'e verilecek özet feature'lar üretir.
    hisse-alarm botunun feature pipeline'ına eklenebilir.
    """
    active = [z for z in zones if z["status"] == "ACTIVE"]
    flipped = [z for z in zones if z["status"] == "FLIPPED"]
    invalid = [z for z in zones if z["status"] == "INVALID"]

    def nearest(zlist, role):
        cands = [z for z in zlist if z["role"] == role]
        if not cands:
            return None
        return min(cands, key=lambda z: abs(z["end_price"] - current_price))

    nearest_active_support = nearest(active, "support")
    nearest_active_resistance = nearest(active, "resistance")

    return {
        "sr_active_support_count": len([z for z in active if z["role"] == "support"]),
        "sr_active_resistance_count": len([z for z in active if z["role"] == "resistance"]),
        "sr_flipped_count": len(flipped),
        "sr_invalid_count": len(invalid),
        "sr_nearest_support_price": nearest_active_support["end_price"] if nearest_active_support else None,
        "sr_nearest_support_touches": nearest_active_support["touches"] if nearest_active_support else 0,
        "sr_nearest_resistance_price": nearest_active_resistance["end_price"] if nearest_active_resistance else None,
        "sr_nearest_resistance_touches": nearest_active_resistance["touches"] if nearest_active_resistance else 0,
        "sr_max_recorded_excursion_pct": max([z["max_excursion_pct"] for z in zones], default=0.0),
    }


# ====================================================================
# 7. ÖRNEK KULLANIM
# ====================================================================

if __name__ == "__main__":
    # Örnek: elinizdeki yfinance/kap verisini DataFrame olarak yükleyip çağırın
    # df = pd.read_csv("DAPGM.csv")  # 'high','low','close' kolonları olmalı
    # zones = process_symbol(df, "DAPGM")
    # feats = zones_to_features(zones, current_price=df['close'].iloc[-1])
    # print(feats)
    print("Modül hazır. process_symbol(df, symbol) ile kullanın.")
