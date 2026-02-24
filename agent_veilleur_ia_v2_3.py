#!/usr/bin/env python3
"""
VeilleurIA v2.3 — Agent de veille IA agentique avec hub Notion
==============================================================

Skill Claude natif — API Anthropic (claude-sonnet-4-6).

NOUVEAUTÉS v2.3 vs v2.2 :

    ① Partie 3 — Skills Claude
    ② Reddit RSS — 3 subreddits (r/LocalLLaMA, r/AIAgents, r/MachineLearning)
    ③ Hub Notion — 4 destinations automatiques
    ④ Telegram — notification courte avec lien Notion

Analogie TP :
    v2.3 = topographe qui dépose le rapport complet dans le classeur,
           extrait les cotes critiques, et envoie juste un SMS "rapport dispo".

Architecture v2.3 :
    Cron 19h45 → [1] RSS → [2] web_search → [3] critique → [4] synthèse
              → [5] redistribution Notion → [6] Telegram

Usage :
    python agent_veilleur_ia_v2_3.py              # Production complète
    python agent_veilleur_ia_v2_3.py --test       # Thinking off, rapide
    python agent_veilleur_ia_v2_3.py --dry-run    # Rapport terminal uniquement
    python agent_veilleur_ia_v2_3.py --feedback like "Super section Skills Claude"

Requirements :
    pip install anthropic feedparser python-telegram-bot python-dotenv tenacity notion-client

Author : Vlad / SRC — Projet Agentic IA 2026
Version : 2.3.0
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import feedparser
from anthropic import Anthropic
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("veilleur_ia.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

load_dotenv()

# ─── Modèles ──────────────────────────────────────────────────────────────────
MODEL_SYNTHESIS = "claude-sonnet-4-6"
MODEL_COLLECT   = "claude-haiku-4-5-20251001"

THINKING_BUDGET = 3000
FEEDBACK_FILE   = Path("feedback_history.json")
LOCK_FILE       = Path("/tmp/veilleur_ia.lock")
FEEDBACK_WINDOW = 14

# ─── Sources RSS ──────────────────────────────────────────────────────────────
RSS_AGENTIQUE = [
    {"name": "Anthropic Blog",    "url": "https://www.anthropic.com/rss.xml",                      "focus": "agentique"},
    {"name": "LangChain Blog",    "url": "https://blog.langchain.dev/rss/",                         "focus": "agentique"},
    {"name": "Hugging Face",      "url": "https://huggingface.co/papers.rss",                       "focus": "agentique"},
    {"name": "The Rundown AI",    "url": "https://www.therundown.ai/feed",                          "focus": "agentique"},
    {"name": "Latent Space",      "url": "https://www.latent.space/feed",                           "focus": "agentique"},
    {"name": "r/LocalLLaMA",      "url": "https://www.reddit.com/r/LocalLLaMA/.rss",                "focus": "agentique"},
    {"name": "r/AIAgents",        "url": "https://www.reddit.com/r/AIAgents/.rss",                  "focus": "agentique"},
    {"name": "r/MachineLearning", "url": "https://www.reddit.com/r/MachineLearning/.rss",           "focus": "agentique"},
]

RSS_OPENCLAW = [
    {"name": "OpenClaw Releases",    "url": "https://github.com/openclaw/openclaw/releases.atom",    "focus": "openclaw"},
    {"name": "OpenClaw Discussions", "url": "https://github.com/openclaw/openclaw/discussions.atom", "focus": "openclaw"},
]

RSS_SKILLS_CLAUDE = [
    {"name": "Anthropic Blog", "url": "https://www.anthropic.com/rss.xml",      "focus": "skills"},
    {"name": "r/ClaudeAI",     "url": "https://www.reddit.com/r/ClaudeAI/.rss", "focus": "skills"},
]

# ─── Requêtes web_search ──────────────────────────────────────────────────────
QUERIES_AGENTIQUE = [
    "agentic AI framework news today 2026",
    "LangGraph CrewAI AutoGen new release 2026",
    "Claude MCP A2A protocol update latest",
    "ArXiv agentic AI multi-agent paper today 2026",
    "LLM agent benchmark comparison 2026",
    "AI agent security vulnerability CVE 2026",
]

QUERIES_OPENCLAW = [
    "OpenClaw agent framework update 2026",
    "OpenClaw community discussion workflow hack",
    "ClawHub AgentSkill new release security 2026",
]

QUERIES_SKILLS_CLAUDE = [
    "Claude skill MCP tool new release 2026",
    "Anthropic Claude API new feature update 2026",
    "Claude skill builder best practices production 2026",
]

# ─── IDs Notion ───────────────────────────────────────────────────────────────
NOTION_DB_RAPPORTS      = os.getenv("NOTION_DB_RAPPORTS_ID", "")
NOTION_DB_PEDAGOGIE     = os.getenv("NOTION_DB_PEDAGOGIE_ID", "")
NOTION_DB_SYSTEME       = os.getenv("NOTION_DB_SYSTEME_ID", "")
NOTION_DB_MISE_EN_PLACE = os.getenv("NOTION_DB_MISE_EN_PLACE_ID", "")


# ─── Classe principale ────────────────────────────────────────────────────────

class VeilleurIA:
    """Agent de veille IA agentique v2.3 — Hub Notion + 3 parties."""

    def __init__(self, test_mode: bool = False, dry_run: bool = False) -> None:
        self._check_env()
        self.client    = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.test_mode = test_mode
        self.dry_run   = dry_run

        # Sonnet toujours pour la synthèse — Haiku ne suit pas les prompts longs
        self.synthesis_model = MODEL_SYNTHESIS
        self.collect_model   = MODEL_COLLECT
        self.use_thinking    = not test_mode  # Thinking off en test pour aller vite

        self.notion = self._init_notion()

        logger.info(
            f"🚀 VeilleurIA v2.3 | {self.synthesis_model} | "
            f"Thinking: {self.use_thinking} | Notion: {'✅' if self.notion else '❌'} | "
            f"Test: {test_mode} | DryRun: {dry_run}"
        )

    def _check_env(self) -> None:
        """Vérifie les variables d'environnement obligatoires."""
        missing = [v for v in ["ANTHROPIC_API_KEY"] if not os.getenv(v)]
        if missing:
            raise EnvironmentError(f"❌ Variables manquantes : {', '.join(missing)}")

    def _init_notion(self):
        """
        Initialise le client Notion si le token est disponible.

        Analogie TP : Vérifier qu'on a bien le badge d'accès au classeur.
        """
        token = os.getenv("NOTION_TOKEN")
        if not token:
            logger.warning("⚠️  NOTION_TOKEN absent — Notion désactivé")
            return None
        try:
            from notion_client import Client
            client = Client(auth=token)
            logger.info("  ✅ Client Notion initialisé")
            return client
        except ImportError:
            logger.warning("⚠️  notion-client non installé → pip install notion-client")
            return None
        except Exception as e:
            logger.warning(f"⚠️  Erreur init Notion : {e}")
            return None

    # ─── Collecte RSS ─────────────────────────────────────────────────────────

    def collect_rss(self, sources: list[dict], max_hours: int = 24) -> list[dict]:
        """
        Collecte les entrées RSS des dernières N heures.

        Analogie TP : Ramasser les feuilles de pointage depuis hier matin.
        """
        entries = []
        cutoff  = datetime.now() - timedelta(hours=max_hours)

        for source in sources:
            try:
                logger.info(f"  📡 {source['name']}")
                feed = feedparser.parse(
                    source["url"],
                    request_headers={"User-Agent": "VeilleurIA/2.3 (veille IA agentique)"},
                )
                for entry in feed.entries[:8]:
                    pub = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub = datetime(*entry.published_parsed[:6])
                    if pub and pub < cutoff:
                        continue
                    entries.append({
                        "source":    source["name"],
                        "focus":     source["focus"],
                        "title":     entry.get("title", "Sans titre"),
                        "link":      entry.get("link", ""),
                        "summary":   entry.get("summary", "")[:400],
                        "published": pub.isoformat() if pub else "Inconnu",
                    })
            except Exception as e:
                logger.warning(f"  ⚠️  RSS {source['name']} : {e}")

        logger.info(f"  ✅ {len(entries)} entrées collectées")
        return entries

    # ─── Résumé RSS Haiku ─────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def summarize_rss(self, entries: list[dict], focus: str) -> str:
        """
        Résume les entrées RSS brutes via Haiku.

        Analogie TP : L'ouvrier qui retranscrit les cotes brutes — travail mécanique.
        """
        if not entries:
            return f"Aucune entrée RSS récente pour {focus}."

        formatted = "\n".join(
            f"- [{e['source']}] {e['title']}\n  {e['summary']}"
            for e in entries[:12]
        )
        response = self.client.messages.create(
            model=self.collect_model,
            max_tokens=600,
            messages=[{"role": "user", "content":
                f"Résume en 3-5 points clés factuels les infos RSS {focus} :\n\n{formatted}"
            }],
        )
        return response.content[0].text

    # ─── Recherche web Sonnet 4.6 ─────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def search_web(self, queries: list[str], focus: str) -> str:
        """
        Recherche web via Sonnet 4.6 + outil web_search natif.

        Analogie TP : Le topographe senior avec sa station totale.
        """
        logger.info(f"  🔍 {len(queries)} requêtes web ({focus})")
        queries_fmt = "\n".join(f"{i+1}. {q}" for i, q in enumerate(queries))
        response = self.client.messages.create(
            model=self.synthesis_model,
            max_tokens=2500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content":
                f"""Expert IA agentique, veille quotidienne {focus} — {datetime.now().strftime('%d/%m/%Y')}.
Lance ces recherches et synthétise les résultats factuellement :
{queries_fmt}
Identifie : annonces majeures, releases, discussions importantes, sources (URLs)."""
            }],
        )
        return "".join(b.text for b in response.content if hasattr(b, "text")) or "Aucun résultat."

    # ─── Passe critique Haiku ─────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def critical_filter(self, rss: str, web: str, focus: str) -> str:
        """
        Filtre Haiku : extrait le top 5 informations les plus importantes.

        Analogie TP : L'assistant qui trie 50 relevés et garde les 5 cotes critiques.
        """
        logger.info(f"  🎯 Passe critique ({focus})")
        response = self.client.messages.create(
            model=self.collect_model,
            max_tokens=500,
            messages=[{"role": "user", "content":
                f"""Éditeur expert IA {focus}. Identifie les 5 infos les PLUS IMPORTANTES du jour.

RSS : {rss}
WEB : {web}

Critères : nouveauté réelle, impact praticien IA, actionnable, pas de doublon.
Format : 1. [SOURCE] Titre — impact en une phrase (5 max, triés par importance)"""
            }],
        )
        return response.content[0].text

    # ─── Chargement feedback ──────────────────────────────────────────────────

    def load_feedback(self) -> str:
        """Charge le contexte feedback des 14 derniers jours."""
        if not FEEDBACK_FILE.exists():
            return "Aucun feedback historique."
        try:
            with open(FEEDBACK_FILE, encoding="utf-8") as f:
                all_fb = json.load(f)
            cutoff = datetime.now() - timedelta(days=FEEDBACK_WINDOW)
            recent = [fb for fb in all_fb if datetime.fromisoformat(fb["date"]) > cutoff]
            if not recent:
                return "Aucun feedback récent."
            likes    = [fb["note"] for fb in recent if fb["type"] == "like"]
            dislikes = [fb["note"] for fb in recent if fb["type"] == "dislike"]
            notes    = [fb["note"] for fb in recent if fb["type"] == "note"]
            return f"""FEEDBACK 14 DERNIERS JOURS ({len(recent)} retours) :
✅ Apprécié : {chr(10).join(f'- {l}' for l in likes[-5:]) if likes else '- Aucun encore'}
❌ Pas plu : {chr(10).join(f'- {d}' for d in dislikes[-5:]) if dislikes else '- Aucun encore'}
📝 Notes : {chr(10).join(f'- {n}' for n in notes[-3:]) if notes else '- Aucune encore'}
→ Adapte le rapport selon ces préférences."""
        except Exception as e:
            logger.warning(f"⚠️  Feedback : {e}")
            return "Erreur chargement feedback."

    # ─── Synthèse rapport Sonnet 4.6 + Extended Thinking ─────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def generate_report(
        self,
        filtered_agentique: str,
        filtered_openclaw:  str,
        filtered_skills:    str,
        feedback:           str,
    ) -> str:
        """
        Génère le rapport complet via Sonnet 4.6 + Extended Thinking.

        Analogie TP :
            Le conducteur de travaux qui réfléchit (Extended Thinking) puis rédige
            le compte-rendu maître d'ouvrage d'une traite. Cible : 6000-7000 mots.
        """
        # FIX : today correctement indenté dans la méthode
        today = datetime.now().strftime("%d/%m/%Y")

        prompt = f"""Tu es VeilleurIA v2.3, expert IA agentique. Rapport quotidien pour Vlad.

PROFIL : Conducteur de travaux TP → reconversion ingénieur IA agentique.
CS50P validé + 275p ML + stack 13 agents en prod. Praticien, pas théoricien.
OBJECTIF : Imaginer de TOUT NOUVEAUX agents from scratch. Ne relie PAS aux agents existants.

{feedback}

══════════════════════════════════════════
TOP INFOS DU JOUR — {today}
══════════════════════════════════════════

🧠 AGENTIQUE (top 5) : {filtered_agentique}
🦞 OPENCLAW (top 5)  : {filtered_openclaw}
🛠️  SKILLS CLAUDE (top 5) : {filtered_skills}

══════════════════════════════════════════
FORMAT RAPPORT — EXIGENCES STRICTES
══════════════════════════════════════════

Génère EXACTEMENT ce format. Cible : 6000-7000 mots.

---
🤖 VEILLE IA AGENTIQUE — {today}
---

## 🧠 PARTIE 1 : AGENTIQUE GÉNÉRALE

### 📰 Information (200-250 mots)
2-3 news majeures : faits + pourquoi important maintenant + impact concret pour Vlad.

### 🎓 Pédagogie (400-500 mots)
**Concept** : définition claire
**Analogie BTP** : cas concret chantier/TP
**Mécanisme** : comment ça marche sous le capot
**Code** : bloc Python 15-25 lignes, commentaires PAR BLOC
**Nouvelle Application** : imagine un tout NOUVEL agent autonome basé sur ce concept
**Ressources** : 1-2 liens concrets

### ⚙️ Système (500-600 mots)
**Architecture** : schéma ASCII si pertinent
**Code production-ready** : complet, commenté par bloc, gestion erreurs
**Commandes exactes** : shell/CLI dans l'ordre
**Paramètres critiques** : valeurs, pièges, defaults dangereux
**Architecture Nouveau Projet** : structurer un NOUVEL agent de A à Z avec ce snippet

### 🔗 Mise en place (200-300 mots)
**Idée de Nouvel Agent** : quel agent inédit prototyper demain
**3 étapes concrètes** : numérotées, actionnables dès demain
**Commande de test** : valider le POC

---

## 🦞 PARTIE 2 : OPENCLAW

### 📰 Information (200-250 mots)
Releases (numéro version exact), breaking changes, nouvelles features, CVE si applicable.

### 🎓 Pédagogie (400-500 mots)
**Concept OpenClaw** : ce que c'est, pourquoi dans OpenClaw
**Analogie BTP** : OPC, sous-traitants, etc.
**Mécanisme** : agents.yaml, gateway, skills
**Config YAML** : bloc complet commenté par bloc
**Cas d'usage inédit** : nouveau type d'agent à construire avec ce composant
**Commande déploiement** : commande exacte openclaw

### ⚙️ Système (500-600 mots)
**Config YAML complète** : commentée par bloc
**Hack communautaire** : technique + contexte
**Intégration KVM1** : déploiement sur le gateway Hostinger
**Snippet Python** : si applicable, production-ready
**Test validation** : commande avant push prod

### 🔗 Mise en place (200-300 mots)
**Nouvelle piste OpenClaw** : quel nouvel agent imaginer
**3 étapes** : actionnables dès demain
**Commande de test** : validation concrète

---

## 🛠️ PARTIE 3 : SKILLS CLAUDE

### 📰 Information (200-250 mots)
Nouveaux skills, mises à jour MCP, évolutions API Claude, discussions communautaires.

### 🎓 Pédagogie (400-500 mots)
**Concept skill** : ce qu'est ce skill/feature, pourquoi il existe
**Analogie BTP** : connexion terrain TP
**Mécanisme** : comment Claude l'implémente (system prompt, tools, context)
**Exemple config** : YAML ou Python complet, commenté par bloc
**Nouvelle Application** : quel agent innovant créer de zéro grâce à ce skill
**Ressources** : doc Anthropic, exemples GitHub

### ⚙️ Système (500-600 mots)
**Config complète** : YAML ou Python, commentée par bloc
**Implémentation** : intégration dans la conception d'un tout nouvel agent
**Paramètres clés** : ce qui change vraiment la qualité
**Test validation** : vérifier que le skill fonctionne
**Optimisation coût** : model routing si applicable

### 🔗 Mise en place (200-300 mots)
**Inspiration Nouveau Skill** : quel nouveau skill développer
**3 étapes concrètes** : numérotées, avec commandes si applicable
**Validation** : mesurer que le prototype fonctionne

---

## 💡 INSIGHT DU JOUR (150-200 mots)
Connexion transversale non évidente entre les 3 parties.
Tendance de fond. Implication stratégique pour les futurs agents de Vlad.

---
📊 Sources : [liste clés avec URLs]
⏱️ {datetime.now().strftime("%H:%M")} | VeilleurIA v2.3 | Sonnet 4.6 + Extended Thinking
---

RÈGLES ABSOLUES :
- Code commenté PAR BLOC
- Analogies BTP systématiques dans toutes les sections Pédagogie
- NE PAS adapter aux agents existants — idéation nouveaux agents uniquement
- Jamais inventer une info — absence > inexactitude"""

        params: dict = {
            "model":      self.synthesis_model,
            "max_tokens": 14000,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if self.use_thinking:
            params["thinking"] = {"type": "enabled", "budget_tokens": THINKING_BUDGET}
            logger.info(f"  🧠 Extended Thinking activé ({THINKING_BUDGET} tokens budget)")

        response = self.client.messages.create(**params)

        # Extraire uniquement le texte final (pas les blocs thinking internes)
        report = "".join(
            b.text for b in response.content
            if hasattr(b, "type") and b.type == "text"
        )
        return report or "Erreur génération rapport."

    # ─── Redistribution Notion via Haiku ──────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def extract_for_notion(self, report: str, section: str) -> str:
        """
        Haiku extrait une section du rapport — 1 appel par partie pour éviter les troncatures.

        Analogie TP : On photocopie cahier par cahier, pas tout le rapport d'un coup.
        """
        instructions = {
            "pedagogie":     "Extrais UNIQUEMENT la section 🎓 Pédagogie de la PARTIE {partie}. Garde le contenu intégral avec tous les blocs de code.",
            "systeme":       "Extrais UNIQUEMENT la section ⚙️ Système de la PARTIE {partie}. Garde tous les blocs de code intacts.",
            "mise_en_place": "Extrais UNIQUEMENT la section 🔗 Mise en place de la PARTIE {partie}. Garde les 3 étapes et la commande de validation.",
        }

        # Marqueurs début/fin pour localiser chaque partie dans le rapport
        parties_labels = {
            1: ("PARTIE 1", "PARTIE 2"),
            2: ("PARTIE 2", "PARTIE 3"),
            3: ("PARTIE 3", "INSIGHT DU JOUR"),
        }

        full_content = []

        for num_partie, (start_marker, end_marker) in parties_labels.items():
            # Localiser le segment de la partie dans le rapport
            start_idx = report.find(start_marker)
            if start_idx == -1:
                continue
            end_idx = report.find(end_marker, start_idx + len(start_marker))
            segment = report[start_idx:end_idx] if end_idx != -1 else report[start_idx:]

            if not segment.strip():
                continue

            response = self.client.messages.create(
                model=self.collect_model,
                max_tokens=2000,
                messages=[{"role": "user", "content":
                    f"{instructions[section].format(partie=num_partie)}\n\n"
                    f"SEGMENT PARTIE {num_partie} :\n{segment[:15000]}"
                }],
            )
            full_content.append(f"## Partie {num_partie}\n\n{response.content[0].text}")

        return "\n\n---\n\n".join(full_content) or "Extraction vide."

    # ─── Parser Markdown → blocs Notion ──────────────────────────────────────

    def _parse_content_to_blocks(self, content: str) -> list:
        """
        Parse le contenu Markdown en blocs Notion ligne par ligne.

        Analogie TP : Trier béton/ferraillage avant de ranger — pas de mélange.

        Pourquoi ligne par ligne et pas split('\\n\\n') :
            Les blocs ```code``` contiennent des sauts de ligne internes
            que le split naïf découpe en morceaux inutilisables.
        """
        blocks = []
        lines  = content.split("\n")
        i      = 0

        while i < len(lines):
            line = lines[i]

            # ── Bloc de code : accumulation jusqu'au ``` fermant ─────────
            if line.strip().startswith("```"):
                lang       = line.strip().replace("```", "").strip() or "python"
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                code = "\n".join(code_lines).strip()
                if code:
                    valid_langs = ["python", "javascript", "bash", "yaml", "json", "markdown", "plain text"]
                    for chunk in [code[j:j+1990] for j in range(0, len(code), 1990)]:
                        blocks.append({
                            "object": "block", "type": "code",
                            "code": {
                                "rich_text": [{"type": "text", "text": {"content": chunk}}],
                                "language":  lang if lang in valid_langs else "plain text",
                            },
                        })
                i += 1  # saute le ``` fermant
                continue

            # ── Titre # ───────────────────────────────────────────────────
            if line.startswith("# ") and not line.startswith("## "):
                blocks.append({
                    "object": "block", "type": "heading_1",
                    "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:][:200]}}]},
                })
                i += 1; continue

            # ── Titre ## ──────────────────────────────────────────────────
            if line.startswith("## "):
                blocks.append({
                    "object": "block", "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:][:200]}}]},
                })
                i += 1; continue

            # ── Titre ### ─────────────────────────────────────────────────
            if line.startswith("### "):
                blocks.append({
                    "object": "block", "type": "heading_3",
                    "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:][:200]}}]},
                })
                i += 1; continue

            # ── Ligne vide → skip ─────────────────────────────────────────
            if not line.strip():
                i += 1; continue

            # ── Paragraphe standard ───────────────────────────────────────
            for chunk in [line[j:j+1990] for j in range(0, len(line), 1990)]:
                blocks.append({
                    "object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
                })
            i += 1

        return blocks

    # ─── Création page Notion ─────────────────────────────────────────────────

    def create_notion_page(
        self,
        database_id: str,
        title:       str,
        content:     str,
        categorie:   Optional[str] = None,
    ) -> Optional[str]:
        """
        Crée une sous-page dans une page Notion parente.
        Envoie le contenu par batch de 100 blocs (limite API Notion).

        Analogie TP :
            Livrer le béton en plusieurs camions toupie —
            Notion ne peut recevoir que 100 blocs par livraison.
        """
        if not self.notion or not database_id:
            logger.warning(f"  ⚠️  Notion non disponible pour '{title}'")
            return None

        try:
            # Parser le Markdown en blocs Notion
            all_blocks = self._parse_content_to_blocks(content)

            # Création initiale avec les 100 premiers blocs
            page    = self.notion.pages.create(
                parent     = {"page_id": database_id},
                properties = {"title": {"title": [{"text": {"content": title}}]}},
                children   = all_blocks[:100],
            )
            page_id = page.get("id", "")
            url     = page.get("url", "")

            # Append des blocs restants par batch de 100
            remaining = all_blocks[100:]
            while remaining:
                self.notion.blocks.children.append(
                    block_id = page_id,
                    children = remaining[:100],
                )
                remaining = remaining[100:]

            logger.info(f"  ✅ Notion page créée : {title} → {url}")
            return url

        except Exception as e:
            logger.error(f"  ❌ Notion erreur ({title}) : {e}")
            return None

    # ─── Notification Telegram ────────────────────────────────────────────────

    async def send_telegram_notification(self, notion_url: str, today: str) -> bool:
        """
        Envoie une notification courte sur Telegram avec le lien Notion.

        Analogie TP : Le SMS au maître d'ouvrage "rapport dispo, voir classeur".
        """
        try:
            import telegram
            bot     = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
            chat_id = os.getenv("TELEGRAM_CHAT_ID")

            message = (
                f"📋 *VeilleurIA — {today}*\n\n"
                f"Ton rapport quotidien est prêt ✅\n\n"
                f"🧠 Agentique · 🦞 OpenClaw · 🛠️ Skills Claude\n\n"
                f"👉 [Lire le rapport]({notion_url})"
                if notion_url else
                f"📋 *VeilleurIA — {today}*\n\nRapport généré ✅ — consulte Notion."
            )

            await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
            logger.info("  ✅ Notification Telegram envoyée")
            return True
        except Exception as e:
            logger.error(f"  ❌ Telegram : {e}")
            return False

    # ─── Feedback ─────────────────────────────────────────────────────────────

    def save_feedback(self, fb_type: str, note: str) -> None:
        """Enregistre un feedback dans feedback_history.json."""
        existing = []
        if FEEDBACK_FILE.exists():
            with open(FEEDBACK_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        existing.append({
            "type": fb_type, "note": note,
            "date": datetime.now().isoformat(),
            "report_date": datetime.now().strftime("%Y-%m-%d"),
        })
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        logger.info(f"  💾 Feedback '{fb_type}' : {note[:60]}")

    # ─── Pipeline principal ───────────────────────────────────────────────────

    def run(self) -> int:
        """
        Pipeline complet v2.3 — 7 étapes.

        1. Collecte RSS     → 10 sources + Reddit
        2. Résumé RSS       → Haiku × 3 parties
        3. Recherche web    → Sonnet 4.6 × 12 requêtes
        4. Passe critique   → Haiku × 3 parties
        5. Synthèse rapport → Sonnet 4.6 + Extended Thinking
        6. Redistribution   → Notion × 4 bases (Haiku extraction)
        7. Notification     → Telegram avec lien Notion
        """
        if LOCK_FILE.exists() and not self.test_mode:
            logger.warning("⚠️  Lock file présent — pipeline déjà en cours ?")
            return 1

        try:
            LOCK_FILE.touch()
            today = datetime.now().strftime("%d/%m/%Y")
            logger.info("=" * 64)
            logger.info(f"🚀 VeilleurIA v2.3 — {today} {datetime.now().strftime('%H:%M')}")
            logger.info(f"   {self.synthesis_model} | Thinking: {self.use_thinking}")
            logger.info("=" * 64)

            # ── [1/7] Collecte RSS ─────────────────────────────────────────
            logger.info("📡 [1/7] Collecte RSS...")
            rss_agentique = self.collect_rss(RSS_AGENTIQUE)
            rss_openclaw  = self.collect_rss(RSS_OPENCLAW)
            rss_skills    = self.collect_rss(RSS_SKILLS_CLAUDE)

            # ── [2/7] Résumé RSS Haiku ─────────────────────────────────────
            logger.info("⚡ [2/7] Résumé RSS via Haiku (3 parties)...")
            sum_agentique = self.summarize_rss(rss_agentique, "agentique")
            sum_openclaw  = self.summarize_rss(rss_openclaw,  "openclaw")
            sum_skills    = self.summarize_rss(rss_skills,    "skills Claude")

            # ── [3/7] Recherche web Sonnet ─────────────────────────────────
            logger.info("🔍 [3/7] Recherche web Sonnet 4.6 (12 requêtes)...")
            web_agentique = self.search_web(QUERIES_AGENTIQUE, "agentique")
            web_openclaw  = self.search_web(QUERIES_OPENCLAW,  "openclaw")
            web_skills    = self.search_web(QUERIES_SKILLS_CLAUDE, "skills Claude")

            # ── [4/7] Passe critique Haiku ─────────────────────────────────
            logger.info("🎯 [4/7] Passe critique Haiku (3 parties)...")
            fil_agentique = self.critical_filter(sum_agentique, web_agentique, "agentique")
            fil_openclaw  = self.critical_filter(sum_openclaw,  web_openclaw,  "openclaw")
            fil_skills    = self.critical_filter(sum_skills,    web_skills,    "skills Claude")

            # ── [5/7] Synthèse Sonnet 4.6 + Extended Thinking ─────────────
            logger.info("✍️  [5/7] Synthèse Sonnet 4.6 + Extended Thinking...")
            feedback = self.load_feedback()
            report   = self.generate_report(
                filtered_agentique = fil_agentique,
                filtered_openclaw  = fil_openclaw,
                filtered_skills    = fil_skills,
                feedback           = feedback,
            )

            # Archivage local
            report_path = Path(f"rapports/rapport_{datetime.now().strftime('%Y%m%d')}.md")
            report_path.parent.mkdir(exist_ok=True)
            report_path.write_text(report, encoding="utf-8")
            logger.info(f"  💾 Rapport archivé : {report_path}")

            # Mode dry-run : affichage terminal uniquement, pas Notion/Telegram
            if self.dry_run:
                print("\n" + "=" * 64)
                print("📋 RAPPORT v2.3 (dry-run)")
                print("=" * 64)
                print(report)
                return 0

            # ── [6/7] Redistribution Notion ───────────────────────────────
            logger.info("📚 [6/7] Redistribution vers Notion (4 bases)...")
            notion_rapport_url = None

            if NOTION_DB_RAPPORTS:
                notion_rapport_url = self.create_notion_page(
                    database_id = NOTION_DB_RAPPORTS,
                    title       = f"Veille IA — {today}",
                    content     = report,
                )
            if NOTION_DB_PEDAGOGIE:
                self.create_notion_page(
                    database_id = NOTION_DB_PEDAGOGIE,
                    title       = f"Pédagogie — {today}",
                    content     = self.extract_for_notion(report, "pedagogie"),
                )
            if NOTION_DB_SYSTEME:
                self.create_notion_page(
                    database_id = NOTION_DB_SYSTEME,
                    title       = f"Système — {today}",
                    content     = self.extract_for_notion(report, "systeme"),
                )
            if NOTION_DB_MISE_EN_PLACE:
                self.create_notion_page(
                    database_id = NOTION_DB_MISE_EN_PLACE,
                    title       = f"Mise en place — {today}",
                    content     = self.extract_for_notion(report, "mise_en_place"),
                )

            # ── [7/7] Notification Telegram ───────────────────────────────
            logger.info("📤 [7/7] Notification Telegram...")
            asyncio.run(self.send_telegram_notification(
                notion_url = notion_rapport_url or "",
                today      = today,
            ))

            logger.info("✅ Pipeline VeilleurIA v2.3 terminé avec succès")
            return 0

        except Exception as e:
            logger.error(f"❌ Erreur pipeline : {e}", exc_info=True)
            return 1
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="VeilleurIA v2.3 — Sonnet 4.6 + Notion + 3 parties",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
    python agent_veilleur_ia_v2_3.py                           # Production
    python agent_veilleur_ia_v2_3.py --test                    # Thinking off, rapide
    python agent_veilleur_ia_v2_3.py --dry-run                 # Terminal, pas Notion
    python agent_veilleur_ia_v2_3.py --feedback like "Super section Skills Claude"
        """,
    )
    parser.add_argument("--test",     action="store_true", help="Thinking off, rapide")
    parser.add_argument("--dry-run",  action="store_true", help="Rapport terminal, pas Notion/Telegram")
    parser.add_argument("--feedback", nargs=2, metavar=("TYPE", "NOTE"),
                        help="like | dislike | note 'texte'")
    args = parser.parse_args()

    if args.feedback:
        fb_type, fb_note = args.feedback
        if fb_type not in ("like", "dislike", "note"):
            print(f"❌ Type invalide : {fb_type}")
            return 1
        agent = VeilleurIA(test_mode=True, dry_run=True)
        agent.save_feedback(fb_type, fb_note)
        print(f"✅ Feedback '{fb_type}' : {fb_note}")
        return 0

    agent = VeilleurIA(test_mode=args.test, dry_run=args.dry_run)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
