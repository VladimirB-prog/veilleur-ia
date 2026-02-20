#!/usr/bin/env python3
"""
VeilleurIA v2.3 — Agent de veille IA agentique avec hub Notion
==============================================================

Skill Claude natif — API Anthropic (claude-sonnet-4-6).

NOUVEAUTÉS v2.3 vs v2.2 :

    ① Partie 3 — Skills Claude
        Nouvelle section dédiée aux skills Claude, MCP, et leur application
        directe à la stack personnelle. Sous-section "Mise en place" qui
        fait le pont entre un concept pédagogique et son implémentation
        concrète dans les skills existants.

    ② Reddit RSS — 3 subreddits
        r/LocalLLaMA, r/AIAgents, r/MachineLearning ajoutés comme sources
        RSS natives (sans API, feedparser suffit). Signal terrain qui
        complète les blogs officiels.

    ③ Hub Notion — 4 destinations automatiques
        Sonnet génère le rapport une seule fois.
        Haiku redistribue ensuite vers 4 bases Notion :
        - 📅 Rapports quotidiens  (1 page complète par jour)
        - 🎓 Base Pédagogie       (1 entrée par concept, avec code coloré)
        - ⚙️  Base Système         (1 entrée par snippet production-ready)
        - 🔗 Mise en place        (1 entrée par action concrète identifiée)

    ④ Telegram — notification courte
        Plus de rapport brut sur Telegram. Juste :
        "📋 Rapport du 18/02 prêt → [lien Notion direct]"

Analogie TP :
    v2.2 = le topographe qui dépose son rapport sur le bureau
    v2.3 = le topographe qui dépose le rapport complet dans le classeur,
           extrait les cotes critiques dans le carnet de bord,
           colle les fiches techniques dans le cahier de références,
           et envoie juste un SMS "rapport dispo, classeur bureau".

Architecture v2.3 :
    Cron 19h45
        ↓
    [1] Collecte RSS → Haiku (10 sources : 7 blogs + 3 Reddit)
        ↓
    [2] Recherche web → Sonnet 4.6 + web_search (12 requêtes : 3 parties)
        ↓
    [3] Passe critique → Haiku (filtre top 5 par partie, 3 parties)
        ↓
    [4] Synthèse rapport → Sonnet 4.6 + Extended Thinking (3 parties)
        ↓
    [5] Redistribution → Haiku × 4 (extrait → Notion bases dédiées)
        ↓
    [6] Notion API → création pages et entrées dans les 4 bases
        ↓
    [7] Telegram → notification courte avec lien Notion

Usage :
    python agent_veilleur_ia_v2_3.py              # Production complète
    python agent_veilleur_ia_v2_3.py --test       # Haiku partout, thinking off
    python agent_veilleur_ia_v2_3.py --dry-run    # Rapport terminal, pas Notion/Telegram
    python agent_veilleur_ia_v2_3.py --feedback like "Super section Skills Claude"

Requirements :
    pip install anthropic feedparser python-telegram-bot python-dotenv tenacity notion-client

Author : Vlad / SRC — Projet Agentic IA 2026
Version : 2.3.0
"""

import argparse
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

# ─── Logging ─────────────────────────────────────────────────────────────────
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
# Analogie TP : chef de chantier (Sonnet) et équipe terrain (Haiku)
MODEL_SYNTHESIS = "claude-sonnet-4-6"          # Synthèse + Extended Thinking
MODEL_COLLECT   = "claude-haiku-4-5-20251001"  # Collecte, critique, redistribution

THINKING_BUDGET   = 3000   # Tokens de réflexion interne Sonnet 4.6
FEEDBACK_FILE     = Path("feedback_history.json")
LOCK_FILE         = Path("/tmp/veilleur_ia.lock")
FEEDBACK_WINDOW   = 14     # Jours de feedback injectés dans le prompt

# ─── Sources RSS ──────────────────────────────────────────────────────────────

# Blogs officiels — Tier 1
RSS_AGENTIQUE = [
    {"name": "Anthropic Blog",  "url": "https://www.anthropic.com/rss.xml",      "focus": "agentique"},
    {"name": "LangChain Blog",  "url": "https://blog.langchain.dev/rss/",         "focus": "agentique"},
    {"name": "Hugging Face",    "url": "https://huggingface.co/papers.rss",       "focus": "agentique"},
    {"name": "The Rundown AI",  "url": "https://www.therundown.ai/feed",          "focus": "agentique"},
    {"name": "Latent Space",    "url": "https://www.latent.space/feed",           "focus": "agentique"},
    # ① NOUVEAU v2.3 — Reddit RSS (sans API, feedparser natif)
    {"name": "r/LocalLLaMA",    "url": "https://www.reddit.com/r/LocalLLaMA/.rss",        "focus": "agentique"},
    {"name": "r/AIAgents",      "url": "https://www.reddit.com/r/AIAgents/.rss",          "focus": "agentique"},
    {"name": "r/MachineLearning","url": "https://www.reddit.com/r/MachineLearning/.rss",  "focus": "agentique"},
]

RSS_OPENCLAW = [
    {"name": "OpenClaw Releases",    "url": "https://github.com/openclaw/openclaw/releases.atom",    "focus": "openclaw"},
    {"name": "OpenClaw Discussions", "url": "https://github.com/openclaw/openclaw/discussions.atom", "focus": "openclaw"},
]

# ② NOUVEAU v2.3 — Sources Skills Claude
RSS_SKILLS_CLAUDE = [
    {"name": "Anthropic Blog",       "url": "https://www.anthropic.com/rss.xml",      "focus": "skills"},
    {"name": "r/ClaudeAI",           "url": "https://www.reddit.com/r/ClaudeAI/.rss", "focus": "skills"},
]

# ─── Requêtes web_search ──────────────────────────────────────────────────────
# 12 requêtes au total (4 par partie)

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

# ② NOUVEAU v2.3 — Requêtes Skills Claude
QUERIES_SKILLS_CLAUDE = [
    "Claude skill MCP tool new release 2026",
    "Anthropic Claude API new feature update 2026",
    "Claude skill builder best practices production 2026",
]

# ─── IDs Notion (à remplir après création des pages) ─────────────────────────
# Pour récupérer un ID Notion : ouvrir la page → "..." → "Copy link"
# L'ID est la suite de chiffres/lettres à la fin de l'URL (32 caractères)
NOTION_DB_RAPPORTS   = os.getenv("NOTION_DB_RAPPORTS_ID", "")    # 📅 Rapports quotidiens
NOTION_DB_PEDAGOGIE  = os.getenv("NOTION_DB_PEDAGOGIE_ID", "")   # 🎓 Base Pédagogie
NOTION_DB_SYSTEME    = os.getenv("NOTION_DB_SYSTEME_ID", "")     # ⚙️  Base Système
NOTION_DB_MISE_EN_PLACE = os.getenv("NOTION_DB_MISE_EN_PLACE_ID", "")  # 🔗 Mise en place


# ─── Classe principale ────────────────────────────────────────────────────────

class VeilleurIA:
    """
    Agent de veille IA agentique v2.3 — Hub Notion + 3 parties.

    Analogie TP :
        L'équipe complète de topographie + archivage :
        - Haiku = ouvriers collecte, tri, redistribution
        - Sonnet 4.6 + Thinking = chef de chantier qui rédige
        - Notion = le classeur de chantier structuré
        - Telegram = le SMS de notification au maître d'ouvrage
    """

    def __init__(self, test_mode: bool = False, dry_run: bool = False) -> None:
        self._check_env()
        self.client    = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.test_mode = test_mode
        self.dry_run   = dry_run

        # En mode test : Haiku pour collecte/redistribution, SONNET pour synthèse
        # Haiku ne suit pas bien les prompts longs à 3 parties
        self.synthesis_model = MODEL_SYNTHESIS  # Toujours Sonnet pour la synthèse
        self.collect_model   = MODEL_COLLECT
        self.use_thinking    = not test_mode    # Thinking off en test pour aller vite

        # Client Notion — initialisé seulement si token disponible
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

        Analogie TP : Vérifier qu'on a bien le badge d'accès au classeur
        avant d'essayer de l'ouvrir.
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
        Collecte les entrées RSS des dernières N heures depuis toutes les sources.

        Analogie TP :
            Ramasser les feuilles de pointage de chaque corps de métier
            déposées depuis hier matin — sans les lire, juste les ramasser.
        """
        entries = []
        cutoff  = datetime.now() - timedelta(hours=max_hours)

        for source in sources:
            try:
                logger.info(f"  📡 {source['name']}")
                feed = feedparser.parse(
                    source["url"],
                    # Header user-agent pour Reddit (bloque les bots sans header)
                    request_headers={"User-Agent": "VeilleurIA/2.3 (veille IA agentique)"}
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
        Résume les entrées RSS brutes via Haiku (déblaiement mécanique).

        Analogie TP :
            L'ouvrier qui retranscrit les cotes brutes sur son carnet :
            travail mécanique, pas de jugement requis.
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

        Analogie TP :
            Le topographe senior avec sa station totale : il fait ses propres
            relevés terrain, ne se contente pas de copier les plans existants.
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

        Analogie TP :
            Avant de présenter au maître d'ouvrage, l'assistant trie les
            50 relevés et ne garde que les 5 cotes critiques pour la décision.
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
        filtered_agentique:   str,
        filtered_openclaw:    str,
        filtered_skills:      str,
        feedback:             str,
    ) -> str:
        """
        Génère le rapport complet via Sonnet 4.6 + Extended Thinking.

        Analogie TP :
            Le conducteur de travaux qui s'assoit 10 minutes avec ses notes
            (Extended Thinking), réfléchit aux connexions entre les 3 chantiers,
            puis rédige le compte-rendu maître d'ouvrage d'une traite.

        Structure rapport v2.3 : 3 parties × (Info + Pédagogie + Système + Mise en place)
        Cible : 6000-7000 mots au total.
        """
        today = datetime.now().strftime("%d/%m/%Y")

        prompt = f"""Tu es VeilleurIA v2.3, expert IA agentique. Rapport quotidien pour Vlad.

PROFIL : Conducteur de travaux TP → reconversion ingénieur IA agentique.
CS50P validé + 275p ML + stack 13 agents en prod. Praticien, pas théoricien.

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
Structure OBLIGATOIRE :
**Concept** : définition claire
**Analogie BTP** : cas concret chantier/TP
**Mécanisme** : comment ça marche sous le capot
**Code** : bloc Python 15-25 lignes, commentaires PAR BLOC (pas ligne par ligne)
**Impact stack** : connexion directe stack V1.0 ou use case SRC
**Ressources** : 1-2 liens concrets

### ⚙️ Système (500-600 mots)
Config ou snippet COMPLET production-ready :
**Architecture** : schéma ASCII si pertinent
**Code production-ready** : complet, commenté par bloc, gestion erreurs
**Commandes exactes** : shell/CLI dans l'ordre
**Paramètres critiques** : valeurs, pièges, defaults dangereux
**Intégration V1.0** : comment brancher sur le Makefile/agents.yaml existant

### 🔗 Mise en place (200-300 mots)
Bridge pédagogie → action concrète :
**Ce concept s'applique à** : quel skill existant de Vlad (VeilleurIA, Sheriff, Coder...)
**3 étapes concrètes** : numérotées, actionnables dès demain
**Commande de test** : valider que c'est en place

---

## 🦞 PARTIE 2 : OPENCLAW

### 📰 Information (200-250 mots)
Releases (numéro version exact), breaking changes, nouvelles features, CVE si applicable.

### 🎓 Pédagogie (400-500 mots)
Structure OBLIGATOIRE :
**Concept OpenClaw** : ce que c'est, pourquoi dans OpenClaw
**Analogie BTP** : OPC, sous-traitants, etc.
**Mécanisme** : agents.yaml, gateway, skills
**Config YAML** : bloc complet commenté par bloc, production-ready
**Cas usage Vlad** : avec VeilleurIA ou stack V1.0
**Commande déploiement** : commande exacte openclaw

### ⚙️ Système (500-600 mots)
AgentSkill ou workflow communautaire :
**Config YAML complète** : commentée par bloc
**Hack communautaire** : technique + contexte
**Intégration KVM1** : comment brancher sur le gateway Hostinger
**Snippet Python** : si applicable, production-ready
**Test validation** : commande pour vérifier avant push prod

### 🔗 Mise en place (200-300 mots)
**S'applique à** : quel composant OpenClaw de la stack Vlad
**3 étapes** : actionnables dès demain
**Commande de test** : validation concrète

---

## 🛠️ PARTIE 3 : SKILLS CLAUDE

### 📰 Information (200-250 mots)
Nouveaux skills, mises à jour MCP, évolutions API Claude, discussions communautaires.

### 🎓 Pédagogie (400-500 mots)
Structure OBLIGATOIRE :
**Concept skill** : ce qu'est ce skill/feature, pourquoi il existe
**Analogie BTP** : connexion terrain TP
**Mécanisme** : comment Claude l'implémente (system prompt, tools, context)
**Exemple config** : YAML ou Python complet, commenté par bloc
**Application VeilleurIA** : comment améliorer VeilleurIA avec ce concept
**Ressources** : doc Anthropic, exemples GitHub

### ⚙️ Système (500-600 mots)
Skill production-ready :
**Config complète** : YAML ou Python, commentée par bloc
**Intégration stack** : comment brancher sur les agents existants
**Paramètres clés** : ce qui change vraiment la qualité
**Test validation** : comment vérifier que le skill fonctionne bien
**Optimisation coût** : si applicable, model routing intelligent

### 🔗 Mise en place (200-300 mots)
**S'applique directement à** : VeilleurIA v2.3 ou skill spécifique existant
**3 étapes concrètes** : numérotées, avec commandes si applicable
**Validation** : comment mesurer que l'amélioration est effective

---

## 💡 INSIGHT DU JOUR (150-200 mots)
Connexion transversale non évidente entre les 3 parties.
Tendance de fond. Implication stratégique pour Vlad.
Pas une conclusion générique — un vrai insight.

---
📊 Sources : [liste clés avec URLs]
⏱️ {datetime.now().strftime("%H:%M")} | VeilleurIA v2.3 | Sonnet 4.6 + Extended Thinking
---

RÈGLES ABSOLUES :
- Code commenté PAR BLOC (pas ligne par ligne, pas sans commentaires)
- Analogies BTP systématiques dans toutes les sections Pédagogie
- Snippets directement intégrables dans la stack V1.0
- Jamais inventer une info — absence > inexactitude
- Si section vide aujourd'hui : développer les autres"""

        params: dict = {
            "model":      self.synthesis_model,
            "max_tokens": 14000,  # thinking (3000) + output 7000 mots (~9000 tokens) + marge
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
        Haiku extrait une section spécifique du rapport pour Notion.

        Analogie TP :
            L'assistant qui photocopie uniquement les pages pertinentes
            du rapport complet pour les classer dans les bons classeurs.

        Args:
            report  : Rapport complet généré par Sonnet
            section : "pedagogie", "systeme" ou "mise_en_place"

        Returns:
            Contenu extrait et formaté pour Notion
        """
        instructions = {
            "pedagogie": """Extrais UNIQUEMENT toutes les sections 🎓 Pédagogie des 3 parties.
Format : ## Partie X — [Titre concept]\n[contenu pédagogie]\n\n""",
            "systeme": """Extrais UNIQUEMENT toutes les sections ⚙️ Système des 3 parties.
Garde tous les blocs de code intacts avec leur syntaxe.
Format : ## Partie X — [Titre]\n[contenu système avec code]\n\n""",
            "mise_en_place": """Extrais UNIQUEMENT toutes les sections 🔗 Mise en place des 3 parties.
Format : ## Partie X — [Skill/composant ciblé]\n[3 étapes + commande test]\n\n""",
        }

        response = self.client.messages.create(
            model=self.collect_model,
            max_tokens=6000,
            messages=[{"role": "user", "content":
                f"{instructions[section]}\n\nRAPPORT COMPLET :\n{report[:40000]}"
            }],
        )
        return response.content[0].text

    # ─── Création page Notion ─────────────────────────────────────────────────

    def _parse_content_to_blocks(self, content: str) -> list:
        """
        Parse le contenu Markdown en blocs Notion proprement.

        Analogie TP :
            Trier les matériaux avant de les ranger : béton avec béton,
            ferraillage avec ferraillage. On ne mélange pas les types.

        Le problème du split naïf sur '\\n\\n' :
            Un bloc ```python\\ncode\\n``` contient des sauts de ligne
            internes → le split le découpe en morceaux inutilisables.
        Solution : on parse ligne par ligne avec un état (dans/hors code).
        """
        blocks = []
        lines = content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # ── Bloc de code : on accumule jusqu'au ``` fermant ──────────
            if line.strip().startswith("```"):
                lang = line.strip().replace("```", "").strip() or "python"
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                code = "\n".join(code_lines).strip()
                if code:
                    # Découpe si > 1990 chars (limite Notion par bloc)
                    for chunk in [code[j:j+1990] for j in range(0, len(code), 1990)]:
                        blocks.append({
                            "object": "block",
                            "type":   "code",
                            "code": {
                                "rich_text": [{"type": "text", "text": {"content": chunk}}],
                                "language":  lang if lang in [
                                    "python", "javascript", "bash", "yaml",
                                    "json", "markdown", "plain text"
                                ] else "plain text",
                            },
                        })
                i += 1  # saute le ``` fermant
                continue

            # ── Titre niveau 1 (#) ────────────────────────────────────────
            if line.startswith("# ") and not line.startswith("## "):
                blocks.append({
                    "object": "block", "type": "heading_1",
                    "heading_1": {"rich_text": [{"type": "text", "text": {
                        "content": line.replace("# ", "")[:200]
                    }}]},
                })
                i += 1
                continue

            # ── Titre niveau 2 (##) ───────────────────────────────────────
            if line.startswith("## "):
                blocks.append({
                    "object": "block", "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {
                        "content": line.replace("## ", "")[:200]
                    }}]},
                })
                i += 1
                continue

            # ── Titre niveau 3 (###) ──────────────────────────────────────
            if line.startswith("### "):
                blocks.append({
                    "object": "block", "type": "heading_3",
                    "heading_3": {"rich_text": [{"type": "text", "text": {
                        "content": line.replace("### ", "")[:200]
                    }}]},
                })
                i += 1
                continue

            # ── Ligne vide → on skippe ────────────────────────────────────
            if not line.strip():
                i += 1
                continue

            # ── Paragraphe standard ───────────────────────────────────────
            for chunk in [line[j:j+1990] for j in range(0, len(line), 1990)]:
                blocks.append({
                    "object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
                })
            i += 1

        return blocks

    def create_notion_page(
        self,
        database_id: str,
        title:       str,
        content:     str,
        categorie:   Optional[str] = None,
    ) -> Optional[str]:
        """
        Crée une sous-page dans une page Notion parente.

        Analogie TP :
            Ajouter une feuille dans le bon classeur avec le bon onglet.

        Args:
            database_id : ID de la page Notion parente
            title       : Titre de la page
            content     : Contenu Markdown à insérer
            categorie   : Non utilisé (pages simples)

        Returns:
            URL de la page créée, ou None si erreur
        """
        if not self.notion or not database_id:
            logger.warning(f"  ⚠️  Notion non disponible pour '{title}'")
            return None

        try:
            # Découpage du contenu en blocs Notion
            content_blocks = []
            for paragraph in content.split("\n\n"):
                if not paragraph.strip():
                    continue
                # Bloc code si commence par ```
                if paragraph.strip().startswith("```"):
                    lang = paragraph.split("\n")[0].replace("```", "").strip() or "python"
                    code = "\n".join(paragraph.split("\n")[1:]).rstrip("`").strip()
                    content_blocks.append({
                        "object": "block",
                        "type":   "code",
                        "code":   {
                            "rich_text": [{"type": "text", "text": {"content": code[:1990]}}],
                            "language":  lang,
                        },
                    })
                elif paragraph.startswith("## "):
                    content_blocks.append({
                        "object": "block",
                        "type":   "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {
                                "content": paragraph.replace("## ", "")[:200]
                            }}]
                        },
                    })
                elif paragraph.startswith("### "):
                    content_blocks.append({
                        "object": "block",
                        "type":   "heading_3",
                        "heading_3": {
                            "rich_text": [{"type": "text", "text": {
                                "content": paragraph.replace("### ", "")[:200]
                            }}]
                        },
                    })
                else:
                    for chunk in [paragraph[i:i+1990] for i in range(0, len(paragraph), 1990)]:
                        content_blocks.append({
                            "object": "block",
                            "type":   "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": chunk}}]
                            },
                        })

            # Création sous-page avec parent = page_id (pas database_id)
            page = self.notion.pages.create(
                parent={"page_id": database_id},
                properties={
                    "title": {"title": [{"text": {"content": title}}]}
                },
                children=self._parse_content_to_blocks(content)[:100],
            )
            url = page.get("url", "")
            logger.info(f"  ✅ Notion page créée : {title} → {url}")
            return url

        except Exception as e:
            logger.error(f"  ❌ Notion erreur ({title}) : {e}")
            return None

    # ─── Envoi notification Telegram ─────────────────────────────────────────

    async def send_telegram_notification(self, notion_url: str, today: str) -> bool:
        """
        Envoie une notification courte sur Telegram avec le lien Notion.

        Analogie TP :
            Le SMS au maître d'ouvrage : "Rapport chantier dispo, voir classeur bureau."
            Pas le rapport complet par SMS — juste la notification.
        """
        try:
            import telegram
            bot     = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
            chat_id = os.getenv("TELEGRAM_CHAT_ID")

            # Message court et lisible — le rapport est sur Notion
            message = (
                f"📋 *VeilleurIA — {today}*\n\n"
                f"Ton rapport quotidien est prêt ✅\n\n"
                f"🧠 Agentique · 🦞 OpenClaw · 🛠️ Skills Claude\n\n"
                f"👉 [Lire le rapport]({notion_url})"
                if notion_url else
                f"📋 *VeilleurIA — {today}*\n\n"
                f"Rapport généré ✅ — consulte Notion pour le lire."
            )

            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
            )
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

        Étapes :
            1. Collecte RSS (10 sources + 2 Skills Claude)
            2. Résumé brut RSS × 3 parties (Haiku)
            3. Recherche web 12 requêtes × 3 parties (Sonnet 4.6)
            4. Passe critique × 3 parties (Haiku)
            5. Synthèse rapport 3 parties (Sonnet 4.6 + Extended Thinking)
            6. Redistribution Notion × 4 bases (Haiku)
            7. Notification Telegram (lien Notion)
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
            logger.info("📡 [1/7] Collecte RSS (10 sources + Reddit)...")
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

            # Archivage local toujours
            report_path = Path(f"rapports/rapport_{datetime.now().strftime('%Y%m%d')}.md")
            report_path.parent.mkdir(exist_ok=True)
            report_path.write_text(report, encoding="utf-8")
            logger.info(f"  💾 Rapport archivé localement : {report_path}")

            # Mode dry-run : affichage terminal uniquement
            if self.dry_run:
                print("\n" + "=" * 64)
                print("📋 RAPPORT v2.3 (dry-run — Notion et Telegram désactivés)")
                print("=" * 64)
                print(report)
                print("=" * 64)
                return 0

            # ── [6/7] Redistribution Notion ───────────────────────────────
            logger.info("📚 [6/7] Redistribution vers Notion (4 bases)...")
            notion_rapport_url = None

            # Base Rapports — rapport complet
            if NOTION_DB_RAPPORTS:
                notion_rapport_url = self.create_notion_page(
                    database_id = NOTION_DB_RAPPORTS,
                    title       = f"Veille IA — {today}",
                    content     = report,
                )

            # Extraction et insertion Pédagogie
            if NOTION_DB_PEDAGOGIE:
                pedagogie_content = self.extract_for_notion(report, "pedagogie")
                self.create_notion_page(
                    database_id = NOTION_DB_PEDAGOGIE,
                    title       = f"Pédagogie — {today}",
                    content     = pedagogie_content,
                )

            # Extraction et insertion Système
            if NOTION_DB_SYSTEME:
                systeme_content = self.extract_for_notion(report, "systeme")
                self.create_notion_page(
                    database_id = NOTION_DB_SYSTEME,
                    title       = f"Système — {today}",
                    content     = systeme_content,
                )

            # Extraction et insertion Mise en place
            if NOTION_DB_MISE_EN_PLACE:
                mep_content = self.extract_for_notion(report, "mise_en_place")
                self.create_notion_page(
                    database_id = NOTION_DB_MISE_EN_PLACE,
                    title       = f"Mise en place — {today}",
                    content     = mep_content,
                )

            # ── [7/7] Notification Telegram ───────────────────────────────
            logger.info("📤 [7/7] Notification Telegram...")
            import asyncio
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
    python agent_veilleur_ia_v2_3.py                         # Production
    python agent_veilleur_ia_v2_3.py --test                  # Haiku partout, rapide
    python agent_veilleur_ia_v2_3.py --dry-run               # Terminal, pas Notion
    python agent_veilleur_ia_v2_3.py --feedback like "Super section Skills Claude"
        """,
    )
    parser.add_argument("--test",    action="store_true", help="Haiku partout, thinking off")
    parser.add_argument("--dry-run", action="store_true", help="Rapport terminal, pas Notion/Telegram")
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
