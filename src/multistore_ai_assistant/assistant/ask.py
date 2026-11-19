"""Orquestra uma pergunta: intenção → SQL/ML/recusa → resposta em texto.

Fluxo principal:
1. Classificador local (ou LLM se confiança baixa / follow-up ambíguo).
2. Recusas e chat sem ir à BD; forecast/orders via modelos ML.
3. Caso contrário: gera SQL, valida com sqlglot, corre com RLS, resume com LLM.
4. Se a query falhar, tenta uma vez a corrigir com o erro no prompt.

Antes de gerar SQL, a cache de SQL (``assistant.cache``) procura uma pergunta
que pede os mesmos dados, feita hoje no mesmo perfil; se existir, reaproveita o SQL (que corre
de novo com o RLS de quem pergunta) e poupa a chamada ao LLM.

Com ``on_event`` (streaming), ``ask`` emite eventos à medida que avança:
``status`` (passo atual), ``data`` (SQL, colunas e linhas, antes do texto) e
``token`` (pedaços da resposta do LLM).

Cada caminho exige o módulo certo na conta (``sql``, ``forecast``, ``orders``);
sem ele a resposta é ``kind="denied"``. A intenção e as tentativas de SQL
ficam no Trace do pedido (``observability``).
"""
import logging
import re
import sys
import unicodedata

import psycopg

from multistore_ai_assistant.api.permissions import has_module
from multistore_ai_assistant.assistant.answer import answer, chat_reply
from multistore_ai_assistant.assistant.cache import lookup as cache_lookup
from multistore_ai_assistant.assistant.cache import store as cache_store
from multistore_ai_assistant.assistant.sql_generator import generate_sql
from multistore_ai_assistant.assistant.sql_validator import InvalidSQL, validate_sql
from multistore_ai_assistant.db.query import IMPERADOR, run_query
from multistore_ai_assistant.forecast.service import forecast_answer, orders_answer
from multistore_ai_assistant.intent.predict import classify
from multistore_ai_assistant.observability import record_cache_hit, record_intent, record_sql_attempt

MAX_ATTEMPTS = 2
log = logging.getLogger("multistore")

# O erro técnico fica no log do servidor; o utilizador vê uma mensagem simples
ERROR_MESSAGES = {
    "pt": "Não consegui responder a essa pergunta. Tenta reformulá-la, por exemplo com um período ou uma loja concretos.",
    "en": "I couldn't answer that question. Try rephrasing it, for example with a specific period or store.",
    "es": "No he podido responder a esa pregunta. Intenta reformularla, por ejemplo con un periodo o una tienda concretos.",
    "fr": "Je n'ai pas pu répondre à cette question. Essaie de la reformuler, par exemple avec une période ou un magasin précis.",
}

REFUSALS = {
    "personal_data": {
        "pt": "Não posso partilhar dados pessoais de funcionários (NIF, NISS, morada, data de nascimento).",
        "en": "I can't share employees' personal data (NIF, NISS, address, birth date).",
        "es": "No puedo compartir datos personales de los empleados (NIF, NISS, dirección, fecha de nacimiento).",
        "fr": "Je ne peux pas partager les données personnelles des employés (NIF, NISS, adresse, date de naissance).",
    },
    "write": {
        "pt": "Só consigo consultar dados, não posso alterar, criar ou apagar nada.",
        "en": "I can only read data; I can't change, create or delete anything.",
        "es": "Solo puedo consultar datos; no puedo modificar, crear ni borrar nada.",
        "fr": "Je peux seulement consulter les données ; je ne peux rien modifier, créer ni supprimer.",
    },
    "off_topic": {
        "pt": "Só respondo a perguntas sobre os dados do grupo: vendas, lojas, produtos, stock e equipas.",
        "en": "I only answer questions about the group's data: sales, stores, products, stock and staff.",
        "es": "Solo respondo preguntas sobre los datos del grupo: ventas, tiendas, productos, stock y equipos.",
        "fr": "Je réponds uniquement aux questions sur les données du groupe : ventes, magasins, produits, stock et équipes.",
    },
}

# Conta sem o módulo pedido (os nomes dos módulos aparecem traduzidos)
MODULE_NAMES = {
    "pt": {"sql": "perguntas aos dados", "forecast": "previsão de vendas", "orders": "sugestão de encomendas"},
    "en": {"sql": "data questions", "forecast": "sales forecast", "orders": "order suggestions"},
    "es": {"sql": "preguntas sobre los datos", "forecast": "previsión de ventas", "orders": "sugerencia de pedidos"},
    "fr": {"sql": "questions sur les données", "forecast": "prévision des ventes", "orders": "suggestion de commandes"},
}
DENIED = {
    "pt": "A tua conta não tem acesso ao módulo «{}». Pede acesso a quem gere a tua conta.",
    "en": "Your account doesn't have access to the “{}” module. Ask whoever manages your account.",
    "es": "Tu cuenta no tiene acceso al módulo «{}». Pide acceso a quien gestiona tu cuenta.",
    "fr": "Ton compte n'a pas accès au module « {} ». Demande l'accès à la personne qui gère ton compte.",
}


def denied(module: str, lang: str) -> dict:
    """Resposta quando a conta não tem o módulo (não gasta tokens nem toca na BD)."""
    lang = lang if lang in DENIED else "pt"
    return {"sql": None, "kind": "denied", "module": module,
            "answer": DENIED[lang].format(MODULE_NAMES[lang][module])}


# Intenções que o classificador pode decidir sozinho a meio de uma conversa
FOLLOW_UP_SAFE = {"forecast", "orders"}

# O atalho "orders" só vale se a pergunta falar mesmo de encomendar / comprar / repor.
# O XLM-R aprendeu a forma "Que … devo …?" como encomenda (99,9 %), e mandava para o
# modelo de encomendas "Que produtos devo promover ou retirar da carta?". Sem um destes
# verbos decide o LLM (que ainda pode responder ORDERS): só se perde um atalho, nunca se ganha.
ORDER_WORDS = re.compile(
    r"encomend|compra|comprar|repor|reposi|reabastec|abastec|falta|acabar|esgot|lista de compras"
    r"|order|buy|purchas|restock|replenish|run(ning)? out|shopping"
    r"|pedir|pedido|reponer|agot"
    r"|command|achet|reapprovision|approvision|rupture|courses")


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def trust_shortcut(intent: str | None, question: str) -> str | None:
    """Confirma o atalho do classificador com palavras-chave (hoje só para ``orders``)."""
    if intent == "orders" and not ORDER_WORDS.search(_plain(question)):
        return None
    return intent


def route_intent(intent: str | None, history: list | None) -> str | None:
    """Decide se confiamos no classificador ou se deixamos o LLM decidir.

    O classificador só vê a pergunta atual. A meio de uma conversa, frases curtas
    como "E no Porto?" ou "Só para a BurgerLab" parecem conversa ou pedidos de
    escrita, mas são perguntas de seguimento. Nesse caso decide o LLM, que vê o
    histórico. A segurança não muda: o validador e o RLS continuam a proteger.

    Args:
        intent: Etiqueta do classificador, ou ``None`` se incerto.
        history: Histórico da conversa; se não vazio, só forecast/orders passam.

    Returns:
        Intenção a usar, ou ``None`` para o caminho text-to-SQL / LLM.
    """
    if history and intent not in FOLLOW_UP_SAFE:
        return None
    return intent


ML_NOTE = "(Machine learning forecast for the next 7 days, not historical data.)"


def _emit(on_event, event_type: str, **data) -> None:
    """Envia um evento ao streaming (se houver quem ouça)."""
    if on_event is not None:
        on_event({"type": event_type, **data})


def _tokens(on_event):
    """Callback para o LLM: cada pedaço de texto vira um evento ``token``."""
    return None if on_event is None else (lambda piece: on_event({"type": "token", "text": piece}))


def _ml_answer(kind: str, question: str, user: dict, lang: str, on_event=None) -> dict:
    """Resposta do modelo de previsão: ``kind`` é ``forecast`` ou ``orders``."""
    if not has_module(user, kind):
        return denied(kind, lang)
    _emit(on_event, "status", step="forecast")
    columns, rows = forecast_answer(user) if kind == "forecast" else orders_answer(user)
    _emit(on_event, "data", kind=kind, sql=None, columns=columns, rows=rows)
    _emit(on_event, "status", step="answer")
    return {"sql": None, "kind": kind, "columns": columns, "rows": rows,
            "answer": answer(f"{question}\n{ML_NOTE}", columns, rows, lang, on_token=_tokens(on_event))}


def _sql_answer(sql: str, question: str, user: dict, lang: str, on_event) -> dict:
    """Valida, corre com RLS e resume. Levanta InvalidSQL / psycopg.Error se falhar."""
    sql = validate_sql(sql)
    _emit(on_event, "status", step="query")
    columns, rows = run_query(sql, user)
    record_sql_attempt()
    _emit(on_event, "data", kind="sql", sql=sql, columns=columns, rows=rows)
    _emit(on_event, "status", step="answer")
    text = answer(question, columns, rows, lang, on_token=_tokens(on_event))
    return {"sql": sql, "kind": "sql", "columns": columns, "rows": rows, "answer": text}


def ask(
    question: str,
    user: dict,
    lang: str = "pt",
    history: list[tuple[str, str]] | None = None,
    on_event=None,
) -> dict:
    """Responde a uma pergunta do gestor.

    Args:
        question: Texto da pergunta.
        user: Perfil RLS (``role``, ``brand_id``, ``store_id``) e, vindo da API,
            ``modules``. Obrigatório.
        lang: Idioma da resposta (``pt``, ``en``, ``es``, ``fr``).
        history: Pares ``(pergunta, SQL|etiqueta)`` das últimas trocas.
        on_event: Opcional (streaming): recebe ``status``, ``data`` e ``token``.

    Returns:
        Dict com ``answer`` (ou ``error``), ``sql``/``kind``, e opcionalmente
        ``columns``/``rows``, ``intent`` e ``cached``. Quando falha: ``kind="error"``
        e ``sql=None`` (o SQL partido fica só no log, nunca no histórico nem no RAG).
        Sem o módulo necessário: ``kind="denied"``.
    """
    # 1.º o classificador local; se não tiver certeza, decide o LLM (com histórico se houver)
    _emit(on_event, "status", step="classify")
    predicted, conf = classify(question)
    intent = route_intent(trust_shortcut(predicted, question), history)
    record_intent(predicted, conf)
    log.info("Intenção: %s (%.2f) -> %s | %r", predicted, conf, intent, question)

    if intent in REFUSALS:
        return {
            "sql": None, "kind": "no_sql", "intent": intent,
            "answer": REFUSALS[intent][lang],
        }
    if intent == "chat":
        _emit(on_event, "status", step="answer")
        return {
            "sql": None, "kind": "no_sql", "intent": intent,
            "answer": chat_reply(question, lang, on_token=_tokens(on_event)),
        }
    if intent in ("forecast", "orders"):
        return {**_ml_answer(intent, question, user, lang, on_event), "intent": intent}

    # Cache de SQL: só sem histórico (um seguimento depende do contexto) e com o módulo de dados
    if not history and has_module(user, "sql"):
        hit = cache_lookup(question, user)
        if hit:
            try:
                result = _sql_answer(hit["sql"], question, user, lang, on_event)
                record_cache_hit()
                log.info("Cache de SQL: %r = %r (%.3f)", question, hit["question"], hit["distance"])
                return {**result, "cached": True}
            except (InvalidSQL, psycopg.Error) as e:      # p.ex. o esquema mudou: segue o caminho normal
                log.warning("SQL da cache falhou, a gerar de novo: %s", e)

    # Text-to-SQL com até MAX_ATTEMPTS tentativas (a 2.ª inclui o erro no prompt)
    prompt = question
    for attempt in range(MAX_ATTEMPTS):
        _emit(on_event, "status", step="sql")
        sql = generate_sql(prompt, history)
        if sql in ("FORECAST", "ORDERS"):
            return _ml_answer(sql.lower(), question, user, lang, on_event)
        if sql.strip() == "NO_SQL":
            _emit(on_event, "status", step="answer")
            return {"sql": None, "kind": "no_sql", "answer": chat_reply(question, lang, on_token=_tokens(on_event))}
        if not has_module(user, "sql"):
            return denied("sql", lang)
        try:
            result = _sql_answer(sql, question, user, lang, on_event)
            if not history:
                cache_store(question, result["sql"], user)
            return result
        except (InvalidSQL, psycopg.Error) as e:
            record_sql_attempt(e)
            if attempt == MAX_ATTEMPTS - 1:
                log.warning("Pergunta falhou: %r | SQL: %s | Erro: %s", question, sql, e)
                return {
                    "sql": None, "kind": "error",
                    "error": ERROR_MESSAGES.get(lang, ERROR_MESSAGES["pt"]),
                }
            prompt = (
                f"{question}\n\nThe previous query failed:\n{sql}\nError: {e}\nFix it."
            )


if __name__ == "__main__":
    # Uso: python -m ...ask [role=id] "pergunta"
    # Ex.: python -m multistore_ai_assistant.assistant.ask loja=3 "Faturação de ontem"
    args = sys.argv[1:]
    user = IMPERADOR
    if args and "=" in args[0]:
        role, value = args.pop(0).split("=")
        user = {
            "role": role,
            "brand_id": int(value) if role == "marca" else None,
            "store_id": int(value) if role == "loja" else None,
        }
    question = " ".join(args) or "Quais as 5 lojas com mais faturação em 2026?"
    result = ask(question, user)
    if result.get("sql"):
        print(result["sql"], "\n")
    if "error" in result:
        print("Erro:", result["error"])
    else:
        print(result["answer"], "\n")
        if result.get("columns"):
            print(" | ".join(result["columns"]))
            for row in result["rows"]:
                print(" | ".join(str(v) for v in row))
