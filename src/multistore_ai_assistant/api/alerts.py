"""Alertas automáticos, mostrados ao entrar no chat.

- **Vendas por loja**: últimos 7 dias completos vs. os 7 anteriores. Os limites
  são por segmento (``THRESHOLDS``): a geladaria depende do tempo e varia muito
  mais de semana para semana. Quando o tempo mudou (máxima média ``TEMP_NOTE`` °C
  ou mais, ou ``RAIN_DAYS_NOTE`` dias de chuva a mais/menos), o alerta diz isso
  ("tempo: máxima média 17 °C vs 19 °C, 6 vs 3 dias de chuva"), para não parecer
  um problema da loja o que é só uma semana de chuva.
- **Stock a acabar**: dias de stock = stock atual ÷ consumo diário previsto
  (previsão de vendas × consumo de ingredientes por euro, o mesmo cálculo das
  encomendas sugeridas). Menos de ``MIN_COVER_DAYS`` → aviso.

Tudo corre com o perfil de quem pede: as vendas passam pelo RLS e o stock é
filtrado às lojas visíveis. Os limiares estão afinados para os dados
fictícios: variação semanal (percentis 10–90) de ±11 % no café e na
hamburgueria e de −24 %/+34 % na geladaria; reposição diária, cobertura mediana
de ~1 dia. Numa base real ajustavam-se (p.ex. 0,5 → 2 dias de stock).
O resultado fica em cache ``CACHE_SECONDS`` por âmbito (perfil + marca + loja).
"""
import logging
import threading
import time
from datetime import timedelta

from multistore_ai_assistant.api.permissions import data_role, has_module
from multistore_ai_assistant.data.signals import weather
from multistore_ai_assistant.db.query import run_query
from multistore_ai_assistant.forecast.orders import suggest_orders

log = logging.getLogger("multistore")

# (queda que avisa, queda grave, subida a destacar) por segmento
THRESHOLDS = {"geladaria": (0.25, 0.40, 0.35)}
DEFAULT_THRESHOLDS = (0.08, 0.15, 0.10)
TEMP_NOTE = 2.0
RAIN_DAYS_NOTE = 2
RAIN_MM = 5.0              # dia "de chuva" (o mesmo limite do gerador para a geladaria)
MIN_COVER_DAYS, HIGH_COVER_DAYS = 0.5, 0.35
MAX_STOCK_ALERTS = 6
CACHE_SECONDS = 600

SALES_SQL = """
WITH d AS (SELECT max(sold_at)::date AS last FROM sales)
SELECT st.id, st.name, b.segment, st.district, d.last,
       sum(s.total) FILTER (WHERE s.sold_at::date > d.last - 7)  AS this_week,
       sum(s.total) FILTER (WHERE s.sold_at::date <= d.last - 7) AS last_week
FROM sales s JOIN stores st ON st.id = s.store_id JOIN brands b ON b.id = st.brand_id CROSS JOIN d
WHERE s.sold_at >= d.last - 13
GROUP BY st.id, st.name, b.segment, st.district, d.last
"""

TEXT = {
    "sales_drop": {
        "pt": "{store}: vendas {pct} % abaixo da semana anterior ({now} € vs {prev} €).",
        "en": "{store}: sales {pct}% below the previous week (€{now} vs €{prev}).",
        "es": "{store}: ventas un {pct} % por debajo de la semana anterior ({now} € frente a {prev} €).",
        "fr": "{store} : ventes {pct} % sous la semaine précédente ({now} € contre {prev} €).",
    },
    "weather": {
        "pt": " Tempo: máxima média {now} °C vs {prev} °C, {rain_now} vs {rain_prev} dias de chuva.",
        "en": " Weather: average high {now} °C vs {prev} °C, {rain_now} vs {rain_prev} rainy days.",
        "es": " Tiempo: máxima media {now} °C frente a {prev} °C, {rain_now} frente a {rain_prev} días de lluvia.",
        "fr": " Météo : maximale moyenne {now} °C contre {prev} °C, {rain_now} contre {rain_prev} jours de pluie.",
    },
    "sales_rise": {
        "pt": "{store}: vendas {pct} % acima da semana anterior ({now} €).",
        "en": "{store}: sales {pct}% above the previous week (€{now}).",
        "es": "{store}: ventas un {pct} % por encima de la semana anterior ({now} €).",
        "fr": "{store} : ventes {pct} % au-dessus de la semaine précédente ({now} €).",
    },
    "low_stock": {
        "pt": "{store}: {ingredient} dá para ~{days} dia(s) ({stock} {unit} em stock).",
        "en": "{store}: {ingredient} lasts ~{days} day(s) ({stock} {unit} in stock).",
        "es": "{store}: {ingredient} alcanza para ~{days} día(s) ({stock} {unit} en stock).",
        "fr": "{store} : {ingredient} tient ~{days} jour(s) ({stock} {unit} en stock).",
    },
}

_cache: dict[tuple, tuple[float, list]] = {}
_lock = threading.Lock()


def _fmt(value: float, lang: str, decimals: int = 0) -> str:
    """Número no formato do idioma (espaço/ponto nos milhares, vírgula/ponto nas décimas)."""
    text = f"{value:,.{decimals}f}"
    if lang == "en":
        return text
    return text.replace(",", " ").replace(".", ",")


def message(alert: dict, lang: str) -> str:
    """Texto do alerta no idioma pedido."""
    lang = lang if lang in ("pt", "en", "es", "fr") else "pt"
    a = alert
    if a["type"] == "low_stock":
        return TEXT["low_stock"][lang].format(store=a["store"], ingredient=a["ingredient"], unit=a["unit"],
                                              days=_fmt(a["days"], lang, 1), stock=_fmt(a["stock"], lang, 1))
    text = TEXT[a["type"]][lang].format(store=a["store"], pct=_fmt(abs(a["change_pct"]), lang, 1),
                                        now=_fmt(a["this_week"], lang), prev=_fmt(a["last_week"], lang))
    if a.get("weather"):
        w = a["weather"]
        text += TEXT["weather"][lang].format(now=_fmt(w["temp_now"], lang), prev=_fmt(w["temp_prev"], lang),
                                             rain_now=w["rain_days_now"], rain_prev=w["rain_days_prev"])
    return text


def week_weather(district: str, last) -> dict | None:
    """Tempo nos 7 dias até ``last`` vs os 7 anteriores, só se mudou o bastante para explicar vendas."""
    w = weather()

    def week(offset):
        days = [w[(district, last - timedelta(days=offset + i))] for i in range(7)
                if (district, last - timedelta(days=offset + i)) in w]
        if len(days) < 5:
            return None
        return sum(t for t, _ in days) / len(days), sum(1 for _, rain in days if rain > RAIN_MM)

    now, prev = week(0), week(7)
    if now is None or prev is None:
        return None
    if abs(now[0] - prev[0]) < TEMP_NOTE and abs(now[1] - prev[1]) < RAIN_DAYS_NOTE:
        return None
    return {"temp_now": round(now[0], 1), "temp_prev": round(prev[0], 1),
            "rain_days_now": now[1], "rain_days_prev": prev[1]}


def sales_alerts(user: dict) -> list[dict]:
    """Lojas visíveis com queda (ou subida) de vendas semana a semana."""
    _, rows = run_query(SALES_SQL, user)
    out = []
    for _store_id, name, segment, district, last, this_week, last_week in rows:
        if not this_week or not last_week:
            continue
        drop, drop_high, rise = THRESHOLDS.get(segment, DEFAULT_THRESHOLDS)
        change = float(this_week) / float(last_week) - 1
        if change <= -drop:
            kind, severity = "sales_drop", "high" if change <= -drop_high else "warn"
        elif change >= rise:
            kind, severity = "sales_rise", "info"
        else:
            continue
        alert = {"type": kind, "severity": severity, "store": name, "segment": segment,
                 "change_pct": round(100 * change, 1),
                 "this_week": round(float(this_week), 2), "last_week": round(float(last_week), 2)}
        if district and last and (change_in_weather := week_weather(district, last)):
            alert["weather"] = change_in_weather
        out.append(alert)
    return out


def stock_alerts(user: dict) -> list[dict]:
    """Ingredientes com stock para menos de ``MIN_COVER_DAYS`` dias, nas lojas visíveis."""
    _, stores = run_query("SELECT id, name FROM stores", user)       # passa pelo RLS
    names = dict(stores)
    df = suggest_orders(None, 7)
    df = df[df["store_id"].isin(names) & (df["needed"] > 0)].copy()
    df["days"] = df["stock"].astype(float) / (df["needed"].astype(float) / 7)
    low = df[df["days"] < MIN_COVER_DAYS].sort_values("days").head(MAX_STOCK_ALERTS)
    return [{"type": "low_stock", "severity": "high" if r.days < HIGH_COVER_DAYS else "warn",
             "store": names[r.store_id], "ingredient": r.ingredient, "unit": r.unit,
             "days": round(float(r.days), 1), "stock": round(float(r.stock), 1)}
            for r in low.itertuples()]


def alerts_for(user: dict, lang: str = "pt") -> list[dict]:
    """Alertas do âmbito do utilizador (mais graves primeiro), com o texto no idioma pedido."""
    key = (data_role(user["role"]), user.get("brand_id"), user.get("store_id"),
           has_module(user, "sql"), has_module(user, "orders"))
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_SECONDS:
        items = cached[1]
    else:
        items = []
        try:
            if has_module(user, "sql"):
                items += sales_alerts(user)
            if has_module(user, "orders"):
                items += stock_alerts(user)
        except Exception:
            log.warning("Não foi possível calcular os alertas", exc_info=True)
        order = {"high": 0, "warn": 1, "info": 2}
        items.sort(key=lambda a: (order[a["severity"]], a.get("change_pct", 0)))
        with _lock:
            _cache[key] = (now, items)
    return [{**a, "message": message(a, lang)} for a in items]


def clear_cache() -> None:
    with _lock:
        _cache.clear()
