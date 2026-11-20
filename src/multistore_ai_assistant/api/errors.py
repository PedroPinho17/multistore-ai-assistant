"""Erros da API num só formato e nas 4 línguas.

Todas as respostas de erro têm a forma ``{"detail": {"code": ..., "message": ...}}``:

- ``code`` é estável (a UI e os clientes da API podem decidir por ele);
- ``message`` vem na língua do pedido, lida do cabeçalho ``Accept-Language``
  (a UI envia a língua escolhida; sem cabeçalho, português).

O código de negócio levanta ``ApiError(code, status, **params)``; o handler em
``main.py`` traduz com ``CATALOG``. Mensagens com parâmetros usam ``{nome}``.
"""
from fastapi import Request

LANGS = ("pt", "en", "es", "fr")
DEFAULT_LANG = "pt"


class ApiError(Exception):
    """Erro com código estável, estado HTTP e parâmetros para a mensagem."""

    def __init__(self, code: str, status: int = 400, message: str | None = None, **params):
        super().__init__(message or code)
        self.code, self.status, self.params = code, status, params
        self.message = message or tr(code, DEFAULT_LANG, **params)


def request_lang(request: Request | None) -> str:
    """Língua do pedido: 1.ª entrada do ``Accept-Language`` que conhecemos (senão PT)."""
    if request is None:
        return DEFAULT_LANG
    for part in request.headers.get("accept-language", "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return DEFAULT_LANG


def tr(code: str, lang: str = DEFAULT_LANG, **params) -> str:
    """Mensagem traduzida de um código (o próprio código se não estiver no catálogo)."""
    entry = CATALOG.get(code)
    if not entry:
        return code
    text = entry.get(lang) or entry[DEFAULT_LANG]
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        return text


def _(pt: str, en: str, es: str, fr: str) -> dict:
    return {"pt": pt, "en": en, "es": es, "fr": fr}


CATALOG = {
    # sessão e login
    "session_invalid": _("Sessão inválida ou expirada.", "Invalid or expired session.",
                         "Sesión no válida o caducada.", "Session invalide ou expirée."),
    "bad_login": _("Utilizador ou palavra-passe errados.", "Wrong username or password.",
                   "Usuario o contraseña incorrectos.", "Nom d'utilisateur ou mot de passe incorrect."),
    "rate_limited": _("Demasiados pedidos. Tenta outra vez daqui a pouco.", "Too many requests. Try again shortly.",
                      "Demasiadas peticiones. Inténtalo de nuevo en un momento.", "Trop de requêtes. Réessaie dans un instant."),
    # conversas e perguntas
    "conv_not_found": _("Conversa não encontrada.", "Chat not found.", "Conversación no encontrada.", "Conversation introuvable."),
    "answer_not_found": _("Resposta não encontrada.", "Answer not found.", "Respuesta no encontrada.", "Réponse introuvable."),
    "unavailable": _("O assistente está indisponível de momento. Tenta outra vez.",
                     "The assistant is unavailable right now. Please try again.",
                     "El asistente no está disponible en este momento. Inténtalo de nuevo.",
                     "L'assistant est indisponible pour le moment. Réessaie plus tard."),
    "llm_quota": _("O modelo de linguagem atingiu o limite de utilização. Tenta outra vez daqui a alguns minutos.",
                   "The language model has hit its usage limit. Please try again in a few minutes.",
                   "El modelo de lenguaje ha alcanzado su límite de uso. Inténtalo de nuevo en unos minutos.",
                   "Le modèle de langage a atteint sa limite d'utilisation. Réessaie dans quelques minutes."),
    "cannot_teach": _("A tua conta não pode ensinar o assistente.", "Your account can't teach the assistant.",
                      "Tu cuenta no puede enseñar al asistente.", "Ton compte ne peut pas entraîner l'assistant."),
    "example_exists": _("Já existe um exemplo com esta pergunta.", "There's already an example with this question.",
                        "Ya existe un ejemplo con esta pregunta.", "Un exemple avec cette question existe déjà."),
    "example_not_found": _("Exemplo não encontrado.", "Example not found.", "Ejemplo no encontrado.", "Exemple introuvable."),
    "review_not_found": _("Esta resposta já não está por rever.", "This answer is no longer waiting for review.",
                          "Esta respuesta ya no está pendiente de revisión.", "Cette réponse n'est plus à revoir."),
    "review_not_sql": _("Respostas de previsão não têm SQL para corrigir: podes ignorá-las.",
                        "Forecast answers have no SQL to fix: you can dismiss them.",
                        "Las respuestas de previsión no tienen SQL que corregir: puedes ignorarlas.",
                        "Les réponses de prévision n'ont pas de SQL à corriger : tu peux les ignorer."),
    "invalid_sql": _("O SQL não passou na validação: {reason}", "The SQL failed validation: {reason}",
                     "El SQL no ha pasado la validación: {reason}", "Le SQL n'a pas passé la validation : {reason}"),
    "sql_not_running": _("O SQL não corre nesta base de dados.", "The SQL doesn't run on this database.",
                         "El SQL no se ejecuta en esta base de datos.", "Le SQL ne s'exécute pas sur cette base de données."),
    # permissões e módulos
    "no_module": _("A tua conta não tem o módulo «{module}».", "Your account doesn't have the “{module}” module.",
                   "Tu cuenta no tiene el módulo «{module}».", "Ton compte n'a pas le module « {module} »."),
    "admin_only": _("Só o admin pode fazer isto.", "Only the admin can do this.",
                    "Solo el admin puede hacer esto.", "Seul l'admin peut faire ceci."),
    "bad_role": _("Perfil inválido.", "Invalid role.", "Perfil no válido.", "Profil invalide."),
    "role_above": _("Não podes criar contas acima do teu perfil.", "You can't create accounts above your own role.",
                    "No puedes crear cuentas por encima de tu perfil.", "Tu ne peux pas créer de comptes au-dessus de ton profil."),
    "bad_scope": _("Este perfil não tem marca nem loja.", "This role has no brand or store.",
                   "Este perfil no tiene marca ni tienda.", "Ce profil n'a ni marque ni magasin."),
    "need_brand": _("Escolhe a marca.", "Choose the brand.", "Elige la marca.", "Choisis la marque."),
    "need_store": _("Escolhe a loja.", "Choose the store.", "Elige la tienda.", "Choisis le magasin."),
    "out_of_scope": _("Essa marca ou loja está fora do teu âmbito.", "That brand or store is outside your scope.",
                      "Esa marca o tienda está fuera de tu ámbito.", "Cette marque ou ce magasin est hors de ton périmètre."),
    "bad_module": _("Módulo desconhecido.", "Unknown module.", "Módulo desconocido.", "Module inconnu."),
    "module_not_yours": _("Não podes dar módulos que tu próprio não tens.", "You can't grant modules you don't have yourself.",
                          "No puedes dar módulos que tú no tienes.", "Tu ne peux pas donner des modules que tu n'as pas."),
    "module_not_for_role": _("Esse perfil não pode ter um dos módulos escolhidos.", "That role can't have one of the chosen modules.",
                             "Ese perfil no puede tener uno de los módulos elegidos.", "Ce profil ne peut pas avoir l'un des modules choisis."),
    "no_modules": _("A conta precisa de pelo menos um módulo de dados.", "The account needs at least one data module.",
                    "La cuenta necesita al menos un módulo de datos.", "Le compte a besoin d'au moins un module de données."),
    # contas
    "bad_username": _("Nome de utilizador inválido (3–32: letras minúsculas, números, . _ -).",
                      "Invalid username (3–32: lowercase letters, numbers, . _ -).",
                      "Nombre de usuario no válido (3–32: minúsculas, números, . _ -).",
                      "Nom d'utilisateur invalide (3–32 : minuscules, chiffres, . _ -)."),
    "too_many_users": _("Limite de {n} contas criadas.", "Limit of {n} created accounts reached.",
                        "Límite de {n} cuentas creadas.", "Limite de {n} comptes créés atteinte."),
    "username_taken": _("Esse nome de utilizador já existe.", "That username already exists.",
                        "Ese nombre de usuario ya existe.", "Ce nom d'utilisateur existe déjà."),
    "not_found": _("Conta não encontrada.", "Account not found.", "Cuenta no encontrada.", "Compte introuvable."),
    "demo_read_only": _("Conta de demonstração: só leitura. Podes ver, mas não criar nem alterar contas, passwords ou fotos.",
                        "Demo account: read-only. You can look, but not create or change accounts, passwords or photos.",
                        "Cuenta de demostración: solo lectura. Puedes ver, pero no crear ni modificar cuentas, contraseñas o fotos.",
                        "Compte de démonstration : lecture seule. Tu peux consulter, mais pas créer ni modifier des comptes, mots de passe ou photos."),
    "cannot_manage": _("Não podes alterar esta conta.", "You can't change this account.",
                       "No puedes modificar esta cuenta.", "Tu ne peux pas modifier ce compte."),
    # passwords
    "pw_too_short": _("A palavra-passe tem de ter pelo menos {n} caracteres.", "The password must have at least {n} characters.",
                      "La contraseña debe tener al menos {n} caracteres.", "Le mot de passe doit avoir au moins {n} caractères."),
    "pw_too_long": _("A palavra-passe é demasiado longa.", "The password is too long.",
                     "La contraseña es demasiado larga.", "Le mot de passe est trop long."),
    "pw_same": _("A nova palavra-passe tem de ser diferente da atual.", "The new password must be different from the current one.",
                 "La nueva contraseña debe ser distinta de la actual.", "Le nouveau mot de passe doit être différent de l'actuel."),
    "pw_has_username": _("A palavra-passe não pode conter o nome de utilizador.", "The password can't contain the username.",
                         "La contraseña no puede contener el nombre de usuario.", "Le mot de passe ne peut pas contenir le nom d'utilisateur."),
    "pw_mix": _("Usa letras e números (ou símbolos) na palavra-passe.", "Use letters and numbers (or symbols) in the password.",
                "Usa letras y números (o símbolos) en la contraseña.", "Utilise des lettres et des chiffres (ou symboles)."),
    "pw_wrong_current": _("A palavra-passe atual está errada.", "The current password is wrong.",
                          "La contraseña actual es incorrecta.", "Le mot de passe actuel est incorrect."),
    # recuperação de password e email da conta
    "reset_demo": _("As contas de demonstração não recuperam a palavra-passe: é pública e está na página de entrada.",
                    "Demo accounts can't reset their password: it is public and shown on the sign-in page.",
                    "Las cuentas de demostración no restablecen la contraseña: es pública y aparece en la página de acceso.",
                    "Les comptes de démonstration ne réinitialisent pas leur mot de passe : il est public et affiché sur la page de connexion."),
    "reset_invalid": _("Este link de recuperação é inválido, expirou ou já foi usado. Pede um novo.",
                       "This reset link is invalid, has expired or was already used. Ask for a new one.",
                       "Este enlace de recuperación no es válido, ha caducado o ya se usó. Pide uno nuevo.",
                       "Ce lien de réinitialisation est invalide, a expiré ou a déjà été utilisé. Demandes-en un nouveau."),
    "bad_email": _("Email inválido.", "Invalid email.", "Correo electrónico no válido.", "E-mail invalide."),
    "email_taken": _("Esse email já está associado a outra conta.", "That email is already used by another account.",
                     "Ese correo ya está asociado a otra cuenta.", "Cet e-mail est déjà utilisé par un autre compte."),
    "demo_no_email": _("As contas de demonstração não têm email.", "Demo accounts have no email.",
                       "Las cuentas de demostración no tienen correo.", "Les comptes de démonstration n'ont pas d'e-mail."),
    # foto de perfil
    "avatar_too_big": _("A imagem tem mais de 2 MB.", "The image is larger than 2 MB.",
                        "La imagen pesa más de 2 MB.", "L'image dépasse 2 Mo."),
    "avatar_bad_format": _("Formato inválido: usa PNG, JPEG ou WebP.", "Invalid format: use PNG, JPEG or WebP.",
                           "Formato no válido: usa PNG, JPEG o WebP.", "Format invalide : utilise PNG, JPEG ou WebP."),
    "avatar_corrupt": _("Imagem corrompida.", "Corrupted image.", "Imagen dañada.", "Image corrompue."),
    "avatar_not_image": _("O ficheiro não é uma imagem PNG, JPEG ou WebP válida.",
                          "The file isn't a valid PNG, JPEG or WebP image.",
                          "El archivo no es una imagen PNG, JPEG o WebP válida.",
                          "Le fichier n'est pas une image PNG, JPEG ou WebP valide."),
    "avatar_not_found": _("Foto não encontrada.", "Photo not found.", "Foto no encontrada.", "Photo introuvable."),
    # definições
    "bad_setting": _("Valor inválido: {detail}", "Invalid value: {detail}", "Valor no válido: {detail}", "Valeur invalide : {detail}"),
}
