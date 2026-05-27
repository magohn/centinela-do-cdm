"""
CENTINELA DO-CDM — Configuración Central
Monitoreo Digital: CD Marathón & Daniel Otero
Desarrollado por Stratégica
"""

import os

# ── Cuenta oficial CD Marathón ───────────────────────────────────────────────

MARATHON_ACCOUNT = {
    "CD Marathón": {
        "twitter":   "CDMarathon",
        "instagram": "cdmarathon",
        "tiktok":    "cdmarathon",
        "categoria": "CLUB_OFICIAL",
    }
}

# ── Daniel Otero — palabras clave (sin handle X confirmado) ──────────────────

DANIEL_OTERO_KEYWORDS = [
    "Daniel Otero", "Otero Marathón", "Otero Marathon",
    "presidente Marathon", "presidente Marathón", "DanielOtero",
]

# ── Medios deportivos hondureños ─────────────────────────────────────────────

MEDIOS_DEPORTIVOS = {
    "Diario Diez": {
        "twitter": "DiarioDiezHn",
        "rss":     "https://www.diez.hn/feed/",
    },
    "Deportes TVC": {
        "twitter": "DeportesTVC",
        "rss":     None,
    },
    "Tigo Sports HN": {
        "twitter": "TigoSportsHN",
        "rss":     None,
    },
    "HRN Deportes": {
        "twitter": "radiohrn",
        "rss":     "https://www.radiohrn.hn/feed/",
    },
    "Liga Nacional HN": {
        "twitter": "lnfphonduras",
        "rss":     None,
    },
    "Federación Fútbol Honduras": {
        "twitter": "FFH_Honduras",
        "rss":     None,
    },
    "HCH Deportes": {
        "twitter": "hchdeportes",
        "rss":     None,
    },
    "Panorama Deportivo": {
        "twitter": "Pdeportivohn",
        "rss":     None,
    },
}

# ── Periodistas deportivos hondureños ────────────────────────────────────────

PERIODISTAS = {
    "Rely Maradiaga":      {"twitter": "RelyYosimar"},
    "Yanuario Paz":        {"twitter": "yanuariopaz"},
    "Juan C. Pineda":      {"twitter": "jcpineda17"},
    "Allan Fajardo":       {"twitter": "allanfajardo29"},
    "Mauricio Kawas":      {"twitter": "makawas"},
    "Copán Álvarez":       {"twitter": "CopanAlvarez"},
    "Orlando Ponce":       {"twitter": "sorlandoponce"},
    "Fredy Nuila":         {"twitter": "fredyro19"},
    "Gustavo Roca":        {"twitter": "GustavoRocaGOL"},
    "Jorge Rivera":        {"twitter": "JorgeRdeportes"},
    "Carlos Prono":        {"twitter": "CARLOSPRONO1"},
    "Oscar Funez":         {"twitter": "chacofunesjr"},
    "Mauricio Portillo":   {"twitter": "MauPortillohn"},
    "Astor Henriquez":     {"twitter": "astorhenriquez"},
    "Gerardo Bustillo":    {"twitter": "GBustillohn"},
    "Jose Jorge Villeda":  {"twitter": "jj_villeda"},
    "Jimmy Rodriguez":     {"twitter": "JimmyArturo"},
    "Nahum Aguilar":       {"twitter": "NahumDIEZ"},
    "Felipe Valencia":     {"twitter": "luiselpipe"},
    "Manfredo Reyes":      {"twitter": "manfredooficial"},
    "Bebeto Flores":       {"twitter": "oscarbebeto"},
    "Luis Guifarro":       {"twitter": "luisguifarro24"},
    "El Baleadero":        {"twitter": "baleadero0501"},
    "Georgina Hernandez":  {"twitter": "AgeorginaH"},
    "Erika Williams":      {"twitter": "Erikawilliamshn"},
    "Jenny Fernandez":     {"twitter": "JFernandezHN15"},
}

# ── Ruido Orgánico — Fans en X ───────────────────────────────────────────────

FANS_X = {
    "Furia Verde 1986":  {"twitter": "FuriaVerde1986"},
    "Verdolaga HN":      {"twitter": "VerdolagaHN"},
    "Marathón Fans":     {"twitter": "MarathonFans"},
}

# ── Ruido Orgánico — Fan Pages Facebook ──────────────────────────────────────
# Requiere FACEBOOK_ACCESS_TOKEN en el .env para activarse

FANPAGES_FB = {
    "CD Marathón Oficial":       {"page_id": "cdmarathon"},
    "Furia Verde Oficial":       {"page_id": "FuriaVerde1986oficial"},
    "Marathón Pasión Verdolaga": {"page_id": "MarathonPasionVerdolaga"},
}

# ── Clubes rivales (para contexto/comparación) ───────────────────────────────

RIVALES = {
    "CD Olimpia":   {"twitter": "CDOlimpia"},
    "Motagua":      {"twitter": "MOTAGUAcom"},
    "Real España":  {"twitter": "rcdespana"},
}

# ── Instancias Nitter (fallback automático) ──────────────────────────────────

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.it",
    "https://nitter.nl",
    "https://nitter.1d4.us",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

# ── Keywords para filtrar contenido relevante de medios ──────────────────────

MARATHON_KEYWORDS = [
    "Marathon", "Marathón", "CDMarathon", "Monstruo Verde",
    "Verdolaga", "Daniel Otero", "Otero", "Furia Verde",
    "San Pedro Sula", "SPS",
    "Estadio Morazán", "Estadio Morazan", "Morazán",
    "Estadio Olímpico", "Estadio Olimpico",
    "Estadio Yankel", "Yankel Rosenthal",
    "Pablo Lavallen", "Lavallen",
]

# ── Keywords de crisis (alerta inmediata) ────────────────────────────────────

CRISIS_KEYWORDS = [
    "renuncia", "destituido", "fraude", "escándalo", "acusado",
    "investigado", "detenido", "corrupción", "crisis", "pleito",
    "sanción", "suspendido", "expulsado",
]

# ── Rutas y configuración general ───────────────────────────────────────────
# Soporta dos entornos: local (macOS) y GitHub Actions (nube)

_GHA       = os.environ.get("GITHUB_ACTIONS") == "true"
_WORKSPACE = os.environ.get("GITHUB_WORKSPACE", "")

if _GHA:
    # GitHub Actions: todos los archivos viven en el workspace del runner
    BASE_DIR    = _WORKSPACE
    REPORTS_DIR = os.path.join(_WORKSPACE, "reportes_cdm")
    DB_PATH     = os.path.join(_WORKSPACE, "cdm.db")
    ENV_PATH    = os.path.join(_WORKSPACE, ".env")
    LOG_PATH    = os.path.join(_WORKSPACE, "cdm.log")
else:
    # Local (macOS)
    BASE_DIR    = os.path.expanduser("~/social_monitor/cdm_agent")
    REPORTS_DIR = os.path.expanduser("~/social_monitor/reportes_cdm")
    DB_PATH     = os.path.join(BASE_DIR, "cdm.db")
    ENV_PATH    = os.path.expanduser("~/social_monitor/.env")
    LOG_PATH    = os.path.join(BASE_DIR, "cdm.log")

REPORT_RECIPIENTS = [
    "max.gonzaleshn@gmail.com",
    "cristian.cousin@gmail.com",
    "correootero@yahoo.com",
]
SENDER_NAME = "🦖 CENTINELA DO-CDM"

# ── Modo de temporada ────────────────────────────────────────────────────────
# True  → Liga Activa   (informe completo con partidos, resultados, rivales)
# False → Liga en Pausa (informe ligero sin datos de competencia)
LIGA_ACTIVA = True

# Horario de recolección (mismas horas que CENTINELA político)
COLLECT_HOURS = [4, 6, 8, 10, 12, 14, 16, 18, 20]

# Hora de entrega del informe
DELIVER_HOUR   = 5
DELIVER_MINUTE = 0

# Máximo de tweets por perfil por ciclo
MAX_TWEETS_PER_PROFILE = 10

# Máximo de items RSS por feed
MAX_RSS_ITEMS = 10
