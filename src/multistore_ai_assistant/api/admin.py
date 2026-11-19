"""Painel de observabilidade (só para a conta ``admin``).

Tudo é calculado a partir da tabela ``request_log`` num intervalo de dias:
volume, taxa de erro, latência (p50/p95), tokens do LLM, intenções, perguntas
mais feitas, avaliações 👍/👎 e o histórico da avaliação automática.
"""
from multistore_ai_assistant.db.pool import connection
from multistore_ai_assistant.eval_results import load_history

TZ = "Europe/Lisbon"
ERROR_KINDS = ("error", "exception")


def _rows(cur) -> list[dict]:
    """Resultado do cursor como lista de dicts (colunas → valores)."""
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


def _iso(rows: list[dict], *keys: str) -> list[dict]:
    """Datas em ISO 8601 (o JSON da API não serializa ``datetime`` por defeito no dict)."""
    for r in rows:
        for k in keys:
            if r.get(k) is not None:
                r[k] = r[k].isoformat()
    return rows


def metrics(days: int = 7) -> dict:
    """Métricas dos últimos ``days`` dias (1–90)."""
    days = max(1, min(int(days), 90))
    since = "now() - make_interval(days => %(days)s)"
    p = {"days": days, "tz": TZ, "errors": list(ERROR_KINDS)}
    with connection("owner") as conn:
        cur = conn.cursor()
        summary = _rows(cur.execute(f"""
            SELECT count(*)                                              AS requests,
                   count(DISTINCT username)                              AS users,
                   count(*) FILTER (WHERE kind = ANY(%(errors)s))        AS errors,
                   count(*) FILTER (WHERE sql_attempts > 0)              AS sql_requests,
                   count(*) FILTER (WHERE sql_failed)                    AS sql_failed,
                   count(*) FILTER (WHERE sql_failed AND kind = 'sql')   AS sql_recovered,
                   count(*) FILTER (WHERE kind = 'denied')               AS denied,
                   round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY duration_ms))  AS p50_ms,
                   round(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms))  AS p95_ms,
                   coalesce(sum(prompt_tokens), 0)                       AS prompt_tokens,
                   coalesce(sum(completion_tokens), 0)                   AS completion_tokens,
                   coalesce(sum(llm_calls), 0)                           AS llm_calls,
                   count(*) FILTER (WHERE rating = 1)                    AS thumbs_up,
                   count(*) FILTER (WHERE rating = -1)                   AS thumbs_down,
                   count(*) FILTER (WHERE intent IS NOT NULL)            AS classified,
                   count(*) FILTER (WHERE cache_hit)                     AS cache_hits
            FROM request_log WHERE created_at >= {since}""", p))[0]

        daily = _rows(cur.execute("""
            WITH d AS (
              SELECT generate_series((now() AT TIME ZONE %(tz)s)::date - (%(days)s - 1),
                                     (now() AT TIME ZONE %(tz)s)::date, interval '1 day')::date AS day)
            SELECT to_char(d.day, 'YYYY-MM-DD') AS day,
                   count(r.id) AS requests,
                   count(r.id) FILTER (WHERE r.kind = ANY(%(errors)s)) AS errors,
                   coalesce(sum(r.prompt_tokens + r.completion_tokens), 0) AS tokens,
                   round(percentile_cont(0.95) WITHIN GROUP (ORDER BY r.duration_ms)) AS p95_ms
            FROM d LEFT JOIN request_log r ON (r.created_at AT TIME ZONE %(tz)s)::date = d.day
            GROUP BY d.day ORDER BY d.day""", p))

        by_kind = _rows(cur.execute(f"""
            SELECT kind, count(*) AS n, round(avg(duration_ms)) AS avg_ms,
                   round(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)) AS p95_ms,
                   round(avg(prompt_tokens + completion_tokens)) AS avg_tokens
            FROM request_log WHERE created_at >= {since}
            GROUP BY kind ORDER BY n DESC""", p))

        by_intent = _rows(cur.execute(f"""
            SELECT coalesce(intent, 'llm') AS intent, count(*) AS n
            FROM request_log WHERE created_at >= {since}
            GROUP BY 1 ORDER BY n DESC""", p))

        top_questions = _iso(_rows(cur.execute(f"""
            SELECT min(question) AS question, count(*) AS n,
                   count(*) FILTER (WHERE kind = ANY(%(errors)s)) AS errors,
                   count(*) FILTER (WHERE rating = 1) AS up, count(*) FILTER (WHERE rating = -1) AS down,
                   max(created_at) AS last_at
            FROM request_log WHERE created_at >= {since}
            GROUP BY lower(btrim(question, ' ?!.¿¡')) ORDER BY n DESC, last_at DESC LIMIT 10""", p)),
            "last_at")

        thumbs_down = _iso(_rows(cur.execute(f"""
            SELECT id, created_at, username, question, kind, error
            FROM request_log WHERE rating = -1 AND created_at >= {since}
            ORDER BY created_at DESC LIMIT 10""", p)), "created_at")

        recent_errors = _iso(_rows(cur.execute(f"""
            SELECT id, created_at, username, question, kind, error, duration_ms
            FROM request_log WHERE (kind = ANY(%(errors)s) OR sql_failed) AND created_at >= {since}
            ORDER BY created_at DESC LIMIT 10""", p)), "created_at")

        by_user = _iso(_rows(cur.execute(f"""
            SELECT username, max(role) AS role, count(*) AS requests,
                   count(*) FILTER (WHERE kind = ANY(%(errors)s)) AS errors,
                   coalesce(sum(prompt_tokens + completion_tokens), 0) AS tokens,
                   max(created_at) AS last_at
            FROM request_log WHERE created_at >= {since}
            GROUP BY username ORDER BY requests DESC LIMIT 15""", p)), "last_at")

    n = summary["requests"] or 0
    rated = summary["thumbs_up"] + summary["thumbs_down"]
    summary.update({
        "error_rate": round(summary["errors"] / n, 4) if n else 0,
        "sql_fail_rate": round(summary["sql_failed"] / summary["sql_requests"], 4) if summary["sql_requests"] else 0,
        "satisfaction": round(summary["thumbs_up"] / rated, 4) if rated else None,
        "avg_tokens": round((summary["prompt_tokens"] + summary["completion_tokens"]) / n) if n else 0,
        "classifier_share": round(summary["classified"] / n, 4) if n else 0,
        "cache_share": round(summary["cache_hits"] / summary["sql_requests"], 4) if summary["sql_requests"] else 0,
    })
    for k in ("p50_ms", "p95_ms"):
        summary[k] = int(summary[k]) if summary[k] is not None else None
    for rows in (daily, by_kind):
        for r in rows:
            for k in ("p95_ms", "avg_ms", "avg_tokens"):
                if r.get(k) is not None:
                    r[k] = int(r[k])
    return {
        "days": days, "summary": summary, "daily": daily, "by_kind": by_kind,
        "by_intent": by_intent, "top_questions": top_questions, "thumbs_down": thumbs_down,
        "recent_errors": recent_errors, "by_user": by_user, "eval_history": load_history(),
    }
