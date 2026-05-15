#!/usr/bin/env python3
"""
CENTINELA DO-CDM — Módulo de Entrega
Corre diariamente a las 5:00 AM vía launchd.
Genera informe de reputación digital con Claude AI y lo envía por email.
"""
import os
import sys
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/social_monitor/.env"), override=True)

import anthropic
import db
from config import (
    MARATHON_ACCOUNT, MEDIOS_DEPORTIVOS, PERIODISTAS, RIVALES,
    REPORT_RECIPIENTS, REPORTS_DIR,
)

GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Construcción del resumen de datos ────────────────────────────────────────

def build_data_summary(posts: list, news: list) -> str:
    """
    Organiza los datos en un diccionario estructurado para Claude.
    Separa por: Marathón oficial / Medios sobre Marathón / Medios sobre Otero /
                Periodistas sobre Marathón / Periodistas sobre Otero / Rivales
    """
    summary = {
        "marathon_oficial":           [],
        "medios_sobre_marathon":      [],
        "medios_sobre_otero":         [],
        "periodistas_sobre_marathon": [],
        "periodistas_sobre_otero":    [],
        "rivales":                    [],
        "fans_x":                     [],
        "fans_fb":                    [],
        "noticias_marathon":          [],
        "noticias_otero":             [],
    }

    MAX = 8  # máx posts por sección

    for p in posts:
        item = {
            "actor":    p["actor"],
            "text":     (p["text"] or "")[:200],
            "url":      p.get("url", ""),
            "likes":    p.get("likes", 0),
            "comments": p.get("comments", 0),
        }
        cat  = p.get("categoria", "")
        subj = p.get("subject", "GENERAL")

        if cat == "CLUB_OFICIAL":
            if len(summary["marathon_oficial"]) < MAX:
                summary["marathon_oficial"].append(item)
        elif cat == "MEDIOS":
            if subj == "OTERO" and len(summary["medios_sobre_otero"]) < MAX:
                summary["medios_sobre_otero"].append(item)
            elif len(summary["medios_sobre_marathon"]) < MAX:
                summary["medios_sobre_marathon"].append(item)
        elif cat == "PERIODISTAS":
            if subj == "OTERO" and len(summary["periodistas_sobre_otero"]) < MAX:
                summary["periodistas_sobre_otero"].append(item)
            elif len(summary["periodistas_sobre_marathon"]) < MAX:
                summary["periodistas_sobre_marathon"].append(item)
        elif cat == "RIVALES":
            if len(summary["rivales"]) < MAX:
                summary["rivales"].append(item)
        elif cat in ("FANS_X", "FANS_FB"):
            key = "fans_x" if cat == "FANS_X" else "fans_fb"
            if len(summary[key]) < MAX:
                summary[key].append({**item, "plataforma": p.get("platform", "")})

    # Noticias RSS (si hay)
    for n in news:
        item = {
            "fuente":  n["media"],
            "titulo":  n["title"],
            "resumen": (n["summary"] or "")[:200],
            "url":     n.get("url", ""),
            "tipo":    "RSS",
        }
        if n.get("subject") == "OTERO" and len(summary["noticias_otero"]) < MAX:
            summary["noticias_otero"].append(item)
        elif len(summary["noticias_marathon"]) < MAX:
            summary["noticias_marathon"].append(item)

    # Noticias desde posts de medios en X (fuente principal)
    medios_posts = [p for p in posts if p.get("categoria") == "MEDIOS"]
    medios_posts.sort(key=lambda p: p.get("likes", 0) + p.get("comments", 0), reverse=True)
    for p in medios_posts[:MAX]:
        item = {
            "fuente":  p["actor"],
            "titulo":  (p["text"] or "")[:180],
            "resumen": "",
            "url":     p.get("url", ""),
            "tipo":    "X",
        }
        if p.get("subject") == "OTERO" and len(summary["noticias_otero"]) < MAX:
            summary["noticias_otero"].append(item)
        elif len(summary["noticias_marathon"]) < MAX:
            summary["noticias_marathon"].append(item)

    # ── Tendencia histórica ───────────────────────────────────────────────────
    trend = db.get_sentiment_trend(days=7)
    summary["tendencia_historica"] = trend  # últimos 7 días de snapshots

    return json.dumps(summary, ensure_ascii=False, indent=2)


# ── Prompts para Claude ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres CENTINELA DO-CDM, un sistema de inteligencia de reputación digital
desarrollado por Stratégica.

PRIORIDAD ABSOLUTA: El sujeto principal de este informe es DANIEL OTERO, presidente del CD Marathón.
CD Marathón es el segundo sujeto. Cuando analices, siempre pondera primero el impacto sobre
la reputación de Daniel Otero, y luego el impacto sobre el club.

CONTEXTO:
- Daniel Otero: Presidente del CD Marathón. Su reputación personal es la prioridad #1.
- CD Marathón: equipo de fútbol hondureño con sede en San Pedro Sula. Prioridad #2.
- Fuentes monitoreadas: medios deportivos, 26 periodistas hondureños, cuenta oficial del club,
  fans en X, fan pages de Facebook y equipos rivales.

INSTRUCCIONES DE FORMATO — MUY IMPORTANTE:
- Usa ÚNICAMENTE etiquetas HTML válidas. NUNCA uses markdown.
- La red social X (antes Twitter) se llama SIEMPRE "X", nunca "Twitter".
- Si no hay datos: <p><em>Sin actividad registrada.</em></p>
- Analiza ÚNICAMENTE los datos reales. No inventes información.

SISTEMA DE TARJETAS — OBLIGATORIO:
Cada elemento individual (cada alerta, cada oportunidad, cada noticia, cada fan post)
debe ir dentro de una tarjeta <div class="card ..."> para separarlo visualmente del siguiente.

Clases disponibles según el tipo:
- Alertas ALTO:      <div class="card card-crisis-alto">
- Alertas MEDIO:     <div class="card card-crisis-medio">
- Alertas BAJO:      <div class="card card-crisis-bajo">
- Oportunidades:     <div class="card card-oportunidad">
- Noticias:          <div class="card card-noticia">
- Fans / Orgánico:   <div class="card card-fan">
- General / neutral: <div class="card card-neutral">

Ejemplo de una alerta MEDIO:
<div class="card card-crisis-medio">
  <ul>
    <li><strong>Sujeto:</strong> Daniel Otero</li>
    <li><strong>Nivel:</strong> MEDIO</li>
    <li><strong>Descripción:</strong> ...</li>
    <li><strong>Fuente:</strong> @cuenta</li>
    <li><strong>Acción sugerida:</strong> ...</li>
  </ul>
</div>

Ejemplo de una noticia:
<div class="card card-noticia">
  <ul>
    <li><strong>Medio:</strong> Diario Diez</li>
    <li><strong>Noticia:</strong> ...</li>
    <li><strong>Ángulo:</strong> Neutral</li>
    <li><strong>Fuente:</strong> X</li>
  </ul>
</div>

NUNCA pongas dos elementos distintos dentro del mismo <div class="card">."""

DAILY_PROMPT = """Analiza los datos de redes sociales y medios deportivos hondureños
del día {date} y genera el INFORME DIARIO de CENTINELA DO-CDM.

PERÍODO: Últimas 24 horas ({period_start} → {period_end})

DATOS:
{data}

PRIORIDAD: Daniel Otero es el sujeto principal del informe. CD Marathón es el segundo sujeto.
Todas las secciones deben analizar primero a Daniel Otero y luego al club.

Genera el informe en HTML limpio con EXACTAMENTE estas 13 secciones en este orden:

<h2>📊 1. RESUMEN EJECUTIVO</h2>
<ul>
<li><strong>Estado de Daniel Otero hoy:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO — [razón en una oración]</li>
<li><strong>Estado de CD Marathón hoy:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO — [razón en una oración]</li>
<li><strong>Hecho más relevante del día:</strong> [descripción — priorizar si involucra a Otero]</li>
<li><strong>Nivel de atención requerida:</strong> ALTA / MEDIA / BAJA — [por qué]</li>
</ul>

<h2>👤 2. DANIEL OTERO — COBERTURA Y SENTIMIENTO</h2>
Prioridad máxima. Analiza TODO lo publicado sobre Daniel Otero: medios, periodistas, fans.
<ul>
<li><strong>Sentimiento general:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>% estimado:</strong> [X% Positivo / X% Neutral / X% Negativo]</li>
<li><strong>Publicación más relevante sobre él:</strong> [fuente y contenido exacto]</li>
<li><strong>Narrativa que se está construyendo sobre su figura:</strong> [descripción]</li>
<li><strong>Temas asociados a su nombre hoy:</strong> [lista]</li>
</ul>

<h2>🚨 3. ALERTAS DE CRISIS</h2>
Primero alertas sobre Daniel Otero, luego sobre CD Marathón.
Para cada alerta:
<ul>
<li><strong>Sujeto:</strong> Daniel Otero / CD Marathón</li>
<li><strong>Nivel:</strong> ALTO / MEDIO / BAJO</li>
<li><strong>Descripción:</strong> [qué se dice, quién lo dice, alcance estimado]</li>
<li><strong>Fuente:</strong> [cuenta o medio]</li>
<li><strong>Acción sugerida:</strong> [respuesta recomendada y tiempo]</li>
</ul>
Si no hay alertas: <p><em>Sin alertas de crisis en las últimas 24 horas.</em></p>

<h2>💡 4. OPORTUNIDADES DETECTADAS</h2>
Primero oportunidades para Daniel Otero, luego para CD Marathón.
<ul>
<li><strong>Sujeto:</strong> Daniel Otero / CD Marathón</li>
<li><strong>Oportunidad:</strong> [descripción concreta]</li>
<li><strong>Cómo aprovecharla:</strong> [acción específica]</li>
<li><strong>Urgencia:</strong> Inmediata / Esta semana / Este mes</li>
</ul>
Si no hay oportunidades: <p><em>Sin oportunidades destacadas hoy.</em></p>

<h2>🦖 5. ACTIVIDAD OFICIAL — CD MARATHÓN EN X</h2>
Posts de @CDMarathon en las últimas 24 horas.
<ul>
<li><strong>Total de publicaciones:</strong> [número]</li>
<li><strong>Temas comunicados:</strong> [lista]</li>
<li><strong>Post más relevante:</strong> [contenido y engagement]</li>
<li><strong>Tono general de la comunicación oficial:</strong> [descripción]</li>
</ul>

<h2>📺 6. MEDIOS DEPORTIVOS — SENTIMIENTO SOBRE MARATHÓN</h2>
Análisis de Diario Diez, TVC, Tigo Sports, HRN, HCH, Panorama, FFH, Liga Nacional.
<ul>
<li><strong>Sentimiento general:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>% estimado:</strong> [X% Positivo / X% Neutral / X% Negativo]</li>
<li><strong>Medio más activo:</strong> [nombre y enfoque]</li>
<li><strong>Nota más destacada:</strong> [medio y titular]</li>
<li><strong>Temas cubiertos:</strong> [lista]</li>
</ul>

<h2>🎙️ 7. PERIODISTAS — SENTIMIENTO SOBRE MARATHÓN</h2>
Análisis de los 26 periodistas deportivos monitoreados.
<ul>
<li><strong>Sentimiento general:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>Periodista más activo:</strong> [nombre y enfoque]</li>
<li><strong>Comentario más impactante:</strong> [autor y cita textual o resumen]</li>
<li><strong>Narrativa dominante entre periodistas:</strong> [descripción]</li>
</ul>

<h2>📈 8. MÉTRICAS DEL DÍA</h2>
<ul>
<li><strong>Total posts recolectados:</strong> [número]</li>
<li><strong>Post con mayor engagement:</strong> [actor, contenido y cifras]</li>
<li><strong>Medio más activo cubriendo a Marathón:</strong> [nombre]</li>
<li><strong>Periodista más activo:</strong> [nombre]</li>
<li><strong>Tema más mencionado:</strong> [tema]</li>
<li><strong>Red más activa:</strong> X</li>
</ul>

<h2>📰 9. NOTICIAS DESTACADAS</h2>
Publicaciones de medios deportivos (Diario Diez, TVC, Tigo Sports, HRN, HCH, Panorama, FFH, Liga Nacional)
extraídas de X y RSS. Selecciona las más relevantes sobre Otero o Marathón.
Para cada una usa este formato:
<ul>
<li><strong>Medio:</strong> [nombre del medio]</li>
<li><strong>Noticia:</strong> [titular o resumen del contenido]</li>
<li><strong>Ángulo:</strong> Favorable / Neutral / Crítico</li>
<li><strong>Fuente:</strong> X / RSS</li>
</ul>
Si no hay noticias relevantes: <p><em>Sin publicaciones de medios registradas en las últimas 24 horas.</em></p>

<h2>🏟️ 10. CONTEXTO COMPETITIVO — RIVALES</h2>
<ul>
<li><strong>Olimpia:</strong> [actividad digital y deportiva o "Sin datos"]</li>
<li><strong>Motagua:</strong> [actividad digital y deportiva o "Sin datos"]</li>
<li><strong>Real España:</strong> [actividad digital y deportiva o "Sin datos"]</li>
<li><strong>Presencia digital de Marathón vs rivales:</strong> [comparación]</li>
</ul>

<h2>📈 11. TENDENCIA DE SENTIMIENTO</h2>
Usa "tendencia_historica" de los datos. Genera una tabla visual — mínimo texto, máximo claridad.

Colores de celda por sentimiento:
- POSITIVO  → style="background:#d4edda;color:#155724;font-weight:bold;text-align:center"
- NEUTRAL   → style="background:#fff3cd;color:#856404;font-weight:bold;text-align:center"
- NEGATIVO  → style="background:#f8d7da;color:#721c24;font-weight:bold;text-align:center"
- MIXTO     → style="background:#d1ecf1;color:#0c5460;font-weight:bold;text-align:center"
- Sin datos → style="background:#f0f0f0;color:#aaa;text-align:center"

Flecha vs día anterior: ↑ mejoró · → igual · ↓ empeoró · — primer día
Riesgo (0–10): 🟢 0–2 · 🟡 3–5 · 🔴 6–8 · 🚨 9–10

<table>
  <tr>
    <th style="text-align:center">Fecha</th>
    <th style="text-align:center">Daniel Otero</th>
    <th style="text-align:center">CD Marathón</th>
    <th style="text-align:center">Afición</th>
    <th style="text-align:center">Posts</th>
    <th style="text-align:center">Alertas</th>
    <th style="text-align:center">Riesgo</th>
  </tr>
  [una fila <tr> por cada día en tendencia_historica, la de HOY con style="outline:2px solid #1a5e1a"]
  [cada celda de sentimiento usa el color correspondiente]
  [celda de Riesgo muestra el emoji + número: ej. 🟡 4]
</table>
<p><strong>Lectura:</strong> [máximo 2 oraciones — ¿la tendencia mejora o empeora? ¿hay punto de inflexión?]</p>
Si no hay historial: <p><em>Primer día — la tabla se construirá a partir de mañana.</em></p>

<h2>🔊 12. RUIDO ORGÁNICO — VOZ DE LA AFICIÓN</h2>
Conversación espontánea de fans en X y Facebook. No son medios — es la afición sin filtro.

<h3>📱 Fans en X (@FuriaVerde1986 · @VerdolagaHN · @MarathonFans)</h3>
<ul>
<li><strong>Sentimiento general de la afición:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>Temas que más generan conversación:</strong> [lista]</li>
<li><strong>Post orgánico más viral:</strong> [cuenta y contenido]</li>
<li><strong>¿Hay presión o inconformidad hacia Otero o el club?:</strong> Sí / No — [descripción]</li>
</ul>

<h3>📘 Fans en Facebook</h3>
<ul>
<li><strong>Estado:</strong> [Con datos / Sin datos — token pendiente]</li>
<li><strong>Sentimiento dominante:</strong> [label o "Sin datos"]</li>
<li><strong>Temas más comentados:</strong> [lista o "Sin datos"]</li>
</ul>

<h3>🌡️ Termómetro de la Afición</h3>
<ul>
<li><strong>Estado del hincha hoy:</strong> Eufórico / Esperanzado / Frustrado / Enojado / Indiferente</li>
<li><strong>Tendencia vs ayer:</strong> ↑ Mejorando / → Estable / ↓ Empeorando / Sin referencia</li>
<li><strong>Señal de alerta temprana:</strong> [presión que podría escalar] o <em>Sin señales.</em></li>
</ul>

<h2>✅ 13. ACCIONES RECOMENDADAS</h2>
Exactamente 3 acciones. Priorizar las que afectan a Daniel Otero directamente.
<h3>[Título Acción 1 — para Otero o Marathón]</h3>
<ul>
<li><strong>Contexto:</strong> [por qué es necesaria ahora]</li>
<li><strong>Acción:</strong> [qué hacer exactamente]</li>
<li><strong>Urgencia:</strong> ALTA / MEDIA / BAJA</li>
</ul>
<h3>[Título Acción 2]</h3>
<ul>
<li><strong>Contexto:</strong> [...]</li>
<li><strong>Acción:</strong> [...]</li>
<li><strong>Urgencia:</strong> [...]</li>
</ul>
<h3>[Título Acción 3]</h3>
<ul>
<li><strong>Contexto:</strong> [...]</li>
<li><strong>Acción:</strong> [...]</li>
<li><strong>Urgencia:</strong> [...]</li>
</ul>"""


# ── Análisis con Claude ──────────────────────────────────────────────────────

def analyze_daily(data_summary: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    now   = datetime.now()
    since = (now - timedelta(hours=24)).strftime("%d/%m %H:%M")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": DAILY_PROMPT.format(
                date=now.strftime("%d de %B, %Y"),
                period_start=since,
                period_end=now.strftime("%d/%m %H:%M"),
                data=data_summary,
            )
        }]
    )
    return msg.content[0].text


# ── Snapshot de sentimiento ──────────────────────────────────────────────────

LABEL_TO_SCORE = {
    "positivo": 1.0, "POSITIVO": 1.0,
    "mixto":    0.2, "MIXTO":    0.2,
    "neutral":  0.0, "NEUTRAL":  0.0,
    "negativo": -1.0, "NEGATIVO": -1.0,
    "sin_datos": 0.0, "error": 0.0,
}

def extract_sentiment_labels(posts: list) -> dict:
    """
    Calcula labels de sentimiento aproximados a partir de los datos brutos:
    mide el ratio de crisis_alerts vs total de posts por categoría.
    Claude dará el análisis real; esto es para el snapshot histórico.
    """
    def score_group(items):
        if not items:
            return 0.0, "NEUTRAL"
        crisis = sum(1 for p in items if p.get("is_alert"))
        ratio  = crisis / len(items)
        if ratio > 0.3:
            return -0.8, "NEGATIVO"
        elif ratio > 0.1:
            return -0.3, "MIXTO"
        else:
            avg_likes = sum(p.get("likes", 0) for p in items) / len(items)
            if avg_likes > 50:
                return 0.8, "POSITIVO"
            return 0.1, "NEUTRAL"

    marathon_posts  = [p for p in posts if p.get("categoria") in ("CLUB_OFICIAL", "MEDIOS", "PERIODISTAS")]
    otero_posts     = [p for p in posts if p.get("subject") == "OTERO"]
    fan_posts       = [p for p in posts if p.get("categoria") in ("FANS_X", "FANS_FB")]
    crisis_total    = sum(1 for p in posts if p.get("is_alert"))

    ms, ml = score_group(marathon_posts)
    os_, ol = score_group(otero_posts)
    fs, fl = score_group(fan_posts)

    return {
        "marathon_score": ms, "marathon_label": ml,
        "otero_score":    os_, "otero_label":   ol,
        "fan_score":      fs,  "fan_label":     fl,
        "post_count":     len(posts),
        "crisis_count":   crisis_total,
        "fan_post_count": len(fan_posts),
    }


# ── HTML del email ───────────────────────────────────────────────────────────

def build_email_html(analysis_html: str) -> str:
    now      = datetime.now()
    date_str = now.strftime("%d de %B, %Y · %H:%M")

    return f"""
    <html>
    <head>
      <style>
        body      {{ font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; color: #222; }}
        h2        {{ margin-top: 28px; padding: 8px 14px; border-radius: 6px;
                     background: #f0f7f0; border-left: 4px solid #1a5e1a; }}
        h3        {{ color: #1a5e1a; margin-top: 16px; margin-bottom: 6px; }}
        table     {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
        th        {{ background: #1a5e1a; color: #fff; padding: 9px 12px; text-align: left; }}
        td        {{ padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
        tr:nth-child(even) {{ background: #f7fcf7; }}
        a         {{ color: #2980b9; }}
        p         {{ line-height: 1.6; }}
        ul        {{ margin: 6px 0; padding-left: 20px; }}
        li        {{ margin: 4px 0; line-height: 1.5; }}

        /* ── Tarjetas para items individuales ── */
        .card          {{ border: 1px solid #dde; border-radius: 8px; padding: 14px 16px;
                          margin: 10px 0; background: #fafafa; }}
        .card ul       {{ margin: 0; padding-left: 18px; }}
        .card li       {{ margin: 5px 0; }}

        /* Colores por nivel de alerta */
        .card-crisis-alto  {{ border-left: 5px solid #c0392b; background: #fff5f5; }}
        .card-crisis-medio {{ border-left: 5px solid #e67e22; background: #fffaf0; }}
        .card-crisis-bajo  {{ border-left: 5px solid #27ae60; background: #f0fff4; }}

        /* Tarjeta de oportunidad */
        .card-oportunidad  {{ border-left: 5px solid #2980b9; background: #f0f7ff; }}

        /* Tarjeta de noticia */
        .card-noticia      {{ border-left: 5px solid #8e44ad; background: #fdf5ff; }}

        /* Tarjeta de fan / ruido orgánico */
        .card-fan          {{ border-left: 5px solid #16a085; background: #f0fffe; }}

        /* Tarjeta neutral / general */
        .card-neutral      {{ border-left: 5px solid #95a5a6; background: #f8f8f8; }}
      </style>
    </head>
    <body>
      <div style="background:#1a5e1a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0">
        <div style="display:flex;align-items:center;gap:14px">
          <span style="font-size:40px">🦖</span>
          <div>
            <h1 style="margin:0;font-size:26px;font-weight:900;letter-spacing:1px">CENTINELA DO-CDM</h1>
            <div style="font-size:11px;opacity:.80;margin-top:3px;letter-spacing:1px">
              Desarrollado por: <b>Stratégica</b>
            </div>
            <div style="font-size:11px;opacity:.65;margin-top:2px;text-transform:uppercase;letter-spacing:2px">
              INFORME DIARIO · Reputación Digital CD Marathón & Daniel Otero
            </div>
          </div>
        </div>
        <p style="margin:12px 0 0;opacity:.75;font-size:13px;
                  border-top:1px solid rgba(255,255,255,.25);padding-top:10px">
          📅 {date_str}
        </p>
      </div>

      <div style="padding:20px;background:#fff;border:1px solid #ddd;
                  border-top:none;border-radius:0 0 8px 8px">
        <div style="background:#e8f5e9;border-left:4px solid #1a5e1a;
                    padding:10px 14px;border-radius:4px;margin-bottom:20px;font-size:13px">
          Monitoreando: <b>CD Marathón · Daniel Otero</b><br>
          Medios: <b>Diario Diez · TVC Deportes · Tigo Sports · HRN · Liga Nacional ·
          FFH · HCH Deportes · Panorama Deportivo</b><br>
          Ruido Orgánico: <b>Furia Verde 1986 · Verdolaga HN · Marathón Fans · Fan Pages FB</b>
        </div>
        {analysis_html}
      </div>

      <p style="color:#aaa;font-size:11px;text-align:center;margin-top:12px">
        🦖 CENTINELA DO-CDM — Desarrollado por Stratégica · Inteligencia Digital Deportiva Honduras
      </p>
    </body>
    </html>"""


# ── Guardar reporte local ────────────────────────────────────────────────────

def save_local_report(html: str) -> str:
    now      = datetime.now()
    dir_path = os.path.join(
        REPORTS_DIR,
        now.strftime("%Y"),
        now.strftime("%m"),
    )
    os.makedirs(dir_path, exist_ok=True)
    filename = f"cdm_{now.strftime('%Y-%m-%d_%H%M')}.html"
    path     = os.path.join(dir_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  ✓ Reporte guardado: {path}")
    return path


# ── Envío de email ───────────────────────────────────────────────────────────

def send_email(html: str, subject: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(REPORT_RECIPIENTS)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_USER, REPORT_RECIPIENTS, msg.as_string())
    log(f"  ✓ Email enviado a: {', '.join(REPORT_RECIPIENTS)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("CENTINELA DO-CDM — Módulo de entrega iniciado")
    db.init_db()

    now = datetime.now()

    log("→ Cargando datos de las últimas 24h…")
    posts = db.get_today_posts()
    news  = db.get_today_news()
    log(f"   {len(posts)} posts · {len(news)} noticias")

    if posts or news:
        # ── Guardar snapshot de sentimiento del día ───────────────────────
        snap = extract_sentiment_labels(posts)
        db.save_sentiment_snapshot(
            date=now.strftime("%Y-%m-%d"),
            marathon_score=snap["marathon_score"],
            otero_score=snap["otero_score"],
            fan_score=snap["fan_score"],
            post_count=snap["post_count"],
            crisis_count=snap["crisis_count"],
            fan_post_count=snap["fan_post_count"],
            marathon_label=snap["marathon_label"],
            otero_label=snap["otero_label"],
            fan_label=snap["fan_label"],
        )
        log(f"  ✓ Snapshot guardado — Marathón: {snap['marathon_label']} · "
            f"Otero: {snap['otero_label']} · Fans: {snap['fan_label']}")

        log("→ Analizando con Claude AI…")
        data_summary  = build_data_summary(posts, news)
        analysis_html = analyze_daily(data_summary)

        email_html = build_email_html(analysis_html)
        save_local_report(email_html)

        subject = f"🦖 CENTINELA DO-CDM — {now.strftime('%A %d/%m/%Y')} · Informe Diario"
        log("→ Enviando informe…")
        send_email(email_html, subject)
    else:
        log("  ⚠️  Sin datos para el informe (¿collect.py corrió?)")

    log("✓ Entrega completa")
    log("=" * 60)


if __name__ == "__main__":
    main()
