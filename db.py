"""
CENTINELA DO-CDM — Capa de Persistencia SQLite
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea tablas si no existen."""
    conn = get_conn()
    c = conn.cursor()

    # Posts de redes sociales
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id    TEXT,
            actor        TEXT NOT NULL,
            categoria    TEXT,           -- CLUB_OFICIAL / MEDIOS / PERIODISTAS / RIVALES
            subject      TEXT,           -- MARATHON / OTERO / RIVAL / GENERAL
            platform     TEXT NOT NULL,
            text         TEXT,
            url          TEXT,
            likes        INTEGER DEFAULT 0,
            comments     INTEGER DEFAULT 0,
            shares       INTEGER DEFAULT 0,
            views        INTEGER DEFAULT 0,
            published_at TEXT,
            collected_at TEXT NOT NULL,
            is_alert     INTEGER DEFAULT 0,
            UNIQUE(source_id, platform)
        )
    """)

    # Noticias RSS
    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            media        TEXT NOT NULL,
            title        TEXT,
            summary      TEXT,
            url          TEXT UNIQUE,
            subject      TEXT,           -- MARATHON / OTERO / GENERAL
            published_at TEXT,
            collected_at TEXT NOT NULL
        )
    """)

    # Alertas de crisis
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type   TEXT,
            actor        TEXT,
            platform     TEXT,
            keyword      TEXT,
            text         TEXT,
            url          TEXT,
            triggered_at TEXT NOT NULL,
            notified     INTEGER DEFAULT 0
        )
    """)

    # Historial de sentimiento diario
    c.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_history (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             TEXT NOT NULL UNIQUE,  -- YYYY-MM-DD
            marathon_score   REAL DEFAULT 0,  -- -1.0 (muy negativo) a 1.0 (muy positivo)
            otero_score      REAL DEFAULT 0,
            fan_score        REAL DEFAULT 0,
            post_count       INTEGER DEFAULT 0,
            crisis_count     INTEGER DEFAULT 0,
            fan_post_count   INTEGER DEFAULT 0,
            marathon_label   TEXT,  -- POSITIVO / NEUTRAL / NEGATIVO / MIXTO
            otero_label      TEXT,
            fan_label        TEXT,
            saved_at         TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ── Guardar datos ─────────────────────────────────────────────────────────────

def save_post(actor, categoria, subject, platform, text, url,
              likes=0, comments=0, shares=0, views=0,
              published_at=None, source_id=None):
    now = datetime.now(timezone.utc).isoformat()
    if not source_id:
        source_id = url or f"{actor}_{platform}_{now}"
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO posts
              (source_id, actor, categoria, subject, platform, text, url,
               likes, comments, shares, views, published_at, collected_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (source_id, actor, categoria, subject, platform, text, url,
              likes, comments, shares, views, published_at, now))
        conn.commit()
        return True
    except Exception as e:
        print(f"  [db] Error guardando post: {e}")
        return False
    finally:
        conn.close()


def save_news(media, title, summary, url, subject="GENERAL", published_at=None):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO news
              (media, title, summary, url, subject, published_at, collected_at)
            VALUES (?,?,?,?,?,?,?)
        """, (media, title, summary, url, subject, published_at, now))
        conn.commit()
        return True
    except Exception as e:
        print(f"  [db] Error guardando noticia: {e}")
        return False
    finally:
        conn.close()


def save_alert(alert_type, actor, platform, keyword, text, url):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute("""
        INSERT INTO alerts
          (alert_type, actor, platform, keyword, text, url, triggered_at, notified)
        VALUES (?,?,?,?,?,?,?,0)
    """, (alert_type, actor, platform, keyword, text, url, now))
    conn.commit()
    conn.close()


def mark_alerts_notified():
    conn = get_conn()
    conn.execute("UPDATE alerts SET notified=1 WHERE notified=0")
    conn.commit()
    conn.close()


# ── Consultas ─────────────────────────────────────────────────────────────────

def get_today_posts():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM posts
        WHERE collected_at >= ?
        ORDER BY likes DESC, collected_at DESC
    """, (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_news():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM news
        WHERE collected_at >= ?
        ORDER BY collected_at DESC
    """, (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_sentiment_snapshot(date, marathon_score, otero_score, fan_score,
                             post_count, crisis_count, fan_post_count,
                             marathon_label, otero_label, fan_label):
    """Guarda el snapshot de sentimiento del día. Reemplaza si ya existe."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute("""
        INSERT INTO sentiment_history
          (date, marathon_score, otero_score, fan_score,
           post_count, crisis_count, fan_post_count,
           marathon_label, otero_label, fan_label, saved_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(date) DO UPDATE SET
          marathon_score=excluded.marathon_score,
          otero_score=excluded.otero_score,
          fan_score=excluded.fan_score,
          post_count=excluded.post_count,
          crisis_count=excluded.crisis_count,
          fan_post_count=excluded.fan_post_count,
          marathon_label=excluded.marathon_label,
          otero_label=excluded.otero_label,
          fan_label=excluded.fan_label,
          saved_at=excluded.saved_at
    """, (date, marathon_score, otero_score, fan_score,
          post_count, crisis_count, fan_post_count,
          marathon_label, otero_label, fan_label, now))
    conn.commit()
    conn.close()


def get_sentiment_trend(days=7):
    """Retorna los últimos N días de historial de sentimiento, del más antiguo al más reciente."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM sentiment_history
        ORDER BY date DESC
        LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))


def get_pending_alerts():
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM alerts WHERE notified=0
        ORDER BY triggered_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
