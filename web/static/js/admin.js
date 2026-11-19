/* Gestão de contas (/users), observabilidade (/admin) e avaliação 👍/👎 das respostas.
 *
 * Carregado antes do script principal do index.html. Define:
 *   - ADMIN_TEXTS e installAdminTexts(TEXTS): textos destas páginas nas 4 línguas;
 *   - AdminMixin: estado e métodos que o Vue junta à aplicação principal.
 * Os templates estão no index.html (como as outras páginas).
 */
"use strict";

const MODULE_ORDER = ["sql", "forecast", "orders", "teach", "users", "observability"];
const DATA_MODULES = ["sql", "forecast", "orders"];
const DASH_DAYS = [1, 7, 30, 90];
const adminCharts = {};

const ADMIN_TEXTS = {
  pt: {
    correct: "guardar como exemplo",
    roles: { admin: "Administrador" },
    pageTitles: { users: "Contas · Multistore AI", admin: "Observabilidade · Multistore AI" },
    nav: { chat: "Chat", users: "Contas", admin: "Painel", profile: "Perfil", main: "Navegação", close: "Fechar menu", account: "Conta" },
    rate: { label: "Avaliar resposta", up: "Boa resposta", down: "Má resposta", thanks: "Obrigado! Vamos rever esta resposta." },
    mods: { sql: "Perguntas aos dados", forecast: "Previsão de vendas", orders: "Sugestão de encomendas",
            teach: "Ensinar o assistente", users: "Gerir contas", observability: "Observabilidade" },
    modsHint: { sql: "Vendas, stock, equipas, margens…", forecast: "Faturação prevista (7 dias)", orders: "Ingredientes a encomendar",
                teach: "Guardar respostas certas como exemplos", users: "Criar contas do mesmo nível ou abaixo", observability: "Painel de métricas" },
    errors: {
      no_module: "A tua conta não tem acesso a esta área.",
      role_above: "Não podes criar contas acima do teu perfil.",
      out_of_scope: "Essa marca ou loja está fora do teu âmbito.",
      need_brand: "Escolhe a marca.", need_store: "Escolhe a loja.",
      bad_scope: "Este perfil não tem marca nem loja.", bad_role: "Perfil inválido.",
      module_not_yours: "Não podes dar módulos que tu próprio não tens.",
      module_not_for_role: "Esse perfil não pode ter um dos módulos escolhidos.",
      no_modules: "Escolhe pelo menos um módulo de dados (perguntas, previsão ou encomendas).",
      bad_module: "Módulo desconhecido.",
      bad_username: "Nome de utilizador inválido: 3 a 32 caracteres (letras minúsculas, números, . _ -).",
      weak_password: "Password fraca: pelo menos 8 caracteres, com letras e números, sem o nome de utilizador.",
      username_taken: "Esse nome de utilizador já existe.",
      too_many_users: "Atingiste o limite de contas criadas.",
      cannot_manage: "Não podes alterar esta conta.", not_found: "Conta não encontrada.",
    },
    p: { kinds: { denied: "Sem acesso" } },
    um: {
      title: "Contas", sub: "Cria e gere contas do teu nível ou abaixo, dentro do teu âmbito. Só podes dar módulos que tu próprio tens.",
      newBtn: "Nova conta", newTitle: "Nova conta", username: "Nome de utilizador",
      usernameHint: "3 a 32 caracteres: letras minúsculas, números, . _ -", password: "Password inicial",
      generate: "Gerar", generated: "Password gerada. Copia-a antes de criar a conta.", role: "Perfil",
      brand: "Marca", store: "Loja", choose: "Escolher…", modules: "Módulos", create: "Criar conta", cancel: "Cancelar",
      created: u => `Conta ${u} criada.`, search: "Procurar", allRoles: "Todos os perfis", allStatus: "Todos os estados",
      active: "Ativa", inactive: "Desativada", you: "tu", demo: "Demo",
      demoHint: "Conta pública de demonstração: só o admin a pode alterar.",
      createdBy: n => `criada por ${n}`, never: "nunca entrou", lastLogin: "Último acesso",
      edit: "Editar", save: "Guardar", saved: "Alterações guardadas.", newPassword: "Nova password (opcional)",
      disable: "Desativar", enable: "Ativar", delete: "Apagar",
      disableTitle: "Desativar conta?", disableText: "A pessoa deixa de conseguir entrar e a sessão aberta termina já.",
      disabled: "Conta desativada.", enabled: "Conta ativada.",
      deleteTitle: "Apagar conta?", deleteText: "A conta e as conversas dela vão ser apagadas. Não dá para desfazer.",
      deleted: "Conta apagada.", empty: "Nenhuma conta corresponde à pesquisa.",
      count: n => `${n} conta${n === 1 ? "" : "s"}`, scopeAll: "Todo o grupo", readOnly: "Só leitura", actions: "Ações",
    },
    adm: {
      title: "Observabilidade", sub: "Cada pergunta fica registada: tempo, intenção, SQL, tokens do LLM e avaliação.",
      period: "Período", days: { 1: "24 h", 7: "7 dias", 30: "30 dias", 90: "90 dias" }, refresh: "Atualizar",
      updated: "Atualizado às", requests: "Pedidos", users: n => `${n} utilizador${n === 1 ? "" : "es"}`,
      errorRate: "Taxa de erro", errorsN: n => `${n} sem resposta`, latency: "Latência p50 / p95",
      tokens: "Tokens por pedido", tokensTotal: n => `${n} no total`, satisfaction: "Satisfação",
      ratings: (u, d) => `${u} positiva${u === 1 ? "" : "s"} · ${d} negativa${d === 1 ? "" : "s"}`, noRatings: "sem avaliações", sqlFail: "SQL com erro",
      recovered: n => `${n} corrigido${n === 1 ? "" : "s"} na 2.ª tentativa`, classifier: "Decididas localmente",
      classifierHint: "intenção sem chamar o LLM", cache: "Cache de SQL", cacheHint: (n) => `${n} respostas sem gerar SQL de novo`, daily: "Pedidos por dia", ok: "Com resposta", failed: "Erro",
      intents: "Intenções (classificador local)", kinds: "Por tipo de resposta", kind: "Tipo", n: "N.º",
      avg: "Média", avgTokens: "Tokens", top: "Perguntas mais feitas", question: "Pergunta", times: "Vezes",
      down: "Respostas mal avaliadas", noDown: "Nenhuma resposta mal avaliada neste período.", errors: "Erros recentes",
      noErrors: "Sem erros neste período.", byUser: "Por utilizador", user: "Utilizador", last: "Último",
      eval: "Avaliação contínua do text-to-SQL", evalSub: "Execution accuracy nas 40 perguntas de eval/questions.json, guardada em cada corrida.",
      evalHow: "Nova corrida:", model: "Modelo", accuracy: "Accuracy", date: "Data", level: "Nível", runs: "Corridas",
      allLevels: "todos", imported: "importado", noEval: "Ainda não há corridas guardadas.",
      empty: "Ainda não há pedidos neste período. Faz perguntas no chat e volta aqui.",
      intentNames: { data: "Dados (SQL)", forecast: "Previsão", orders: "Encomendas", chat: "Conversa",
                     personal_data: "Dados pessoais", write: "Pedido de escrita", off_topic: "Fora de âmbito", llm: "Decide o LLM" },
      kindNames: { sql: "SQL", forecast: "Previsão", orders: "Encomendas", no_sql: "Conversa", denied: "Sem módulo",
                   error: "Erro", exception: "Falha técnica" },
    },
  },
  en: {
    correct: "save as example",
    roles: { admin: "Administrator" },
    pageTitles: { users: "Accounts · Multistore AI", admin: "Observability · Multistore AI" },
    nav: { chat: "Chat", users: "Accounts", admin: "Dashboard", profile: "Profile", main: "Navigation", close: "Close menu", account: "Account" },
    rate: { label: "Rate answer", up: "Good answer", down: "Bad answer", thanks: "Thanks! We'll review this answer." },
    mods: { sql: "Data questions", forecast: "Sales forecast", orders: "Order suggestions",
            teach: "Teach the assistant", users: "Manage accounts", observability: "Observability" },
    modsHint: { sql: "Sales, stock, staff, margins…", forecast: "Forecast revenue (7 days)", orders: "Ingredients to order",
                teach: "Save correct answers as examples", users: "Create accounts at the same level or below", observability: "Metrics dashboard" },
    errors: {
      no_module: "Your account can't access this area.",
      role_above: "You can't create accounts above your own role.",
      out_of_scope: "That brand or store is outside your scope.",
      need_brand: "Choose the brand.", need_store: "Choose the store.",
      bad_scope: "This role has no brand or store.", bad_role: "Invalid role.",
      module_not_yours: "You can't grant modules you don't have yourself.",
      module_not_for_role: "That role can't have one of the chosen modules.",
      no_modules: "Choose at least one data module (questions, forecast or orders).",
      bad_module: "Unknown module.",
      bad_username: "Invalid username: 3 to 32 characters (lowercase letters, numbers, . _ -).",
      weak_password: "Weak password: at least 8 characters, letters and numbers, without the username.",
      username_taken: "That username already exists.",
      too_many_users: "You've reached the limit of accounts you can create.",
      cannot_manage: "You can't change this account.", not_found: "Account not found.",
    },
    p: { kinds: { denied: "No access" } },
    um: {
      title: "Accounts", sub: "Create and manage accounts at your level or below, within your scope. You can only grant modules you have.",
      newBtn: "New account", newTitle: "New account", username: "Username",
      usernameHint: "3 to 32 characters: lowercase letters, numbers, . _ -", password: "Initial password",
      generate: "Generate", generated: "Password generated. Copy it before creating the account.", role: "Role",
      brand: "Brand", store: "Store", choose: "Choose…", modules: "Modules", create: "Create account", cancel: "Cancel",
      created: u => `Account ${u} created.`, search: "Search", allRoles: "All roles", allStatus: "All statuses",
      active: "Active", inactive: "Disabled", you: "you", demo: "Demo",
      demoHint: "Public demo account: only the admin can change it.",
      createdBy: n => `created by ${n}`, never: "never signed in", lastLogin: "Last sign-in",
      edit: "Edit", save: "Save", saved: "Changes saved.", newPassword: "New password (optional)",
      disable: "Disable", enable: "Enable", delete: "Delete",
      disableTitle: "Disable account?", disableText: "The person can no longer sign in and any open session ends now.",
      disabled: "Account disabled.", enabled: "Account enabled.",
      deleteTitle: "Delete account?", deleteText: "The account and its chats will be deleted. This can't be undone.",
      deleted: "Account deleted.", empty: "No account matches your search.",
      count: n => `${n} account${n === 1 ? "" : "s"}`, scopeAll: "Whole group", readOnly: "Read-only", actions: "Actions",
    },
    adm: {
      title: "Observability", sub: "Every question is logged: time, intent, SQL, LLM tokens and rating.",
      period: "Period", days: { 1: "24 h", 7: "7 days", 30: "30 days", 90: "90 days" }, refresh: "Refresh",
      updated: "Updated at", requests: "Requests", users: n => `${n} user${n === 1 ? "" : "s"}`,
      errorRate: "Error rate", errorsN: n => `${n} unanswered`, latency: "Latency p50 / p95",
      tokens: "Tokens per request", tokensTotal: n => `${n} in total`, satisfaction: "Satisfaction",
      ratings: (u, d) => `${u} positive · ${d} negative`, noRatings: "no ratings", sqlFail: "SQL with errors",
      recovered: n => `${n} fixed on the 2nd attempt`, classifier: "Decided locally",
      classifierHint: "intent without calling the LLM", cache: "SQL cache", cacheHint: (n) => `${n} answers without generating SQL again`, daily: "Requests per day", ok: "Answered", failed: "Error",
      intents: "Intents (local classifier)", kinds: "By answer type", kind: "Type", n: "Count",
      avg: "Average", avgTokens: "Tokens", top: "Most asked questions", question: "Question", times: "Times",
      down: "Answers rated down", noDown: "No answers rated down in this period.", errors: "Recent errors",
      noErrors: "No errors in this period.", byUser: "By user", user: "User", last: "Last",
      eval: "Continuous text-to-SQL evaluation", evalSub: "Execution accuracy on the 40 questions in eval/questions.json, saved on every run.",
      evalHow: "New run:", model: "Model", accuracy: "Accuracy", date: "Date", level: "Level", runs: "Runs",
      allLevels: "all", imported: "imported", noEval: "No saved runs yet.",
      empty: "No requests in this period yet. Ask something in the chat and come back.",
      intentNames: { data: "Data (SQL)", forecast: "Forecast", orders: "Orders", chat: "Chat",
                     personal_data: "Personal data", write: "Write request", off_topic: "Off-topic", llm: "LLM decides" },
      kindNames: { sql: "SQL", forecast: "Forecast", orders: "Orders", no_sql: "Chat", denied: "No module",
                   error: "Error", exception: "Technical failure" },
    },
  },
  es: {
    correct: "guardar como ejemplo",
    roles: { admin: "Administrador" },
    pageTitles: { users: "Cuentas · Multistore AI", admin: "Observabilidad · Multistore AI" },
    nav: { chat: "Chat", users: "Cuentas", admin: "Panel", profile: "Perfil", main: "Navegación", close: "Cerrar menú", account: "Cuenta" },
    rate: { label: "Valorar respuesta", up: "Buena respuesta", down: "Mala respuesta", thanks: "¡Gracias! Revisaremos esta respuesta." },
    mods: { sql: "Preguntas sobre los datos", forecast: "Previsión de ventas", orders: "Sugerencia de pedidos",
            teach: "Enseñar al asistente", users: "Gestionar cuentas", observability: "Observabilidad" },
    modsHint: { sql: "Ventas, stock, equipos, márgenes…", forecast: "Facturación prevista (7 días)", orders: "Ingredientes a pedir",
                teach: "Guardar respuestas correctas como ejemplos", users: "Crear cuentas del mismo nivel o inferior", observability: "Panel de métricas" },
    errors: {
      no_module: "Tu cuenta no tiene acceso a esta área.",
      role_above: "No puedes crear cuentas por encima de tu perfil.",
      out_of_scope: "Esa marca o tienda está fuera de tu ámbito.",
      need_brand: "Elige la marca.", need_store: "Elige la tienda.",
      bad_scope: "Este perfil no tiene marca ni tienda.", bad_role: "Perfil no válido.",
      module_not_yours: "No puedes dar módulos que tú no tienes.",
      module_not_for_role: "Ese perfil no puede tener uno de los módulos elegidos.",
      no_modules: "Elige al menos un módulo de datos (preguntas, previsión o pedidos).",
      bad_module: "Módulo desconocido.",
      bad_username: "Nombre de usuario no válido: de 3 a 32 caracteres (minúsculas, números, . _ -).",
      weak_password: "Contraseña débil: al menos 8 caracteres, con letras y números, sin el nombre de usuario.",
      username_taken: "Ese nombre de usuario ya existe.",
      too_many_users: "Has alcanzado el límite de cuentas creadas.",
      cannot_manage: "No puedes modificar esta cuenta.", not_found: "Cuenta no encontrada.",
    },
    p: { kinds: { denied: "Sin acceso" } },
    um: {
      title: "Cuentas", sub: "Crea y gestiona cuentas de tu nivel o inferior, dentro de tu ámbito. Solo puedes dar módulos que tú tienes.",
      newBtn: "Nueva cuenta", newTitle: "Nueva cuenta", username: "Nombre de usuario",
      usernameHint: "De 3 a 32 caracteres: minúsculas, números, . _ -", password: "Contraseña inicial",
      generate: "Generar", generated: "Contraseña generada. Cópiala antes de crear la cuenta.", role: "Perfil",
      brand: "Marca", store: "Tienda", choose: "Elegir…", modules: "Módulos", create: "Crear cuenta", cancel: "Cancelar",
      created: u => `Cuenta ${u} creada.`, search: "Buscar", allRoles: "Todos los perfiles", allStatus: "Todos los estados",
      active: "Activa", inactive: "Desactivada", you: "tú", demo: "Demo",
      demoHint: "Cuenta pública de demostración: solo el admin puede modificarla.",
      createdBy: n => `creada por ${n}`, never: "nunca ha entrado", lastLogin: "Último acceso",
      edit: "Editar", save: "Guardar", saved: "Cambios guardados.", newPassword: "Nueva contraseña (opcional)",
      disable: "Desactivar", enable: "Activar", delete: "Borrar",
      disableTitle: "¿Desactivar la cuenta?", disableText: "La persona ya no podrá entrar y la sesión abierta termina ahora.",
      disabled: "Cuenta desactivada.", enabled: "Cuenta activada.",
      deleteTitle: "¿Borrar la cuenta?", deleteText: "Se borrarán la cuenta y sus conversaciones. No se puede deshacer.",
      deleted: "Cuenta borrada.", empty: "Ninguna cuenta coincide con la búsqueda.",
      count: n => `${n} cuenta${n === 1 ? "" : "s"}`, scopeAll: "Todo el grupo", readOnly: "Solo lectura", actions: "Acciones",
    },
    adm: {
      title: "Observabilidad", sub: "Cada pregunta queda registrada: tiempo, intención, SQL, tokens del LLM y valoración.",
      period: "Periodo", days: { 1: "24 h", 7: "7 días", 30: "30 días", 90: "90 días" }, refresh: "Actualizar",
      updated: "Actualizado a las", requests: "Peticiones", users: n => `${n} usuario${n === 1 ? "" : "s"}`,
      errorRate: "Tasa de error", errorsN: n => `${n} sin respuesta`, latency: "Latencia p50 / p95",
      tokens: "Tokens por petición", tokensTotal: n => `${n} en total`, satisfaction: "Satisfacción",
      ratings: (u, d) => `${u} positiva${u === 1 ? "" : "s"} · ${d} negativa${d === 1 ? "" : "s"}`, noRatings: "sin valoraciones", sqlFail: "SQL con error",
      recovered: n => `${n} corregido${n === 1 ? "" : "s"} en el 2.º intento`, classifier: "Decididas localmente",
      classifierHint: "intención sin llamar al LLM", cache: "Caché de SQL", cacheHint: (n) => `${n} respuestas sin volver a generar SQL`, daily: "Peticiones por día", ok: "Con respuesta", failed: "Error",
      intents: "Intenciones (clasificador local)", kinds: "Por tipo de respuesta", kind: "Tipo", n: "N.º",
      avg: "Media", avgTokens: "Tokens", top: "Preguntas más frecuentes", question: "Pregunta", times: "Veces",
      down: "Respuestas mal valoradas", noDown: "Ninguna respuesta mal valorada en este periodo.", errors: "Errores recientes",
      noErrors: "Sin errores en este periodo.", byUser: "Por usuario", user: "Usuario", last: "Último",
      eval: "Evaluación continua del text-to-SQL", evalSub: "Execution accuracy en las 40 preguntas de eval/questions.json, guardada en cada ejecución.",
      evalHow: "Nueva ejecución:", model: "Modelo", accuracy: "Accuracy", date: "Fecha", level: "Nivel", runs: "Ejecuciones",
      allLevels: "todos", imported: "importado", noEval: "Aún no hay ejecuciones guardadas.",
      empty: "Aún no hay peticiones en este periodo. Pregunta algo en el chat y vuelve.",
      intentNames: { data: "Datos (SQL)", forecast: "Previsión", orders: "Pedidos", chat: "Charla",
                     personal_data: "Datos personales", write: "Petición de escritura", off_topic: "Fuera de ámbito", llm: "Decide el LLM" },
      kindNames: { sql: "SQL", forecast: "Previsión", orders: "Pedidos", no_sql: "Charla", denied: "Sin módulo",
                   error: "Error", exception: "Fallo técnico" },
    },
  },
  fr: {
    correct: "enregistrer comme exemple",
    roles: { admin: "Administrateur" },
    pageTitles: { users: "Comptes · Multistore AI", admin: "Observabilité · Multistore AI" },
    nav: { chat: "Chat", users: "Comptes", admin: "Tableau de bord", profile: "Profil", main: "Navigation", close: "Fermer le menu", account: "Compte" },
    rate: { label: "Évaluer la réponse", up: "Bonne réponse", down: "Mauvaise réponse", thanks: "Merci ! Nous allons revoir cette réponse." },
    mods: { sql: "Questions sur les données", forecast: "Prévision des ventes", orders: "Suggestion de commandes",
            teach: "Entraîner l'assistant", users: "Gérer les comptes", observability: "Observabilité" },
    modsHint: { sql: "Ventes, stock, équipes, marges…", forecast: "Chiffre d'affaires prévu (7 jours)", orders: "Ingrédients à commander",
                teach: "Enregistrer les bonnes réponses comme exemples", users: "Créer des comptes du même niveau ou inférieur", observability: "Tableau de métriques" },
    errors: {
      no_module: "Ton compte n'a pas accès à cette zone.",
      role_above: "Tu ne peux pas créer de comptes au-dessus de ton profil.",
      out_of_scope: "Cette marque ou ce magasin est hors de ton périmètre.",
      need_brand: "Choisis la marque.", need_store: "Choisis le magasin.",
      bad_scope: "Ce profil n'a ni marque ni magasin.", bad_role: "Profil invalide.",
      module_not_yours: "Tu ne peux pas donner des modules que tu n'as pas.",
      module_not_for_role: "Ce profil ne peut pas avoir l'un des modules choisis.",
      no_modules: "Choisis au moins un module de données (questions, prévision ou commandes).",
      bad_module: "Module inconnu.",
      bad_username: "Nom d'utilisateur invalide : 3 à 32 caractères (minuscules, chiffres, . _ -).",
      weak_password: "Mot de passe faible : au moins 8 caractères, lettres et chiffres, sans le nom d'utilisateur.",
      username_taken: "Ce nom d'utilisateur existe déjà.",
      too_many_users: "Tu as atteint la limite de comptes créés.",
      cannot_manage: "Tu ne peux pas modifier ce compte.", not_found: "Compte introuvable.",
    },
    p: { kinds: { denied: "Sans accès" } },
    um: {
      title: "Comptes", sub: "Crée et gère des comptes de ton niveau ou inférieur, dans ton périmètre. Tu ne peux donner que les modules que tu as.",
      newBtn: "Nouveau compte", newTitle: "Nouveau compte", username: "Nom d'utilisateur",
      usernameHint: "3 à 32 caractères : minuscules, chiffres, . _ -", password: "Mot de passe initial",
      generate: "Générer", generated: "Mot de passe généré. Copie-le avant de créer le compte.", role: "Profil",
      brand: "Marque", store: "Magasin", choose: "Choisir…", modules: "Modules", create: "Créer le compte", cancel: "Annuler",
      created: u => `Compte ${u} créé.`, search: "Rechercher", allRoles: "Tous les profils", allStatus: "Tous les états",
      active: "Actif", inactive: "Désactivé", you: "toi", demo: "Démo",
      demoHint: "Compte public de démonstration : seul l'admin peut le modifier.",
      createdBy: n => `créé par ${n}`, never: "jamais connecté", lastLogin: "Dernière connexion",
      edit: "Modifier", save: "Enregistrer", saved: "Modifications enregistrées.", newPassword: "Nouveau mot de passe (optionnel)",
      disable: "Désactiver", enable: "Activer", delete: "Supprimer",
      disableTitle: "Désactiver le compte ?", disableText: "La personne ne pourra plus se connecter et la session ouverte se termine maintenant.",
      disabled: "Compte désactivé.", enabled: "Compte activé.",
      deleteTitle: "Supprimer le compte ?", deleteText: "Le compte et ses conversations seront supprimés. C'est irréversible.",
      deleted: "Compte supprimé.", empty: "Aucun compte ne correspond à la recherche.",
      count: n => `${n} compte${n === 1 ? "" : "s"}`, scopeAll: "Tout le groupe", readOnly: "Lecture seule", actions: "Actions",
    },
    adm: {
      title: "Observabilité", sub: "Chaque question est enregistrée : temps, intention, SQL, tokens du LLM et évaluation.",
      period: "Période", days: { 1: "24 h", 7: "7 jours", 30: "30 jours", 90: "90 jours" }, refresh: "Actualiser",
      updated: "Mis à jour à", requests: "Requêtes", users: n => `${n} utilisateur${n === 1 ? "" : "s"}`,
      errorRate: "Taux d'erreur", errorsN: n => `${n} sans réponse`, latency: "Latence p50 / p95",
      tokens: "Tokens par requête", tokensTotal: n => `${n} au total`, satisfaction: "Satisfaction",
      ratings: (u, d) => `${u} positive${u === 1 ? "" : "s"} · ${d} négative${d === 1 ? "" : "s"}`, noRatings: "aucune évaluation", sqlFail: "SQL en erreur",
      recovered: n => `${n} corrigé${n === 1 ? "" : "s"} au 2e essai`, classifier: "Décidées localement",
      classifierHint: "intention sans appeler le LLM", cache: "Cache SQL", cacheHint: (n) => `${n} réponses sans régénérer le SQL`, daily: "Requêtes par jour", ok: "Avec réponse", failed: "Erreur",
      intents: "Intentions (classifieur local)", kinds: "Par type de réponse", kind: "Type", n: "Nb",
      avg: "Moyenne", avgTokens: "Tokens", top: "Questions les plus posées", question: "Question", times: "Fois",
      down: "Réponses mal notées", noDown: "Aucune réponse mal notée sur cette période.", errors: "Erreurs récentes",
      noErrors: "Aucune erreur sur cette période.", byUser: "Par utilisateur", user: "Utilisateur", last: "Dernière",
      eval: "Évaluation continue du text-to-SQL", evalSub: "Execution accuracy sur les 40 questions de eval/questions.json, enregistrée à chaque exécution.",
      evalHow: "Nouvelle exécution :", model: "Modèle", accuracy: "Accuracy", date: "Date", level: "Niveau", runs: "Exécutions",
      allLevels: "tous", imported: "importé", noEval: "Aucune exécution enregistrée pour l'instant.",
      empty: "Aucune requête sur cette période. Pose une question dans le chat et reviens.",
      intentNames: { data: "Données (SQL)", forecast: "Prévision", orders: "Commandes", chat: "Discussion",
                     personal_data: "Données personnelles", write: "Demande d'écriture", off_topic: "Hors sujet", llm: "Le LLM décide" },
      kindNames: { sql: "SQL", forecast: "Prévision", orders: "Commandes", no_sql: "Discussion", denied: "Sans module",
                   error: "Erreur", exception: "Panne technique" },
    },
  },
};

/** Junta ADMIN_TEXTS aos textos principais (objetos aninhados são fundidos, não substituídos). */
function installAdminTexts(TEXTS) {
  const merge = (target, src) => {
    for (const [k, v] of Object.entries(src)) {
      if (v && typeof v === "object" && !Array.isArray(v) && typeof target[k] === "object") merge(target[k], v);
      else target[k] = v;
    }
  };
  for (const code of Object.keys(ADMIN_TEXTS)) if (TEXTS[code]) merge(TEXTS[code], ADMIN_TEXTS[code]);
}

/** Password aleatória forte (com minúscula, maiúscula, número e símbolo). */
function randomPassword(length = 14) {
  const sets = ["abcdefghijkmnpqrstuvwxyz", "ABCDEFGHJKLMNPQRSTUVWXYZ", "23456789", "!#%+-=?@"];
  const all = sets.join("");
  const pick = s => s[crypto.getRandomValues(new Uint32Array(1))[0] % s.length];
  const chars = sets.map(pick);
  while (chars.length < length) chars.push(pick(all));
  for (let i = chars.length - 1; i > 0; i--) {             // baralha (Fisher–Yates)
    const j = crypto.getRandomValues(new Uint32Array(1))[0] % (i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}

const emptyForm = () => ({ username: "", password: "", show: false, role: "", brand_id: "", store_id: "",
                           modules: [], error: "", saving: false });

const AdminMixin = {
  data() {
    return {
      um: { list: [], options: null, loading: false, form: null, editId: null, edit: null,
            query: "", role: "", status: "" },
      adm: { data: null, days: 7, loading: false, error: "", updated: null },
    };
  },
  computed: {
    moduleOrder() { return MODULE_ORDER; },
    dashDays() { return DASH_DAYS; },
    filteredUsers() {
      const q = this.um.query.trim().toLowerCase();
      return this.um.list.filter(u =>
        (!q || [u.username, u.brand_name, u.store_name].some(v => (v || "").toLowerCase().includes(q)))
        && (!this.um.role || u.role === this.um.role)
        && (!this.um.status || (this.um.status === "active") === u.active));
    },
    formModules() {
      const f = this.um.form, o = this.um.options;
      return f && o && f.role ? o.modules[f.role] || [] : [];
    },
    formStores() {
      const o = this.um.options;
      if (!o) return [];
      const brands = Object.fromEntries((o.brands || []).map(b => [b.id, b.name]));
      const groups = {};
      for (const s of o.stores) (groups[brands[s.brand_id] || "—"] ||= []).push(s);
      return Object.entries(groups).map(([brand, stores]) => ({ brand, stores }));
    },
    admKpis() {
      const d = this.adm.data, a = this.t.adm;
      if (!d) return [];
      const s = d.summary, fmt = n => this.format(n, 0);
      const total = s.prompt_tokens + s.completion_tokens;
      return [
        { key: "req", icon: "chat", label: a.requests, value: fmt(s.requests), hint: a.users(s.users) },
        { key: "err", icon: "alert", label: a.errorRate, value: this.pct(s.error_rate), hint: a.errorsN(s.errors),
          tone: s.error_rate > 0.1 ? "bad" : s.error_rate > 0.03 ? "warn" : "good" },
        { key: "lat", icon: "clock", label: a.latency,
          value: s.p50_ms == null ? "—" : `${this.ms(s.p50_ms)} / ${this.ms(s.p95_ms)}`, hint: "" },
        { key: "tok", icon: "hash", label: a.tokens, value: fmt(s.avg_tokens), hint: a.tokensTotal(fmt(total)) },
        { key: "sat", icon: "up", label: a.satisfaction, value: s.satisfaction == null ? "—" : this.pct(s.satisfaction),
          hint: s.thumbs_up + s.thumbs_down ? a.ratings(s.thumbs_up, s.thumbs_down) : a.noRatings,
          tone: s.satisfaction == null ? "" : s.satisfaction < 0.7 ? "warn" : "good" },
        { key: "sql", icon: "database", label: a.sqlFail, value: this.pct(s.sql_fail_rate), hint: a.recovered(s.sql_recovered) },
      ];
    },
    intentRows() {
      const d = this.adm.data;
      if (!d) return [];
      const max = Math.max(1, ...d.by_intent.map(r => r.n));
      return d.by_intent.map(r => ({ ...r, label: this.t.adm.intentNames[r.intent] || r.intent,
                                     pct: Math.round(100 * r.n / max) }));
    },
  },
  methods: {
    hasModule(m) { return (this.user?.modules || []).includes(m); },
    async refreshMe() {
      try {
        const me = await this.api("/me");
        this.user = me; store.set("user", JSON.stringify(me));
        this.applyUserSettings?.(me.settings);
      } catch {}
    },
    apiError(e) {                     // erros com código → texto traduzido
      return (e.code && this.t.errors[e.code]) || e.message;
    },

    // ----- Avaliação 👍 / 👎 das respostas -----
    async rate(m, value) {
      const next = m.rating === value ? 0 : value;
      const before = m.rating;
      m.rating = next || null;
      try {
        await this.api("/ratings", { request_id: m.requestId, rating: next });
        if (next === -1) this.toast(this.t.rate.thanks, "ok");
      } catch (e) { m.rating = before; this.toast(this.apiError(e)); }
    },

    // ----- Contas -----
    async loadUsers() {
      this.um.loading = true;
      try {
        const [list, options] = await Promise.all([this.api("/users"), this.um.options ? null : this.api("/users/options")]);
        this.um.list = list;
        if (options) this.um.options = options;
      } catch (e) { this.toast(this.apiError(e)); }
      finally { this.um.loading = false; }
    },
    openNewUser() {
      const roles = this.um.options?.roles || [];
      this.um.form = emptyForm();
      this.pickRole(roles[roles.length - 1] || "");
      this.$nextTick(() => document.getElementById("nu-username")?.focus());
    },
    pickRole(role) {
      const f = this.um.form;
      f.role = role; f.brand_id = ""; f.store_id = "";
      f.modules = [...(this.um.options?.defaults?.[role] || [])];
      const o = this.um.options;
      if (role === "marca" && o.brands.length === 1) f.brand_id = o.brands[0].id;
      if (role === "loja" && o.stores.length === 1) f.store_id = o.stores[0].id;
    },
    toggleIn(list, m) { const i = list.indexOf(m); if (i >= 0) list.splice(i, 1); else list.push(m); },
    genPassword() {
      const f = this.um.form;
      f.password = randomPassword(); f.show = true;
      this.toast(this.t.um.generated, "ok");
    },
    async submitNewUser() {
      const f = this.um.form;
      f.error = "";
      if (!DATA_MODULES.some(m => f.modules.includes(m))) { f.error = this.t.errors.no_modules; return; }
      f.saving = true;
      try {
        const body = { username: f.username.trim().toLowerCase(), password: f.password, role: f.role,
                       brand_id: f.role === "marca" ? Number(f.brand_id) || null : null,
                       store_id: f.role === "loja" ? Number(f.store_id) || null : null,
                       modules: MODULE_ORDER.filter(m => f.modules.includes(m)) };
        const created = await this.api("/users", body);
        this.toast(this.t.um.created(created.username), "ok");
        this.um.form = null;
        await this.loadUsers();
      } catch (e) { f.error = this.apiError(e); }
      finally { if (this.um.form) f.saving = false; }
    },
    startEdit(u) {
      if (this.um.editId === u.id) { this.um.editId = null; return; }
      this.um.editId = u.id;
      this.um.edit = { modules: [...u.modules], password: "", show: false, saving: false, error: "" };
    },
    editableModules(u) { return this.um.options?.modules?.[u.role] || []; },
    async saveEdit(u) {
      const e = this.um.edit;
      e.error = "";
      const body = {};
      const mods = MODULE_ORDER.filter(m => e.modules.includes(m));
      if (mods.join() !== u.modules.join()) body.modules = mods;
      if (e.password) body.password = e.password;
      if (!Object.keys(body).length) { this.um.editId = null; return; }
      e.saving = true;
      try {
        await this.api(`/users/${u.id}`, body, "PATCH");
        this.toast(this.t.um.saved, "ok");
        this.um.editId = null;
        await this.loadUsers();
      } catch (err) { e.error = this.apiError(err); }
      finally { e.saving = false; }
    },
    async toggleActive(u) {
      if (u.active) {
        const ok = await this.confirmDialog({ title: this.t.um.disableTitle, subject: u.username,
                                              text: this.t.um.disableText, confirm: this.t.um.disable, danger: true });
        if (!ok) return;
      }
      try {
        await this.api(`/users/${u.id}`, { active: !u.active }, "PATCH");
        this.toast(u.active ? this.t.um.disabled : this.t.um.enabled, "ok");
        await this.loadUsers();
      } catch (e) { this.toast(this.apiError(e)); }
    },
    async removeUser(u) {
      const ok = await this.confirmDialog({ title: this.t.um.deleteTitle, subject: u.username,
                                            text: this.t.um.deleteText, confirm: this.t.um.delete, danger: true });
      if (!ok) return;
      try {
        await this.api(`/users/${u.id}`, null, "DELETE");
        this.toast(this.t.um.deleted, "ok");
        await this.loadUsers();
      } catch (e) { this.toast(this.apiError(e)); }
    },
    scopeOf(u) {
      if (u.role === "admin" || u.role === "imperador") return this.t.um.scopeAll;
      if (u.role === "marca") return u.brand_name || "—";
      return [u.store_name, u.brand_name].filter(Boolean).join(" · ");
    },
    userInitials(name) { return name.split(/[.\s_-]/).map(p => p[0]).join("").slice(0, 2).toUpperCase(); },

    // ----- Observabilidade -----
    async loadMetrics(days) {
      if (days) this.adm.days = days;
      this.adm.loading = true; this.adm.error = "";
      try {
        this.adm.data = await this.api(`/admin/metrics?days=${this.adm.days}`);
        this.adm.updated = this.now();
        this.$nextTick(this.drawAdminCharts);
      } catch (e) { this.adm.error = this.apiError(e); }
      finally { this.adm.loading = false; }
    },
    destroyAdminCharts() { for (const k of Object.keys(adminCharts)) { adminCharts[k].destroy(); delete adminCharts[k]; } },
    drawAdminCharts() {
      const d = this.adm.data;
      if (!d || this.view !== "admin") return;
      this.destroyAdminCharts();
      const css = getComputedStyle(document.documentElement);
      const c = name => css.getPropertyValue(name).trim();
      const brand = c("--brand"), danger = c("--danger"), muted = c("--muted"), grid = c("--border");
      const base = {
        animation: { duration: reduceMotion ? 0 : 700 },
        plugins: { legend: { labels: { color: muted, boxWidth: 12 } } },
        scales: { x: { ticks: { color: muted }, grid: { display: false }, stacked: true },
                  y: { ticks: { color: muted, precision: 0 }, grid: { color: grid }, stacked: true, beginAtZero: true } },
      };
      const daily = document.getElementById("adm-daily");
      if (daily) {
        const label = day => new Date(day + "T12:00:00").toLocaleDateString(LOCALES[this.lang], { day: "numeric", month: "short" });
        adminCharts.daily = new Chart(daily, {
          type: "bar",
          data: { labels: d.daily.map(r => label(r.day)),
                  datasets: [
                    { label: this.t.adm.ok, data: d.daily.map(r => r.requests - r.errors), backgroundColor: brand + "cc", borderRadius: 6 },
                    { label: this.t.adm.failed, data: d.daily.map(r => r.errors), backgroundColor: danger + "cc", borderRadius: 6 },
                  ] },
          options: base,
        });
      }
      const evalEl = document.getElementById("adm-eval");
      if (evalEl && d.eval_history.length) {
        const palette = [brand, "#0ea5e9", "#f59e0b", "#8b5cf6", "#ec4899"];
        const models = [...new Set(d.eval_history.map(r => r.model))];
        adminCharts.eval = new Chart(evalEl, {
          type: "bar",
          data: {
            labels: d.eval_history.map(r => [this.shortDate(r.date), this.shortModel(r.model)]),
            datasets: [{ label: this.t.adm.accuracy,
                         data: d.eval_history.map(r => Math.round(1000 * (r.accuracy ?? 0)) / 10),
                         backgroundColor: d.eval_history.map(r => palette[models.indexOf(r.model) % palette.length] + "cc"),
                         borderRadius: 6 }],
          },
          options: { ...base, plugins: { legend: { display: false },
                                         tooltip: { callbacks: { label: ctx => `${ctx.parsed.y} %` } } },
                     scales: { x: { ticks: { color: muted, font: { size: 11 } }, grid: { display: false } },
                               y: { min: 0, max: 100, ticks: { color: muted, callback: v => v + " %" }, grid: { color: grid } } } },
        });
      }
    },
    pct(x) { return x == null ? "—" : (100 * x).toLocaleString(LOCALES[this.lang], { maximumFractionDigits: 1 }) + " %"; },
    ms(x) {
      if (x == null) return "—";
      return x >= 1000 ? (x / 1000).toLocaleString(LOCALES[this.lang], { maximumFractionDigits: 1 }) + " s" : x + " ms";
    },
    shortDate(iso) {
      return new Date(iso).toLocaleString(LOCALES[this.lang], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    },
    shortModel(m) { return (m || "").replace(/^openai\//, "").replace("Qwen2.5-Coder-", "Qwen "); },
    dailyLabel() {
      const d = this.adm.data;
      if (!d) return "";
      return `${this.t.adm.daily}: ` + d.daily.map(r => `${r.day} ${r.requests}`).join(", ");
    },
    evalLabel() {
      const d = this.adm.data;
      if (!d) return "";
      return `${this.t.adm.eval}: ` + d.eval_history.map(r => `${r.model} ${this.pct(r.accuracy)}`).join(", ");
    },
  },
};
