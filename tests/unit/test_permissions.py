"""Regras de perfis e módulos (funções puras de api.permissions)."""
import pytest

from multistore_ai_assistant.api.permissions import (
    MODULES,
    ROLE_MODULES,
    AccessDenied,
    can_manage,
    can_view,
    check_modules,
    check_new_account,
    data_role,
    effective_modules,
    has_module,
    in_scope,
)
from tests.conftest import ADMIN, IMPERADOR, LOJA, MARCA

OTHER_BRAND = 2
OTHER_STORE = 9          # loja de outra marca


def target(id=50, role="loja", brand_id=None, store_id=1, store_brand=1, created_by=None, protected=False):
    return {"id": id, "role": role, "brand_id": brand_id, "store_id": store_id,
            "store_brand": store_brand, "created_by": created_by, "protected": protected}


# ---------- módulos ----------

def test_admin_always_has_every_module():
    assert effective_modules("admin", ["sql"]) == list(MODULES)


@pytest.mark.parametrize("role", ["imperador", "marca", "loja"])
def test_accounts_without_saved_modules_get_everything_their_role_allows(role):
    assert set(effective_modules(role, None)) == ROLE_MODULES[role]


def test_saved_modules_are_capped_by_the_role():
    """Mesmo que a BD tenha 'observability' numa loja, a conta não o recebe."""
    assert effective_modules("loja", ["sql", "observability", "teach"]) == ["sql"]


def test_modules_keep_a_stable_order():
    assert effective_modules("imperador", ["users", "sql"]) == ["sql", "users"]


def test_only_admin_gets_observability():
    assert all("observability" not in ROLE_MODULES[r] for r in ("imperador", "marca", "loja"))


def test_teach_is_only_for_admin_and_imperador():
    """Os exemplos RAG servem a todos: uma loja não pode ensinar SQL ao grupo inteiro."""
    assert "teach" in ROLE_MODULES["imperador"]
    assert "teach" not in ROLE_MODULES["marca"] | ROLE_MODULES["loja"]


def test_has_module_reads_the_profile():
    assert has_module(LOJA, "sql") and not has_module(LOJA, "observability")
    assert has_module(ADMIN, "observability")


def test_offline_profiles_without_modules_key_use_the_role():
    assert has_module({"role": "imperador"}, "teach")
    assert not has_module({"role": "loja"}, "teach")


@pytest.mark.parametrize("role,expected", [("admin", "imperador"), ("imperador", "imperador"),
                                           ("marca", "marca"), ("loja", "loja")])
def test_rls_sees_admin_as_imperador(role, expected):
    assert data_role(role) == expected


# ---------- âmbito ----------

@pytest.mark.parametrize("actor", [ADMIN, IMPERADOR])
def test_group_wide_roles_reach_everything(actor):
    assert in_scope(actor, "marca", OTHER_BRAND, None, None)
    assert in_scope(actor, "loja", None, OTHER_BRAND, OTHER_STORE)


def test_brand_manager_scope_is_their_brand():
    assert in_scope(MARCA, "marca", 1, None, None)
    assert in_scope(MARCA, "loja", None, 1, 5)
    assert not in_scope(MARCA, "marca", OTHER_BRAND, None, None)
    assert not in_scope(MARCA, "loja", None, OTHER_BRAND, OTHER_STORE)


def test_store_manager_scope_is_their_store():
    assert in_scope(LOJA, "loja", None, 1, 1)
    assert not in_scope(LOJA, "loja", None, 1, 2)       # outra loja da mesma marca
    assert not in_scope(LOJA, "marca", 1, None, None)


# ---------- criar contas ----------

@pytest.mark.parametrize("actor,role", [
    (MARCA, "imperador"), (MARCA, "admin"), (LOJA, "marca"), (LOJA, "imperador"), (IMPERADOR, "admin"),
])
def test_cannot_create_accounts_above_your_level(actor, role):
    scope = {"brand_id": 1} if role == "marca" else {}
    with pytest.raises(AccessDenied) as e:
        check_new_account(actor, role, scope.get("brand_id"), None, None, None)
    assert e.value.code == "role_above"


@pytest.mark.parametrize("actor,role,brand,store,store_brand", [
    (ADMIN, "admin", None, None, None),
    (IMPERADOR, "imperador", None, None, None),        # mesmo nível
    (IMPERADOR, "marca", OTHER_BRAND, None, None),
    (MARCA, "marca", 1, None, None),                    # mesmo nível, mesma marca
    (MARCA, "loja", None, 5, 1),
    (LOJA, "loja", None, 1, 1),                         # mesmo nível, mesma loja
])
def test_can_create_same_level_or_below_within_scope(actor, role, brand, store, store_brand):
    assert check_new_account(actor, role, brand, store, store_brand, None) == ["sql", "forecast", "orders"]


@pytest.mark.parametrize("actor,role,brand,store,store_brand", [
    (MARCA, "marca", OTHER_BRAND, None, None),
    (MARCA, "loja", None, OTHER_STORE, OTHER_BRAND),
    (LOJA, "loja", None, 2, 1),
])
def test_cannot_create_outside_your_scope(actor, role, brand, store, store_brand):
    with pytest.raises(AccessDenied) as e:
        check_new_account(actor, role, brand, store, store_brand, None)
    assert e.value.code == "out_of_scope"


@pytest.mark.parametrize("role,brand,store,code", [
    ("marca", None, None, "need_brand"), ("marca", 1, 1, "need_brand"),
    ("loja", None, None, "need_store"), ("loja", 1, 1, "need_store"),
    ("imperador", 1, None, "bad_scope"), ("chefe", None, None, "bad_role"),
])
def test_scope_must_match_the_role(role, brand, store, code):
    with pytest.raises(AccessDenied) as e:
        check_new_account(ADMIN, role, brand, store, 1, None)
    assert e.value.code == code and e.value.status == 400


def test_new_accounts_get_data_modules_unless_more_are_chosen():
    assert check_modules(IMPERADOR, "marca", None) == ["sql", "forecast", "orders"]
    assert check_modules(IMPERADOR, "marca", ["sql", "users"]) == ["sql", "users"]


def test_cannot_give_modules_you_do_not_have():
    me = {**MARCA, "modules": ["sql", "users"]}
    with pytest.raises(AccessDenied) as e:
        check_modules(me, "loja", ["sql", "forecast"])
    assert e.value.code == "module_not_yours"


def test_cannot_give_modules_the_role_cannot_have():
    with pytest.raises(AccessDenied) as e:
        check_modules(ADMIN, "loja", ["sql", "teach"])
    assert e.value.code == "module_not_for_role"


def test_account_needs_at_least_one_data_module():
    with pytest.raises(AccessDenied) as e:
        check_modules(IMPERADOR, "marca", ["users"])
    assert e.value.code == "no_modules"


def test_unknown_modules_are_rejected():
    with pytest.raises(AccessDenied) as e:
        check_modules(ADMIN, "loja", ["sql", "root"])
    assert e.value.code == "bad_module"


# ---------- gerir contas ----------

def test_nobody_manages_their_own_account_here():
    assert not can_manage(IMPERADOR, target(id=IMPERADOR["id"], role="imperador", store_id=None))


def test_admin_manages_everything_including_demo_accounts():
    assert can_manage(ADMIN, target(protected=True))
    assert can_manage(ADMIN, target(role="admin", store_id=None))


def test_demo_accounts_are_read_only_for_everyone_else():
    assert not can_manage(IMPERADOR, target(protected=True))


def test_lower_levels_in_scope_are_manageable():
    assert can_manage(IMPERADOR, target(role="marca", brand_id=OTHER_BRAND, store_id=None))
    assert can_manage(MARCA, target(store_brand=1))
    assert not can_manage(MARCA, target(store_id=OTHER_STORE, store_brand=OTHER_BRAND))


def test_same_level_only_if_you_created_it():
    peer = target(role="marca", brand_id=1, store_id=None)
    assert not can_manage(MARCA, peer)
    assert can_manage(MARCA, {**peer, "created_by": MARCA["id"]})


def test_higher_levels_are_never_manageable():
    assert not can_manage(MARCA, target(role="imperador", store_id=None, created_by=MARCA["id"]))


def test_listing_hides_higher_levels_and_other_scopes():
    assert can_view(MARCA, target(protected=True))                       # vê a demo da sua marca (só leitura)
    assert not can_view(MARCA, target(role="imperador", store_id=None))
    assert not can_view(MARCA, target(store_id=OTHER_STORE, store_brand=OTHER_BRAND))
    assert not can_view(IMPERADOR, target(role="admin", store_id=None))  # o admin é invisível
