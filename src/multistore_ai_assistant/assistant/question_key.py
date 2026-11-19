"""Chave normalizada de uma pergunta, para a cache de SQL decidir se duas perguntas são a mesma.

Cada palavra passa para uma forma canónica, igual nas 4 línguas:

- **sinónimos** → um conceito: ``faturação`` = ``revenue`` = ``facturación`` = ``vendas``;
  ``funcionários`` = ``empregados`` = ``employees``; ``outubro`` = ``october`` = ``m10``;
- **agrupamentos** (``por``, ``cada``, ``each``, ``by``…) ligam-se à dimensão seguinte:
  ``cada marca`` = ``por marca`` = ``by:brand``. Se a seguir vier uma métrica
  (``top 5 lojas por faturação``), é só a ordenação e fica a métrica;
- **ordem** (``mais``/``top``/``highest`` → ``top``; ``menos``/``lowest`` → ``bottom``) e
  comparações (``mais de`` → ``gt``);
- **palavras vazias** (artigos, preposições, "qual", "mostra-me", "foi"…) saem;
- **palavras desconhecidas** ficam tal como estão. Nomes de lojas ("Maia", "Braga"),
  filtros ("sem", "except", "fim de semana") ou termos novos têm de aparecer nas duas
  perguntas, por isso nunca se confundem.

Duas perguntas com a mesma chave pedem os mesmos dados. A lista é conservadora:
uma palavra ambígua (``sold``, ``vendu``, ``combien``) fica desconhecida, o que só
faz perder um acerto; uma palavra mal mapeada podia devolver o SQL errado.
"""
import re
import unicodedata

_GROUPS = {
    "revenue": "faturacao faturamento faturou faturaram faturamos faturei faturado fatura receita venda vendi vendeu "
               "vendemos venderam revenue revenues turnover facturacion facturado facturo ingreso ventas venta vendio "
               "vendimos chiffre affaires vente",
    "units": "vendido vendida quantidade unidade quantity unit cantidad unidad quantite",
    "count": "quantos quantas numero number many cuantos cuantas nombre count contagem",
    "margin": "margem margens margin margen margenes marge",
    "avg": "medio media medios medias average avg promedio moyen moyenne",
    "ticket": "ticket",
    "employee": "funcionario empregado trabalhador colaborador employee worker empleado trabajador employe salarie",
    "store": "loja store shop tienda magasin boutique",
    "brand": "marca brand marque",
    "product": "produto product producto produit",
    "menu": "menu",
    "ingredient": "ingrediente ingredient",
    "supplier": "fornecedor supplier vendor proveedor fournisseur",
    "payment": "pagamento payment pago paiement",
    "shift": "turno shift equipe",
    "stock": "stock estoque existencia inventario inventory",
    "purchase": "compra purchase achat",
    "transfer": "transferencia transfer transfert",
    "day": "dia dias day days jour jours",
    "hour": "hora horas hour hours heure heures",
    "week": "semana semanas week weeks semaine semaines",
    "month": "mes meses month months mois",
    "year": "ano anos year years annee annees",
    "yesterday": "ontem yesterday ayer hier",
    "today": "hoje today hoy aujourd",
    "this": "este esta this current atual actual ce cette",
    "last": "passado passada ultimo ultima ultimos ultimas last previous anterior pasado pasada dernier derniere "
            "precedent precedente",
    "next": "proximo proxima proximos proximas next seguinte siguiente prochain prochaine",
    "top": "mais most highest maior maiores melhor melhores top best mejor mejores plus",
    "bottom": "menos least lowest menor menores pior piores worst peor peores moins",
    "by": "por cada by per each par chaque",
}
_MONTHS = [
    "janeiro january enero janvier", "fevereiro february febrero fevrier", "marco march marzo mars",
    "abril april avril", "maio may mayo mai", "junho june junio juin", "julho july julio juillet",
    "agosto august aout", "setembro september septiembre septembre", "outubro october octubre octobre",
    "novembro november noviembre novembre", "dezembro december diciembre decembre",
]
STOPWORDS = set(["a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "ao", "aos", "e", "com", "para", "pelo", "pela", "pelos", "pelas", "que", "qual", "quais", "quanto", "quanta", "foi", "foram", "ser", "sao", "tem", "teve", "tiveram", "fez", "fizeram", "fiz", "ha", "houve", "me", "mostra", "mostrar", "mostre", "diz", "diga", "dizer", "lista", "listar", "indica", "sabes", "podes", "pode", "favor", "minha", "meu", "minhas", "meus", "nossa", "nosso", "nossas", "nossos", "sua", "seu", "suas", "seus", "total", "totais", "valor", "valores", "tenho", "temos", "the", "of", "in", "on", "at", "for", "to", "an", "and", "what", "which", "was", "were", "is", "are", "has", "have", "had", "does", "did", "do", "how", "much", "show", "tell", "give", "list", "please", "my", "our", "with", "el", "la", "los", "las", "del", "en", "un", "una", "y", "cual", "cuales", "cuanto", "cuanta", "fue", "fueron", "es", "son", "tiene", "tienen", "tuvo", "hizo", "muestra", "dame", "dime", "mi", "mis", "nuestro", "nuestra", "con", "le", "les", "des", "du", "au", "aux", "une", "et", "quel", "quelle", "quels", "quelles", "est", "sont", "ont", "fait", "montre", "donne", "mon", "ma", "avec", "hui", "ai", "je", "il", "qu"])
# Expressões de várias palavras, trocadas antes de tudo (``moyen`` sozinho é "média")
PHRASES = {
    ("metodo", "de", "pagamento"): "payment", ("forma", "de", "pagamento"): "payment",
    ("meio", "de", "pagamento"): "payment", ("payment", "method"): "payment", ("metodo", "de", "pago"): "payment",
    ("forma", "de", "pago"): "payment", ("moyen", "de", "paiement"): "payment", ("mode", "de", "paiement"): "payment",
    ("ticket", "medio"): "ticket", ("average", "ticket"): "ticket", ("ticket", "promedio"): "ticket",
    ("ticket", "moyen"): "ticket", ("valor", "medio", "por", "venda"): "ticket",
    ("average", "sale", "value"): "ticket", ("average", "order", "value"): "ticket",
    ("fim", "de", "semana"): "weekend", ("weekend",): "weekend", ("fin", "de", "semana"): "weekend",
    ("chiffre", "d", "affaires"): "revenue", ("how", "many"): "count",
}
_PHRASE_LENGTHS = sorted({len(p) for p in PHRASES}, reverse=True)
COMPARE = {("mais", "de"): "gt", ("more", "than"): "gt", ("mas", "de"): "gt", ("plus", "de"): "gt",
           ("menos", "de"): "lt", ("less", "than"): "lt", ("moins", "de"): "lt",
           ("acima", "de"): "gt", ("abaixo", "de"): "lt"}
METRICS = {"revenue", "units", "count", "margin", "avg", "ticket", "stock", "purchase"}

LEXICON = {w: concept for concept, words in _GROUPS.items() for w in words.split()}
LEXICON.update({w: f"m{i:02d}" for i, words in enumerate(_MONTHS, 1) for w in words.split()})


def words(text: str) -> list[str]:
    """Palavras em minúsculas, sem acentos (``faturação`` → ``faturacao``)."""
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+|\d+", plain)


def canonical(word: str) -> str | None:
    """Conceito da palavra, ``None`` se for vazia, ou a própria palavra se for desconhecida."""
    if word in STOPWORDS:
        return None
    if word in LEXICON:
        return LEXICON[word]
    if len(word) > 4 and word.endswith("s"):          # plurais: lojas → loja, vendas → venda
        if word[:-1] in LEXICON:
            return LEXICON[word[:-1]]
        if word[:-1] in STOPWORDS:
            return None
    return word


def question_key(question: str) -> tuple[str, ...]:
    """Chave canónica: duas perguntas com a mesma chave pedem os mesmos dados."""
    ws = words(question)
    tokens: list[str] = []
    i = 0
    while i < len(ws):
        phrase = next((n for n in _PHRASE_LENGTHS if tuple(ws[i:i + n]) in PHRASES), 0)
        if phrase:
            tokens.append(PHRASES[tuple(ws[i:i + phrase])])
            i += phrase
            continue
        pair = (ws[i], ws[i + 1]) if i + 1 < len(ws) else None
        if pair in COMPARE:
            tokens.append(COMPARE[pair])
            i += 2
            continue
        concept = canonical(ws[i])
        if concept is not None:
            tokens.append(concept)
        i += 1

    key: set[str] = set()
    j = 0
    while j < len(tokens):
        t = tokens[j]
        if t == "by":
            nxt = tokens[j + 1] if j + 1 < len(tokens) else ""
            if nxt and nxt not in METRICS and nxt != "by":
                key.add("by:" + nxt)               # "por loja" / "each store"
                j += 2
                continue
            j += 1                                 # "por faturação": só ordenação, a métrica fica
            continue
        key.add(t)
        j += 1
    if any(k.startswith("m") and k[1:].isdigit() for k in key):
        key.discard("month")                       # "no mês de outubro" = "em outubro"
    return tuple(sorted(key))
