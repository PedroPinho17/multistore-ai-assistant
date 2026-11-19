"""Perguntas de seguimento sugeridas depois de cada resposta (sem LLM, sem tokens).

Regras simples a partir do tipo de resposta, das colunas do resultado e do
período mencionado na pergunta: "E por loja?" quando a resposta é por marca,
"Comparar com o mês anterior" quando a pergunta tem um mês, etc. Devolve no
máximo ``MAX`` sugestões, já no idioma da conversa.
"""
import re

MAX = 3

TEXT = {
    "by_store": {"pt": "E por loja?", "en": "And by store?", "es": "¿Y por tienda?", "fr": "Et par magasin ?"},
    "by_brand": {"pt": "E por marca?", "en": "And by brand?", "es": "¿Y por marca?", "fr": "Et par marque ?"},
    "by_month": {"pt": "Mostra a evolução por mês", "en": "Show the trend by month",
                 "es": "Muestra la evolución por mes", "fr": "Montre l'évolution par mois"},
    "prev_month": {"pt": "Comparar com o mês anterior", "en": "Compare with the previous month",
                   "es": "Comparar con el mes anterior", "fr": "Comparer avec le mois précédent"},
    "prev_year": {"pt": "Comparar com o ano passado", "en": "Compare with last year",
                  "es": "Comparar con el año pasado", "fr": "Comparer avec l'année dernière"},
    "top3": {"pt": "Mostra só o top 3", "en": "Show only the top 3", "es": "Muestra solo el top 3",
             "fr": "Montre seulement le top 3"},
    "by_payment": {"pt": "E por método de pagamento?", "en": "And by payment method?",
                   "es": "¿Y por método de pago?", "fr": "Et par moyen de paiement ?"},
    "orders": {"pt": "Que ingredientes devo encomendar?", "en": "Which ingredients should I order?",
               "es": "¿Qué ingredientes debo pedir?", "fr": "Quels ingrédients dois-je commander ?"},
    "forecast": {"pt": "Quanto vou vender nos próximos 7 dias?", "en": "How much will I sell in the next 7 days?",
                 "es": "¿Cuánto venderé en los próximos 7 días?", "fr": "Combien vais-je vendre dans les 7 prochains jours ?"},
    "margins": {"pt": "Que produtos devo promover ou retirar da carta?",
                "en": "Which products should I promote or remove from the menu?",
                "es": "¿Qué productos debo promocionar o retirar de la carta?",
                "fr": "Quels produits dois-je promouvoir ou retirer de la carte ?"},
}

MONTHS = re.compile(
    r"\b(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"enero|febrero|marzo|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
    r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
    r"m[eê]s|month|mes|mois)\b", re.I)
PER_MONTH = re.compile(r"\b(por|by|per|par|cada|each)\s+(m[eê]s|month|mes|mois)\b", re.I)
YEAR = re.compile(r"\b(20\d\d|ano|year|año|année)\b", re.I)


def suggestions(question: str, kind: str, columns: list[str] | None, rows: list | None, lang: str = "pt",
                scope: str = "imperador") -> list[str]:
    """Até 3 perguntas de seguimento, por ordem de utilidade.

    ``scope`` é o perfil de dados: uma loja não recebe "E por marca?" nem
    "E por loja?" (só vê uma), uma marca não recebe "E por marca?".
    """
    lang = lang if lang in ("pt", "en", "es", "fr") else "pt"
    cols = " ".join(columns or []).lower()
    keys: list[str] = []
    if kind == "forecast":
        keys = ["orders", "margins"]
    elif kind == "orders":
        keys = ["forecast"]
    elif kind == "sql":
        if scope != "loja" and ("marca" in cols or "brand" in cols):
            keys.append("by_store")
        elif scope == "imperador" and ("loja" in cols or "store" in cols):
            keys.append("by_brand")
        one_month = MONTHS.search(question) and not PER_MONTH.search(question)
        if one_month:
            keys.append("prev_month")
        elif YEAR.search(question):
            keys.append("prev_year")
        time_series = any(w in cols for w in ("mes", "month", "dia", "day", "semana", "week", "data", "date"))
        if rows and len(rows) > 5 and not time_series:
            keys.append("top3")
        if not MONTHS.search(question) and "mes" not in cols and "month" not in cols and rows and len(rows) <= 5:
            keys.append("by_month")
        if "pagamento" not in cols and "payment" not in cols and ("fatura" in cols or "revenue" in cols):
            keys.append("by_payment")
    seen = {question.strip(" ?¿!.").lower()}       # nunca sugerir a pergunta que acabou de ser feita
    out = []
    for key in keys:
        text = TEXT[key][lang]
        if text.strip(" ?¿!.").lower() not in seen:
            seen.add(text.strip(" ?¿!.").lower())
            out.append(text)
    return out[:MAX]
