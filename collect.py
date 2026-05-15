#!/usr/bin/env python3
"""
CENTINELA DO-CDM — Módulo de Recolección
Corre cada 2 horas vía launchd.
Recopila posts de X/Twitter (Nitter RSS) y noticias RSS
de CD Marathón, Daniel Otero, medios y periodistas deportivos.
"""
import os
import sys
import time
import hashlib
import feedparser
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/social_monitor/.env"), override=True)

import db
from config import (
    MARATHON_ACCOUNT, PERIODISTAS, MEDIOS_DEPORTIVOS, RIVALES,
    FANS_X, FANPAGES_FB,
    DANIEL_OTERO_KEYWORDS, MARATHON_KEYWORDS, CRISIS_KEYWORDS,
    NITTER_INSTANCES, MAX_TWEETS_PER_PROFILE, MAX_RSS_ITEMS,
)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Nitter RSS ────────────────────────────────────────────────────────────────

def get_nitter_feed(username: str, retries: int = 3) -> list:
    """Obtiene tweets de un usuario vía Nitter RSS con fallback automático."""
    for instance in NITTER_INSTANCES:
        url = f"{instance}/{username}/rss"
        for attempt in range(retries):
            try:
                resp = requests.get(url, timeout=12,
                                    headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    if feed.entries:
                        return feed.entries[:MAX_TWEETS_PER_PROFILE]
            except Exception:
                pass
            time.sleep(1)
    return []


def make_source_id(url: str, text: str) -> str:
    raw = (url or text or "")[:200]
    return hashlib.md5(raw.encode()).hexdigest()


def extract_metrics(entry) -> dict:
    stats = {"likes": 0, "comments": 0, "views": 0}
    summary = getattr(entry, "summary", "") or ""
    import re
    for tag, key in [("♥", "likes"), ("💬", "comments"), ("👁", "views")]:
        m = re.search(rf"{re.escape(tag)}\s*(\d+)", summary)
        if m:
            stats[key] = int(m.group(1))
    return stats


def classify_subject(text: str) -> str:
    """Clasifica si el post habla de Marathón, Daniel Otero, o es general."""
    text_lower = text.lower()
    otero_keys = ["daniel otero", "otero marathon", "otero marathón",
                  "presidente marathon", "presidente marathón"]
    if any(k in text_lower for k in otero_keys):
        return "OTERO"
    marathon_keys = ["marathon", "marathón", "cdmarathon",
                     "monstruo verde", "verdolaga", "furia verde"]
    if any(k in text_lower for k in marathon_keys):
        return "MARATHON"
    return "GENERAL"


def is_marathon_related(text: str) -> bool:
    """Filtra si un post de medios/periodistas es relevante para CDM."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in MARATHON_KEYWORDS)


def check_crisis(text: str):
    text_lower = text.lower()
    for kw in CRISIS_KEYWORDS:
        if kw.lower() in text_lower:
            return kw
    return None


# ── Recolectores ─────────────────────────────────────────────────────────────

def collect_marathon_x():
    """Posts oficiales de CD Marathón en X."""
    log("  → X: CD Marathón (@CDMarathon)…")
    entries = get_nitter_feed("CDMarathon")
    saved = 0
    for e in entries:
        text  = e.get("title", "")
        url   = e.get("link", "")
        stats = extract_metrics(e)
        subj  = classify_subject(text)
        sid   = make_source_id(url, text)

        if db.save_post(
            actor="CD Marathón", categoria="CLUB_OFICIAL", subject=subj,
            platform="twitter", text=text, url=url,
            likes=stats["likes"], comments=stats["comments"], views=stats["views"],
            source_id=sid,
        ):
            saved += 1
            kw = check_crisis(text)
            if kw:
                db.save_alert("CRISIS", "CD Marathón", "twitter", kw, text, url)
                log(f"    ⚠️  ALERTA: '{kw}' detectada en post de Marathón")

    log(f"     {saved} nuevos posts de CD Marathón")
    return saved


def collect_medios():
    """Posts de medios deportivos — filtra solo los que mencionan a Marathón/Otero."""
    total = 0
    for media_name, info in MEDIOS_DEPORTIVOS.items():
        handle = info.get("twitter")
        if not handle:
            continue
        log(f"  → X: {media_name} (@{handle})…")
        entries = get_nitter_feed(handle)
        saved = 0
        for e in entries:
            text = e.get("title", "")
            url  = e.get("link", "")
            if not is_marathon_related(text):
                continue
            stats = extract_metrics(e)
            subj  = classify_subject(text)
            sid   = make_source_id(url, text)
            if db.save_post(
                actor=media_name, categoria="MEDIOS", subject=subj,
                platform="twitter", text=text, url=url,
                likes=stats["likes"], comments=stats["comments"], views=stats["views"],
                source_id=sid,
            ):
                saved += 1
        log(f"     {saved} posts relevantes de {media_name}")
        total += saved
        time.sleep(1.5)
    return total


def collect_periodistas():
    """Posts de periodistas deportivos — filtra por relevancia."""
    total = 0
    for name, info in PERIODISTAS.items():
        handle = info.get("twitter")
        if not handle:
            continue
        log(f"  → X: {name} (@{handle})…")
        entries = get_nitter_feed(handle)
        saved = 0
        for e in entries:
            text = e.get("title", "")
            url  = e.get("link", "")
            if not is_marathon_related(text):
                continue
            stats = extract_metrics(e)
            subj  = classify_subject(text)
            sid   = make_source_id(url, text)
            if db.save_post(
                actor=name, categoria="PERIODISTAS", subject=subj,
                platform="twitter", text=text, url=url,
                likes=stats["likes"], comments=stats["comments"], views=stats["views"],
                source_id=sid,
            ):
                saved += 1
        if saved:
            log(f"     {saved} posts relevantes de {name}")
        total += saved
        time.sleep(1.5)
    return total


def collect_rivales():
    """Posts de equipos rivales — para contexto comparativo."""
    total = 0
    for club, info in RIVALES.items():
        handle = info.get("twitter")
        if not handle:
            continue
        log(f"  → X: {club} (@{handle})…")
        entries = get_nitter_feed(handle)
        saved = 0
        for e in entries[:5]:  # Solo los 5 más recientes de rivales
            text = e.get("title", "")
            url  = e.get("link", "")
            sid  = make_source_id(url, text)
            stats = extract_metrics(e)
            if db.save_post(
                actor=club, categoria="RIVALES", subject="RIVAL",
                platform="twitter", text=text, url=url,
                likes=stats["likes"], comments=stats["comments"], views=stats["views"],
                source_id=sid,
            ):
                saved += 1
        total += saved
        time.sleep(1)
    return total


def collect_rss():
    """Noticias RSS de medios deportivos — filtra por Marathón/Otero."""
    total = 0
    for media_name, info in MEDIOS_DEPORTIVOS.items():
        rss_url = info.get("rss")
        if not rss_url:
            continue
        log(f"  → RSS: {media_name}…")
        try:
            resp = requests.get(rss_url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.content)
            saved = 0
            for entry in feed.entries[:MAX_RSS_ITEMS]:
                title   = entry.get("title", "")
                summary = entry.get("summary", "")[:300]
                url     = entry.get("link", "")
                pub     = entry.get("published", "")

                # Filtrar: solo noticias que mencionan Marathón/Otero
                combined = f"{title} {summary}"
                if not is_marathon_related(combined):
                    continue

                subj = classify_subject(combined)
                if db.save_news(media_name, title, summary, url,
                                subject=subj, published_at=pub):
                    saved += 1
            if saved:
                log(f"     {saved} noticias relevantes de {media_name}")
            total += saved
        except Exception as ex:
            log(f"     ⚠️  RSS error {media_name}: {ex}")
        time.sleep(1)
    return total


# ── Ruido Orgánico — X ───────────────────────────────────────────────────────

def collect_fans_x():
    """Posts de cuentas de fans de Marathón en X — conversación orgánica."""
    total = 0
    for name, info in FANS_X.items():
        handle = info.get("twitter")
        if not handle:
            continue
        log(f"  → X Fans: {name} (@{handle})…")
        entries = get_nitter_feed(handle)
        saved = 0
        for e in entries:
            text  = e.get("title", "")
            url   = e.get("link", "")
            stats = extract_metrics(e)
            subj  = classify_subject(text)
            sid   = make_source_id(url, text)
            if db.save_post(
                actor=name, categoria="FANS_X", subject=subj,
                platform="twitter", text=text, url=url,
                likes=stats["likes"], comments=stats["comments"], views=stats["views"],
                source_id=sid,
            ):
                saved += 1
                kw = check_crisis(text)
                if kw:
                    db.save_alert("CRISIS_FANS", name, "twitter", kw, text, url)
                    log(f"    ⚠️  ALERTA en fans: '{kw}'")
        log(f"     {saved} posts de {name}")
        total += saved
        time.sleep(1.5)
    return total


# ── Ruido Orgánico — Facebook ─────────────────────────────────────────────────

def collect_fans_fb():
    """Posts de fan pages de Facebook — requiere FACEBOOK_ACCESS_TOKEN en .env."""
    fb_token = os.environ.get("FACEBOOK_ACCESS_TOKEN")
    if not fb_token:
        log("  → Facebook: sin token configurado — omitido")
        return 0

    total = 0
    from datetime import timedelta
    since = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())

    for page_name, info in FANPAGES_FB.items():
        page_id = info.get("page_id")
        log(f"  → FB: {page_name}…")
        try:
            url    = f"https://graph.facebook.com/v18.0/{page_id}/posts"
            params = {
                "access_token": fb_token,
                "fields": "message,created_time,likes.summary(true),comments.summary(true),shares",
                "since": since,
                "limit": 25,
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()

            if "data" not in data:
                log(f"     ⚠️  Sin datos de {page_name}: {data.get('error', {}).get('message', '')}")
                continue

            saved = 0
            for post in data["data"]:
                text     = post.get("message", "")
                post_url = f"https://www.facebook.com/{page_id}/posts/{post.get('id','').split('_')[-1]}"
                likes    = post.get("likes", {}).get("summary", {}).get("total_count", 0)
                comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
                shares   = post.get("shares", {}).get("count", 0) if "shares" in post else 0
                pub      = post.get("created_time", "")
                subj     = classify_subject(text)
                sid      = make_source_id(post_url, text)

                if db.save_post(
                    actor=page_name, categoria="FANS_FB", subject=subj,
                    platform="facebook", text=text, url=post_url,
                    likes=likes, comments=comments, shares=shares,
                    published_at=pub, source_id=sid,
                ):
                    saved += 1
                    kw = check_crisis(text)
                    if kw:
                        db.save_alert("CRISIS_FANS", page_name, "facebook", kw, text, post_url)

            log(f"     {saved} posts de {page_name}")
            total += saved
        except Exception as ex:
            log(f"     ⚠️  Error Facebook {page_name}: {ex}")
        time.sleep(1)
    return total


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("CENTINELA DO-CDM — Recolección iniciada")
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    db.init_db()

    p1 = collect_marathon_x()
    p2 = collect_medios()
    p3 = collect_periodistas()
    p4 = collect_rivales()
    p5 = collect_fans_x()
    p6 = collect_fans_fb()
    n1 = collect_rss()

    total_posts = p1 + p2 + p3 + p4 + p5 + p6
    log(f"✓ Ciclo completo: {total_posts} posts nuevos · {n1} noticias nuevas")
    log("=" * 60)


if __name__ == "__main__":
    main()
