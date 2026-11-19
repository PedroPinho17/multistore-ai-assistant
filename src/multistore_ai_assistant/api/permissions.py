"""Perfis, módulos e regras de gestão de utilizadores (lógica pura, sem BD).

Perfis, do mais alto para o mais baixo::

    admin (0)  >  imperador (1)  >  marca (2)  >  loja (3)

- ``admin`` é a conta do dono da aplicação: vê os dados como o Imperador e,
  além disso, o painel de observabilidade. Nunca é uma conta de demonstração;
  cria-se com ``python -m multistore_ai_assistant.data.create_admin``.
- O RLS da BD só conhece ``imperador``/``marca``/``loja``: o admin entra
  nas policies como ``imperador`` (ver ``data_role``).

Módulos (o que cada conta pode usar):

- ``sql``: perguntas aos dados (text-to-SQL);
- ``forecast``: previsão de vendas;
- ``orders``: sugestão de encomendas;
- ``teach``: ensinar o assistente (guardar pergunta→SQL nos exemplos RAG e rever os 👎 de todos);
- ``users``: criar e gerir contas do mesmo nível ou abaixo;
- ``observability``: painel de métricas (só ``admin``).

Regras:

1. Quem cria só dá perfis do seu nível ou abaixo, dentro do seu âmbito
   (uma marca só cria contas da sua marca; uma loja só da sua loja).
2. Só dá módulos que ele próprio tem e que o perfil novo pode ter
   (``teach`` mexe nos exemplos de todos, por isso fica para admin/imperador).
3. Gere contas de nível abaixo no seu âmbito; do mesmo nível, só as que criou.
4. As contas de demonstração (``protected``) só o admin as altera.
5. As contas de demonstração têm a password pública: **na gestão de contas só
   leem** (veem a lista, não criam, não alteram, não apagam) e não mudam a
   própria password nem a foto. Sem isto, qualquer visitante podia mudar a
   password de uma conta real criada pelo admin, criar Imperadores em cadeia
   ou trancar a demo a toda a gente. O admin (também ``protected``) não conta.
"""

from multistore_ai_assistant.api.errors import ApiError

ROLE_LEVEL = {"admin": 0, "imperador": 1, "marca": 2, "loja": 3}
ROLES = tuple(ROLE_LEVEL)

MODULES = ("sql", "forecast", "orders", "teach", "users", "observability")

# Módulos que cada perfil PODE ter (máximo)
ROLE_MODULES = {
    "admin": set(MODULES),
    "imperador": {"sql", "forecast", "orders", "teach", "users"},
    "marca": {"sql", "forecast", "orders", "users"},
    "loja": {"sql", "forecast", "orders", "users"},
}
# Contas sem módulos escolhidos (``modules`` NULL, p.ex. as de demonstração): tudo o que o perfil permite
DEFAULT_MODULES = ROLE_MODULES
# Conta nova sem módulos escolhidos: só os de dados ("users" e "teach" dão-se de propósito)
NEW_ACCOUNT_MODULES = {"sql", "forecast", "orders"}
# Contas por criador (evita que uma conta pública de demo encha a tabela)
MAX_CREATED_PER_USER = 25


class AccessDenied(ApiError):
    """Pedido recusado: ``code`` estável (traduzido pela API), ``message`` em PT para logs."""

    def __init__(self, code: str, message: str, status: int = 403, **params):
        super().__init__(code, status, message, **params)


def is_demo(user: dict) -> bool:
    """Conta pública de demonstração (password no README): só leitura nas contas e no perfil."""
    return bool(user.get("protected")) and user.get("role") != "admin"


def require_not_demo(user: dict) -> None:
    if is_demo(user):
        raise AccessDenied("demo_read_only", "Conta de demonstração: só leitura.")


def data_role(role: str) -> str:
    """Perfil que o RLS da BD conhece (o admin vê os dados como o Imperador)."""
    return "imperador" if role == "admin" else role


def effective_modules(role: str, modules) -> list[str]:
    """Módulos que a conta tem mesmo: os guardados (ou os por defeito) ∩ o máximo do perfil."""
    chosen = DEFAULT_MODULES[role] if modules is None else set(modules)
    allowed = chosen & ROLE_MODULES[role]
    if role == "admin":                    # o admin tem sempre tudo
        allowed = set(MODULES)
    return [m for m in MODULES if m in allowed]


def has_module(user: dict, module: str) -> bool:
    """True se o utilizador tem o módulo.

    Perfis sem a chave ``modules`` (scripts offline, CLI) têm acesso a tudo
    o que o perfil permite.
    """
    modules = user.get("modules")
    if modules is None:
        return module in ROLE_MODULES.get(user.get("role"), set())
    return module in modules


def in_scope(actor: dict, role: str, brand_id: int | None, store_brand: int | None,
             store_id: int | None) -> bool:
    """O âmbito da conta-alvo cabe no âmbito de quem atua?

    Args:
        actor: Quem cria/gere (``role``, ``brand_id``, ``store_id``).
        role, brand_id, store_id: Perfil e âmbito da conta-alvo.
        store_brand: Marca da loja da conta-alvo (se for de loja).
    """
    if actor["role"] in ("admin", "imperador"):
        return True
    if actor["role"] == "marca":
        target_brand = brand_id if role == "marca" else store_brand
        return target_brand is not None and target_brand == actor["brand_id"]
    # loja: só contas da mesma loja
    return role == "loja" and store_id == actor["store_id"]


def check_new_account(actor: dict, role: str, brand_id: int | None, store_id: int | None,
                      store_brand: int | None, modules: list[str] | None) -> list[str]:
    """Valida o perfil, o âmbito e os módulos de uma conta nova.

    Returns:
        Lista final de módulos (ordenada como ``MODULES``).

    Raises:
        AccessDenied: com o código do motivo.
    """
    require_not_demo(actor)
    if role not in ROLE_LEVEL:
        raise AccessDenied("bad_role", "Perfil inválido.", 400)
    if ROLE_LEVEL[role] < ROLE_LEVEL[actor["role"]]:
        raise AccessDenied("role_above", "Não podes criar contas acima do teu perfil.")
    if role in ("admin", "imperador") and (brand_id or store_id):
        raise AccessDenied("bad_scope", "Este perfil não tem marca nem loja.", 400)
    if role == "marca" and (not brand_id or store_id):
        raise AccessDenied("need_brand", "Escolhe a marca.", 400)
    if role == "loja" and (not store_id or brand_id):
        raise AccessDenied("need_store", "Escolhe a loja.", 400)
    if not in_scope(actor, role, brand_id, store_brand, store_id):
        raise AccessDenied("out_of_scope", "Essa marca/loja está fora do teu âmbito.")
    return check_modules(actor, role, modules)


def check_modules(actor: dict, role: str, modules: list[str] | None) -> list[str]:
    """Módulos pedidos ⊆ módulos de quem atua ∩ máximo do perfil-alvo."""
    wanted = NEW_ACCOUNT_MODULES & ROLE_MODULES[role] if modules is None else set(modules)
    unknown = wanted - set(MODULES)
    if unknown:
        raise AccessDenied("bad_module", f"Módulos desconhecidos: {sorted(unknown)}", 400)
    actor_modules = set(actor.get("modules") or effective_modules(actor["role"], None))
    if wanted - actor_modules:
        raise AccessDenied("module_not_yours", "Não podes dar módulos que tu próprio não tens.")
    if wanted - ROLE_MODULES[role]:
        raise AccessDenied("module_not_for_role", "Esse perfil não pode ter esse módulo.", 400)
    if not wanted & {"sql", "forecast", "orders"}:
        raise AccessDenied("no_modules", "A conta precisa de pelo menos um módulo de dados.", 400)
    return [m for m in MODULES if m in wanted]


def can_manage(actor: dict, target: dict) -> bool:
    """Quem atua pode alterar/apagar a conta-alvo?

    ``target`` tem ``id``, ``role``, ``brand_id``, ``store_id``, ``store_brand``,
    ``created_by`` e ``protected``.
    """
    if target["id"] == actor.get("id"):
        return False                                   # a própria conta muda-se no perfil
    if actor["role"] == "admin":
        return True
    if is_demo(actor):
        return False                                   # demo: só leitura
    if target.get("protected"):
        return False                                   # contas de demonstração
    level_actor, level_target = ROLE_LEVEL[actor["role"]], ROLE_LEVEL[target["role"]]
    if level_target < level_actor:
        return False
    if level_target == level_actor and target.get("created_by") != actor.get("id"):
        return False
    return in_scope(actor, target["role"], target.get("brand_id"), target.get("store_brand"),
                    target.get("store_id"))


def can_view(actor: dict, target: dict) -> bool:
    """Contas que aparecem na lista: as que gere, mais as protegidas do seu âmbito (só leitura)."""
    if target["id"] == actor.get("id"):
        return True
    if ROLE_LEVEL[target["role"]] < ROLE_LEVEL[actor["role"]]:
        return False
    return in_scope(actor, target["role"], target.get("brand_id"), target.get("store_brand"),
                    target.get("store_id"))
