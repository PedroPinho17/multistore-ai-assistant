"""Valores das respostas → JSON válido, igual para o SSE (``/ask/stream``) e para ``messages.result``.

O ``json.dumps`` do Python escreve ``NaN`` e ``Infinity`` sem se queixar, mas não são
JSON: o ``JSON.parse`` do browser recusa-os e o ``jsonb`` do PostgreSQL também (a mensagem
da resposta não ficava gravada). Por isso, antes de serializar:

- ``float`` NaN/±Infinity (incluindo os do numpy) → ``None``;
- ``Decimal`` NaN/Infinity (``numeric`` do Postgres) → ``None``; os finitos ficam ``Decimal``
  (cada sítio decide como os escreve: texto no SSE, número na BD);
- escalares numpy/pandas → o tipo nativo equivalente.

Quem serializa usa ``allow_nan=False``: se algum valor escapar a isto, falha logo.
"""
import math
from decimal import Decimal


def jsonable(value):
    """Cópia de ``value`` (dicts, listas, tuplos) sem NaN/Infinity e sem tipos do numpy."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, float):                      # inclui numpy.float64 (subclasse de float)
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):   # escalares numpy (float32, int64…)
        try:
            return jsonable(value.item())
        except (TypeError, ValueError):
            return str(value)
    return value
