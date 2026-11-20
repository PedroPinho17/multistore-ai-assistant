"""Corpos dos pedidos (validação Pydantic): tamanhos máximos e valores permitidos."""
from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["pt", "en", "es", "fr"]
Module = Literal["sql", "forecast", "orders", "teach", "users", "observability"]
# Uma das 6 cores ou uma cor personalizada #rrggbb
ACCENT_PATTERN = r"^(green|orange|blue|wine|purple|graphite|#[0-9a-fA-F]{6})$"


class LoginIn(BaseModel):
    """Corpo do POST /login."""
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AskIn(BaseModel):
    """Corpo do POST /ask e /ask/stream."""
    question: str = Field(min_length=1, max_length=500)
    lang: Lang = "pt"
    conversation_id: int | None = None


class FeedbackIn(BaseModel):
    """Corpo do POST /feedback (exemplo pergunta→SQL para o RAG)."""
    question: str = Field(min_length=1, max_length=500)
    sql: str = Field(min_length=1, max_length=10_000)


class ReviewSqlIn(BaseModel):
    """Corpo do POST /review/{id}/preview: SQL corrigido para testar."""
    sql: str = Field(min_length=1, max_length=10_000)


class ReviewTeachIn(BaseModel):
    """Corpo do POST /review/{id}/teach: a pergunta como fica no exemplo e o SQL corrigido."""
    question: str = Field(min_length=1, max_length=500)
    sql: str = Field(min_length=1, max_length=10_000)


class ExampleIn(BaseModel):
    """Corpo do POST/PUT /examples: um exemplo do RAG."""
    question: str = Field(min_length=3, max_length=500)
    sql: str = Field(min_length=1, max_length=10_000)


class ExplainIn(BaseModel):
    """Corpo do POST /explain: o SQL de uma resposta da própria conta."""
    request_id: int
    lang: Lang = "pt"


class RatingIn(BaseModel):
    """Corpo do POST /ratings: 1 = 👍, -1 = 👎, 0 = tirar a avaliação."""
    request_id: int
    rating: Literal[-1, 0, 1]


class RenameIn(BaseModel):
    """Corpo do PATCH /conversations/{id}."""
    title: str = Field(min_length=1, max_length=80)


class PasswordIn(BaseModel):
    """Corpo do POST /profile/password."""
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class ForgotIn(BaseModel):
    """Corpo do POST /password/forgot: email (ou nome de utilizador) e a língua do email."""
    login: str = Field(min_length=3, max_length=254)
    lang: Lang = "pt"


class ResetIn(BaseModel):
    """Corpo do POST /password/reset: o token do link e a nova password."""
    token: str = Field(min_length=20, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class EmailIn(BaseModel):
    """Corpo do PUT /profile/email: ``null`` ou vazio tira o email."""
    email: str | None = Field(default=None, max_length=254)


class AvatarIn(BaseModel):
    """Corpo do POST /profile/avatar: data URL PNG/JPEG/WebP (a UI envia 160×160)."""
    image: str = Field(min_length=1, max_length=100_000)


class NewUserIn(BaseModel):
    """Corpo do POST /users."""
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    role: Literal["admin", "imperador", "marca", "loja"]
    brand_id: int | None = None
    store_id: int | None = None
    modules: list[Module] | None = Field(default=None, max_length=10)
    email: str | None = Field(default=None, max_length=254)


class UserPatchIn(BaseModel):
    """Corpo do PATCH /users/{id}: só os campos enviados mudam (``email: ""`` tira o email)."""
    modules: list[Module] | None = Field(default=None, max_length=10)
    active: bool | None = None
    password: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=254)


class UserSettingsIn(BaseModel):
    """Corpo do PUT /settings/me: só os campos enviados mudam; ``null`` = predefinição."""
    model_config = {"extra": "forbid"}
    lang: Lang | None = None
    theme: Literal["light", "dark", "system"] | None = None
    accent: str | None = Field(default=None, pattern=ACCENT_PATTERN)


class AppSettingsIn(BaseModel):
    """Corpo do PUT /settings/app (só admin)."""
    model_config = {"extra": "forbid"}
    default_accent: str | None = Field(default=None, pattern=ACCENT_PATTERN)
    default_lang: Lang | None = None
    show_demo_accounts: bool | None = None
    session_hours: Literal[1, 2, 4, 8, 12, 24] | None = None
