#!/usr/bin/env python3
"""
VeilleurIA v2.1 — Agent de veille informationnelle IA agentique
==============================================================

Skill Claude natif — API Anthropic (claude-sonnet-4-6).
Version 2.1 : 3 leviers qualité activés pour tirer le maximum de Sonnet 4.6.

NOUVEAUTÉS v2.1 vs v2.0 :
    Levier 1 — Extended Thinking sur la synthèse finale
        Sonnet 4.6 "réfléchit" avant de rédiger : croise RSS + web_search,
        détecte les redondances, identifie le signal vs le bruit.
        Résultat : rapport plus dense, moins de remplissage.

    Levier 2 — 9 requêtes web_search (vs 6) mieux ciblées
        Ajout de 3 nouvelles zones de relevé :
        - Papers ArXiv agentique du jour
        - Benchmarks comparatifs modèles
        - CVE et sécurité agentique

    Levier 3 — Passe critique Haiku avant synthèse Sonnet
        Haiku filtre les top 5 informations les plus importantes
        depuis toutes les sources collectées. Sonnet ne reçoit que
        le signal propre → rapport sans dilution.

Analogie TP :
    v2.0 = topographe qui recopie tous ses relevés bruts dans le rapport
    v2.1 = topographe qui trie ses relevés (Haiku), réfléchit aux cotes
           critiques (Extended Thinking), puis rédige le compte-rendu
           de chantier avec uniquement ce qui compte pour la décision.

Architecture v2.1 :
    Cron 19h45
        ↓
    [1] Collecte RSS → Haiku (résumé brut)
        ↓
    [2] Recherche web → Sonnet 4.6 + web_search (9 requêtes ciblées)
        ↓
    [3] Passe critique → Haiku (filtre top 5 par partie) ← NOUVEAU
        ↓
    [4] Synthèse finale → Sonnet 4.6 + Extended Thinking ← NOUVEAU
        ↓
    [5] Feedback injecté → apprentissage continu
        ↓
    Telegram push 20h00

Usage :
    python agent_veilleur_ia_v2_1.py           # Run complet production
    python agent_veilleur_ia_v2_1.py --test    # Run test avec Haiku partout
    python agent_veilleur_ia_v2_1.py --dry-run # Rapport sans Telegram
    python agent_veilleur_ia_v2_1.py --feedback like "Excellent focus OpenClaw"

Requirements :
    pip install anthropic feedparser python-telegram-bot python-dotenv tenacity

Author : Vlad / SRC — Projet Agentic IA 2026
Version : 2.2.0 (Extended Thinking + 9 requêtes + passe critique + prompt dense 4000-5000 mots)
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

# ─── Configuration logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("veilleur_ia.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ─── Variables d'environnement ────────────────────────────────────────────────
load_dotenv()

# ─── Constantes modèles ───────────────────────────────────────────────────────

# Analogie TP : 3 niveaux d'ouvriers selon la complexité de la tâche
MODEL_SYNTHESIS = "claude-sonnet-4-6"         # Chef de chantier : synthèse + thinking
MODEL_COLLECT   = "claude-haiku-4-5-20251001" # Ouvrier qualifié : collecte + critique

# Budget tokens pour l'Extended Thinking (réflexion interne, non comptés output)
# 3000 tokens = ~2-3 minutes de "réflexion" avant rédaction
THINKING_BUDGET = 3000

# ─── Fichiers de persistance ─────────────────────────────────────────────────
FEEDBACK_FILE = Path("feedback_history.json")
LOCK_FILE     = Path("/tmp/veilleur_ia.lock")
FEEDBACK_WINDOW_DAYS = 14

# ─── Sources RSS ─────────────────────────────────────────────────────────────

RSS_SOURCES_AGENTIQUE = [
    {"name": "Anthropic Blog",    "url": "https://www.anthropic.com/rss.xml",        "tier": 1, "focus": "agentique"},
    {"name": "LangChain Blog",    "url": "https://blog.langchain.dev/rss/",           "tier": 1, "focus": "agentique"},
    {"name": "Hugging Face",      "url": "https://huggingface.co/papers.rss",         "tier": 1, "focus": "agentique"},
    {"name": "The Rundown AI",    "url": "https://www.therundown.ai/feed",            "tier": 2, "focus": "agentique"},
    {"name": "Latent Space",      "url": "https://www.latent.space/feed",             "tier": 1, "focus": "agentique"},
]

RSS_SOURCES_OPENCLAW = [
    {"name": "OpenClaw Releases",    "url": "https://github.com/openclaw/openclaw/releases.atom",    "tier": 1, "focus": "openclaw"},
    {"name": "OpenClaw Discussions", "url": "https://github.com/openclaw/openclaw/discussions.atom", "tier": 1, "focus": "openclaw"},
]

# ─── LEVIER 2 : 9 requêtes web_search (vs 6 en v2.0) ─────────────────────────
# Nouvelles zones de relevé : ArXiv papers, benchmarks, sécurité agentique

SEARCH_QUERIES_AGENTIQUE = [
    # Bloc 1 — News et releases (identique v2.0)
    "agentic AI framework news today 2026",
    "LangGraph CrewAI AutoGen new release 2026",
    "Claude MCP A2A protocol update latest",
    # Bloc 2 — NOUVEAU : papers académiques du jour
    "ArXiv agentic AI multi-agent paper today 2026",
    # Bloc 3 — NOUVEAU : benchmarks comparatifs
    "LLM agent benchmark comparison 2026 performance",
    # Bloc 4 — NOUVEAU : sécurité agentique
    "AI agent security vulnerability prompt injection 2026",
]

SEARCH_QUERIES_OPENCLAW = [
    # Bloc 1 — Communauté et releases (identique v2.0)
    "OpenClaw agent framework update 2026",
    "OpenClaw community discussion hack workflow",
    # Bloc 2 — NOUVEAU : ClawHub sécurité élargi
    "ClawHub AgentSkill new release security CVE 2026",
]


# ─── Classe principale ────────────────────────────────────────────────────────

class VeilleurIA:
    """
    Agent de veille IA agentique — v2.1 avec 3 leviers qualité.

    Analogie TP :
        L'équipe complète de topographie :
        - Haiku = ouvriers qui font les relevés terrain et trient les cotes
        - Sonnet 4.6 + Extended Thinking = chef de chantier qui réfléchit
          aux implications avant de rédiger le compte-rendu maître d'ouvrage
    """

    def __init__(self, test_mode: bool = False, dry_run: bool = False) -> None:
        """
        Initialise l'agent.

        Args:
            test_mode : Si True, utilise Haiku partout + désactive Extended Thinking
            dry_run   : Si True, affiche rapport sans envoyer sur Telegram
        """
        self._check_env_vars()

        self.client    = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.test_mode = test_mode
        self.dry_run   = dry_run

        # En mode test : Haiku partout, Extended Thinking désactivé
        self.synthesis_model    = MODEL_COLLECT if test_mode else MODEL_SYNTHESIS
        self.collect_model      = MODEL_COLLECT
        # Extended Thinking désactivé en mode test (non supporté par Haiku)
        self.use_thinking       = not test_mode

        logger.info(
            f"🚀 VeilleurIA v2.1 | Modèle: {self.synthesis_model} | "
            f"Thinking: {self.use_thinking} | Test: {test_mode} | DryRun: {dry_run}"
        )

    def _check_env_vars(self) -> None:
        """Vérifie la présence des variables d'environnement requises."""
        required = ["ANTHROPIC_API_KEY"]
        missing = [v for v in required if not os.getenv(v)]
        if missing:
            raise EnvironmentError(
                f"❌ Variables manquantes dans .env : {', '.join(missing)}"
            )

    # ─── Collecte RSS ─────────────────────────────────────────────────────────

    def collect_rss_entries(self, sources: list[dict], max_hours: int = 24) -> list[dict]:
        """
        Collecte les entrées RSS des dernières N heures.

        Analogie TP :
            Ramasser les feuilles de pointage de chaque corps de métier
            déposées depuis hier matin — sans les lire, juste les ramasser.

        Args:
            sources   : Sources RSS à consulter
            max_hours : Fenêtre temporelle

        Returns:
            Liste d'articles récents {source, title, link, summary, published}
        """
        entries = []
        cutoff  = datetime.now() - timedelta(hours=max_hours)

        for source in sources:
            try:
                logger.info(f"  📡 RSS : {source['name']}")
                feed = feedparser.parse(source["url"])

                for entry in feed.entries[:10]:
                    pub_date = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])

                    if pub_date and pub_date < cutoff:
                        continue

                    entries.append({
                        "source":    source["name"],
                        "focus":     source["focus"],
                        "tier":      source["tier"],
                        "title":     entry.get("title", "Sans titre"),
                        "link":      entry.get("link", ""),
                        "summary":   entry.get("summary", "")[:500],
                        "published": pub_date.isoformat() if pub_date else "Inconnu",
                    })

            except Exception as e:
                logger.warning(f"  ⚠️  Erreur RSS {source['name']} : {e}")

        logger.info(f"  ✅ {len(entries)} entrées RSS collectées")
        return entries

    # ─── Résumé brut RSS via Haiku ────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def summarize_rss_with_haiku(self, entries: list[dict], focus: str) -> str:
        """
        Résume les entrées RSS brutes via Haiku.

        Analogie TP :
            L'ouvrier qui retranscrit les cotes brutes sur son carnet :
            travail mécanique de déblaiement, pas de jugement.

        Args:
            entries : Articles RSS collectés
            focus   : "agentique" ou "openclaw"

        Returns:
            Résumé brut (5 points clés maximum)
        """
        if not entries:
            return f"Aucune entrée RSS récente pour {focus}."

        formatted = "\n".join(
            f"- [{e['source']}] {e['title']} ({e['published']})\n  {e['summary']}"
            for e in entries[:15]
        )

        prompt = f"""Tu es un assistant de veille technique spécialisé en IA {focus}.
Voici les entrées RSS des dernières 24h :

{formatted}

Résume en 3-5 points clés factuels les informations les plus importantes.
Sois bref et précis. Pas de mise en forme complexe."""

        response = self.client.messages.create(
            model=self.collect_model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    # ─── Recherche web Sonnet 4.6 + web_search (Levier 2) ────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def search_with_sonnet(self, queries: list[str], focus: str) -> str:
        """
        Lance des recherches web via Sonnet 4.6 + outil web_search natif.

        Analogie TP :
            Le topographe senior avec sa station totale (Sonnet 4.6) :
            il fait ses propres relevés sur le terrain, pas juste copier
            les plans des autres. Il juge la pertinence des cotes lui-même.

        Note Sonnet 4.6 :
            web_search amélioré nativement — traite et filtre les résultats
            automatiquement pour optimiser qualité et efficacité tokens.

        Args:
            queries : 3 ou 6 requêtes selon la section
            focus   : "agentique" ou "openclaw"

        Returns:
            Synthèse structurée des résultats web
        """
        logger.info(f"  🔍 {len(queries)} requêtes web_search ({focus})")

        queries_formatted = "\n".join(f"{i+1}. {q}" for i, q in enumerate(queries))

        prompt = f"""Tu es un expert en IA agentique chargé d'une veille quotidienne.
Date : {datetime.now().strftime('%d/%m/%Y')}

Lance ces recherches pour la section "{focus}" du rapport :
{queries_formatted}

Pour chaque recherche :
1. Trouve les informations les plus récentes et pertinentes
2. Identifie les annonces majeures, releases, discussions importantes
3. Note les sources (URLs)
4. Signale explicitement si rien de notable aujourd'hui

Produis une synthèse factuelle et structurée."""

        response = self.client.messages.create(
            model=self.synthesis_model,
            max_tokens=2500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extraction du texte final après les éventuels tool_use blocks
        result_text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        return result_text or "Aucun résultat de recherche disponible."

    # ─── LEVIER 3 : Passe critique Haiku ──────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def critical_filter_with_haiku(
        self,
        rss_summary: str,
        search_results: str,
        focus: str,
    ) -> str:
        """
        Passe critique Haiku : filtre les top 5 informations les plus importantes.

        Analogie TP :
            Avant de présenter au maître d'ouvrage, le chef de chantier demande
            à son assistant de trier les 50 relevés et de ne garder que les
            5 cotes critiques pour la décision. Le maître d'ouvrage ne voit
            que ce qui compte — pas le relevé exhaustif complet.

        Pourquoi Haiku et pas Sonnet ?
            C'est du filtrage éditorial, pas du raisonnement complexe.
            Haiku reconnaît parfaitement ce qui est important dans un corpus.
            Économie : ~0.002$ vs ~0.04$ pour Sonnet sur cette passe.

        Args:
            rss_summary    : Résumé RSS Haiku de la section
            search_results : Résultats recherche web Sonnet
            focus          : "agentique" ou "openclaw"

        Returns:
            Top 5 informations filtrées, prêtes pour Sonnet
        """
        logger.info(f"  🎯 Passe critique Haiku ({focus})")

        prompt = f"""Tu es un éditeur expert en IA {focus}.

Voici toutes les informations collectées aujourd'hui pour la section "{focus}" :

SOURCES RSS :
{rss_summary}

RECHERCHES WEB :
{search_results}

Ta tâche : identifier et lister les 5 informations les PLUS IMPORTANTES de la journée.
Critères de sélection :
- Nouveauté réelle (pas une répétition d'hier)
- Impact concret sur les praticiens IA
- Actionnable ou pédagogiquement riche
- Pas de doublon entre RSS et web search

Format de réponse :
1. [SOURCE] Titre ou sujet — impact en une phrase
2. ...
(5 éléments maximum, triés par importance décroissante)

Si moins de 5 informations notables : liste uniquement les vraies nouveautés."""

        response = self.client.messages.create(
            model=self.collect_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    # ─── Chargement feedback ──────────────────────────────────────────────────

    def load_feedback_context(self) -> str:
        """
        Charge le contexte de feedback des 14 derniers jours.

        Analogie TP :
            Relire les annotations du maître d'ouvrage sur les
            comptes-rendus précédents avant de rédiger le nouveau.

        Returns:
            Texte de contexte à injecter dans le prompt de synthèse
        """
        if not FEEDBACK_FILE.exists():
            return "Aucun feedback historique. Premier rapport ou historique vide."

        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                all_feedback = json.load(f)

            cutoff = datetime.now() - timedelta(days=FEEDBACK_WINDOW_DAYS)
            recent = [
                fb for fb in all_feedback
                if datetime.fromisoformat(fb["date"]) > cutoff
            ]

            if not recent:
                return "Aucun feedback dans les 14 derniers jours."

            likes    = [fb["note"] for fb in recent if fb["type"] == "like"]
            dislikes = [fb["note"] for fb in recent if fb["type"] == "dislike"]
            notes    = [fb["note"] for fb in recent if fb["type"] == "note"]

            return f"""HISTORIQUE FEEDBACK ({len(recent)} retours — 14 derniers jours) :

✅ CE QUI A ÉTÉ APPRÉCIÉ :
{chr(10).join(f'- {l}' for l in likes[-5:]) if likes else '- Aucun retour positif encore'}

❌ CE QUI N'A PAS PLU :
{chr(10).join(f'- {d}' for d in dislikes[-5:]) if dislikes else '- Aucun retour négatif encore'}

📝 NOTES LIBRES :
{chr(10).join(f'- {n}' for n in notes[-3:]) if notes else '- Aucune note libre encore'}

→ Adapte le rapport en tenant compte de ces préférences."""

        except Exception as e:
            logger.warning(f"  ⚠️  Erreur chargement feedback : {e}")
            return "Erreur chargement feedback — rapport standard."

    # ─── LEVIER 1 : Synthèse finale Sonnet 4.6 + Extended Thinking ───────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_final_report(
        self,
        filtered_agentique: str,
        filtered_openclaw: str,
        feedback_context: str,
    ) -> str:
        """
        Génère le rapport final via Sonnet 4.6 avec Extended Thinking activé.

        LEVIER 1 — Extended Thinking :
            Avant de rédiger, Sonnet 4.6 "réfléchit" en interne avec un budget
            de THINKING_BUDGET tokens. Il croise les informations filtrées,
            identifie les connexions non évidentes entre agentique et OpenClaw,
            et décide de la structure optimale du rapport.

            Analogie TP :
                Le conducteur de travaux qui s'assoit 10 minutes avec ses notes
                avant de rédiger le compte-rendu — il réfléchit, croise les
                informations, anticipe les questions du maître d'ouvrage. Il
                ne dicte pas au fil de la plume.

        Note : en mode test, thinking est désactivé (Haiku ne le supporte pas).

        Args:
            filtered_agentique : Top 5 infos agentique (passe critique Haiku)
            filtered_openclaw  : Top 5 infos OpenClaw (passe critique Haiku)
            feedback_context   : Historique feedback utilisateur

        Returns:
            Rapport Markdown structuré prêt pour Telegram
        """
        today = datetime.now().strftime("%d/%m/%Y")

        prompt = f"""Tu es VeilleurIA, expert en IA agentique. Tu génères un rapport de veille
quotidien pour Vlad — conducteur de travaux TP en reconversion ingénierie IA.

PROFIL VLAD :
- Conducteur de travaux TP (réseaux eau, assainissement, hydraulique) → raisonnement terrain solide
- CS50P validé + 275 pages ML → base technique réelle, pas débutant
- Stack multi-agents V1.0 en prod (13 agents, Makefile, Telegram, VPS) → praticien, pas théoricien
- Objectif : devenir ingénieur IA agentique → chaque rapport = cours + ressource de référence

{feedback_context}

═══════════════════════════════════════
TOP INFORMATIONS DU JOUR — {today}
(pré-filtrées et triées par importance)
═══════════════════════════════════════

🧠 AGENTIQUE GÉNÉRALE (top 5) :
{filtered_agentique}

🦞 OPENCLAW (top 5) :
{filtered_openclaw}

═══════════════════════════════════════
STRUCTURE DU RAPPORT — EXIGENCES DÉTAILLÉES
═══════════════════════════════════════

Génère le rapport EXACTEMENT selon ce format.
CIBLE : 4000 à 5000 mots au total. Chaque section doit être SUBSTANTIELLE.

---
🤖 VEILLE IA AGENTIQUE — {today}
---

## 🧠 PARTIE 1 : AGENTIQUE GÉNÉRALE

### 📰 Information (200-250 mots)
Pour chaque news majeure du jour (2-3 maximum) :
- Ce qui s'est passé (les faits bruts)
- Pourquoi c'est important maintenant (contexte dans l'évolution du domaine)
- Impact concret pour un praticien IA comme Vlad (pas "c'est intéressant", mais "ça change X dans ton workflow")
Pas de résumé de titre. L'impact réel, la portée réelle.

### 🎓 Pédagogie (400-500 mots)
Un concept agentique mis en lumière par l'actualité du jour. Structure obligatoire :

**Le concept** : définition claire en 2-3 phrases, sans jargon inutile
**L'analogie BTP** : explication via un cas concret de chantier/TP (réseau eau, terrassement, OPC, etc.)
**Comment ça marche techniquement** : le mécanisme sous le capot, avec les termes exacts du domaine
**Exemple de code minimal** : 15-25 lignes Python commentées montrant le concept en action
**Ce que ça change pour toi** : connexion directe avec la stack V1.0 de Vlad ou un use case SRC réel
**Pour aller plus loin** : 1-2 ressources concrètes (doc officielle, paper, repo GitHub)

### ⚙️ Système (500-600 mots)
Les éléments directement implémentables issus de l'actualité du jour :

**Architecture ou pattern** : schéma ASCII si pertinent, description du flux de données
**Config ou snippet production-ready** : code complet avec tous les paramètres, commentaires inline,
  gestion d'erreurs, prêt à coller dans un projet réel
**Commandes exactes** : les commandes shell/CLI avec leurs flags, dans l'ordre d'exécution
**Paramètres critiques** : les valeurs à ne pas rater, les pièges courants, les defaults dangereux
**Compatibilité stack V1.0** : comment intégrer avec le Makefile, agents.yaml, ou pipeline Telegram existant

---

## 🦞 PARTIE 2 : OPENCLAW

### 📰 Information (200-250 mots)
Releases, annonces, discussions communautaires du jour :
- Numéro de version exact si release (ex: v2.3.1)
- Ce qui change concrètement (breaking changes, nouvelles features, deprecations)
- Signalement si CVE ou advisory sécurité → impact sur la stack de Vlad

### 🎓 Pédagogie (400-500 mots)
Un concept ou feature OpenClaw mis en lumière aujourd'hui. Structure obligatoire :

**Le concept OpenClaw** : ce que c'est, pourquoi c'est dans OpenClaw et pas ailleurs
**L'analogie BTP** : explication terrain (OPC = orchestrateur, sous-traitants = sub-agents, etc.)
**Mécanisme interne** : comment OpenClaw implémente ça sous le capot (agents.yaml, gateway, skills)
**Exemple de configuration** : bloc YAML ou Python complet, commenté, production-ready
**Cas d'usage Vlad** : comment utiliser ça avec VeilleurIA ou la stack V1.0 existante
**Commande de déploiement** : la commande exacte openclaw pour activer/tester cette feature

### ⚙️ Système (500-600 mots)
Tout ce qui est directement utilisable depuis la communauté OpenClaw aujourd'hui :

**AgentSkill ou workflow remarquable** : description + config YAML complète si disponible
**Hack ou pattern communautaire** : la technique qui circule, expliquée et contextualisée
**Intégration concrète** : comment brancher ça sur le gateway de Vlad (KVM1 ou KVM2 Hostinger)
**Snippet Python ou YAML production-ready** : code complet avec commentaires, gestion erreurs
**Test de validation** : la commande pour vérifier que ça fonctionne avant push en prod

---

## 💡 INSIGHT DU JOUR (150-200 mots)
Une observation transversale non évidente :
- Connexion entre un développement agentique général et une évolution OpenClaw
- Tendance de fond qui se dessine à travers plusieurs news du jour
- Implication stratégique pour la stack ou la reconversion de Vlad
Pas une conclusion générique — un vrai insight que seul quelqu'un qui a lu tout le rapport peut formuler.

---
📊 Sources utilisées : [liste des sources clés avec URLs]
⏱️ {datetime.now().strftime("%H:%M")} | VeilleurIA v2.2 | Sonnet 4.6 + Extended Thinking + Passe critique
---

RÈGLES ABSOLUES :
- DENSITÉ avant tout : chaque section doit atteindre sa cible en mots, pas de remplissage vide
- Pédagogique ET actionnable : expliquer le concept ET donner le code pour l'implémenter
- Analogies BTP systématiques dans les sections Pédagogie — c'est le pont cognitif de Vlad
- Code production-ready : gestion d'erreurs, commentaires en français, type hints, pas de pseudocode
- Si une info n'est pas disponible aujourd'hui : développer davantage les autres sections
- Jamais inventer une information — préférer l'absence à l'inexactitude
- Les snippets code doivent être directement intégrables dans la stack V1.0 existante"""

        # Construction des paramètres — Extended Thinking conditionnel
        # max_tokens = thinking_budget (3000) + output cible (~8500 tokens) + marge
        create_params: dict = {
            "model":      self.synthesis_model,
            "max_tokens": 12000,
            "messages":   [{"role": "user", "content": prompt}],
        }

        # LEVIER 1 : Active Extended Thinking si Sonnet 4.6 (pas Haiku)
        if self.use_thinking:
            create_params["thinking"] = {
                "type":         "enabled",
                "budget_tokens": THINKING_BUDGET,
            }
            logger.info(f"  🧠 Extended Thinking activé (budget: {THINKING_BUDGET} tokens)")

        response = self.client.messages.create(**create_params)

        # Extraction uniquement du texte final (pas des blocs thinking internes)
        report_text = "".join(
            block.text
            for block in response.content
            if hasattr(block, "text") and block.type == "text"
        )

        # Log du thinking utilisé pour monitoring des coûts
        if self.use_thinking:
            thinking_used = sum(
                len(block.thinking) if hasattr(block, "thinking") else 0
                for block in response.content
                if hasattr(block, "type") and block.type == "thinking"
            )
            logger.info(f"  📊 Thinking utilisé : ~{thinking_used} chars internes")

        return report_text or "Erreur génération rapport — contenu vide."

    # ─── Envoi Telegram ───────────────────────────────────────────────────────

    async def send_telegram(self, report: str) -> bool:
        """
        Envoie le rapport sur Telegram.
        Découpe automatiquement si > 4000 caractères (limite Telegram).

        Args:
            report : Rapport Markdown

        Returns:
            True si succès, False sinon
        """
        try:
            import telegram

            bot     = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
            chat_id = os.getenv("TELEGRAM_CHAT_ID")

            max_len = 4000
            chunks  = [report[i: i + max_len] for i in range(0, len(report), max_len)]

            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    chunk = f"[{i+1}/{len(chunks)}]\n{chunk}"
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode="Markdown",
                )

            logger.info(f"  ✅ Rapport envoyé Telegram ({len(chunks)} message(s))")
            return True

        except Exception as e:
            logger.error(f"  ❌ Erreur Telegram : {e}")
            return False

    # ─── Enregistrement feedback ──────────────────────────────────────────────

    def save_feedback(self, feedback_type: str, note: str, report_date: Optional[str] = None) -> None:
        """
        Enregistre un feedback utilisateur dans feedback_history.json.

        Args:
            feedback_type : "like", "dislike" ou "note"
            note          : Texte du feedback
            report_date   : Date du rapport concerné (optionnel)
        """
        existing = []
        if FEEDBACK_FILE.exists():
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)

        existing.append({
            "type":        feedback_type,
            "note":        note,
            "date":        datetime.now().isoformat(),
            "report_date": report_date or datetime.now().strftime("%Y-%m-%d"),
        })

        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        logger.info(f"  💾 Feedback '{feedback_type}' : {note[:60]}...")

    # ─── Pipeline principal ───────────────────────────────────────────────────

    def run(self) -> int:
        """
        Pipeline complet v2.1 — 6 étapes (vs 5 en v2.0).

        Étapes :
            1. Collecte RSS (Haiku — mécanique)
            2. Résumé brut RSS (Haiku — déblaiement)
            3. Recherche web 9 requêtes (Sonnet 4.6 + web_search)
            4. Passe critique (Haiku — filtre top 5) ← NOUVEAU v2.1
            5. Synthèse finale (Sonnet 4.6 + Extended Thinking) ← NOUVEAU v2.1
            6. Envoi Telegram

        Returns:
            0 si succès, 1 si erreur
        """
        if LOCK_FILE.exists() and not self.test_mode:
            logger.warning("⚠️  Lock file présent — pipeline déjà en cours ?")
            return 1

        try:
            LOCK_FILE.touch()
            logger.info("=" * 62)
            logger.info(f"🚀 VeilleurIA v2.2 — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            logger.info(f"   Modèle : {self.synthesis_model} | Thinking : {self.use_thinking}")
            logger.info("=" * 62)

            # ── ÉTAPE 1 : Collecte RSS ─────────────────────────────────────
            logger.info("📡 [1/6] Collecte RSS...")
            entries_agentique = self.collect_rss_entries(RSS_SOURCES_AGENTIQUE)
            entries_openclaw  = self.collect_rss_entries(RSS_SOURCES_OPENCLAW)

            # ── ÉTAPE 2 : Résumé brut Haiku ───────────────────────────────
            logger.info("⚡ [2/6] Résumé RSS via Haiku...")
            rss_agentique = self.summarize_rss_with_haiku(entries_agentique, "agentique")
            rss_openclaw  = self.summarize_rss_with_haiku(entries_openclaw, "openclaw")

            # ── ÉTAPE 3 : Recherche web 9 requêtes ────────────────────────
            logger.info("🔍 [3/6] Recherche web via Sonnet 4.6 (9 requêtes)...")
            web_agentique = self.search_with_sonnet(SEARCH_QUERIES_AGENTIQUE, "agentique")
            web_openclaw  = self.search_with_sonnet(SEARCH_QUERIES_OPENCLAW, "openclaw")

            # ── ÉTAPE 4 : Passe critique Haiku (NOUVEAU v2.1) ─────────────
            logger.info("🎯 [4/6] Passe critique Haiku (filtre top 5)...")
            filtered_agentique = self.critical_filter_with_haiku(
                rss_agentique, web_agentique, "agentique"
            )
            filtered_openclaw = self.critical_filter_with_haiku(
                rss_openclaw, web_openclaw, "openclaw"
            )

            # ── ÉTAPE 5 : Feedback + Synthèse Extended Thinking ───────────
            logger.info("💾 [5/6] Chargement feedback...")
            feedback_context = self.load_feedback_context()

            logger.info(f"✍️  [5/6] Synthèse Sonnet 4.6 + Extended Thinking...")
            report = self.generate_final_report(
                filtered_agentique=filtered_agentique,
                filtered_openclaw=filtered_openclaw,
                feedback_context=feedback_context,
            )

            # ── ÉTAPE 6 : Envoi / affichage ───────────────────────────────
            logger.info("📤 [6/6] Envoi rapport...")
            if self.dry_run:
                print("\n" + "=" * 62)
                print("📋 RAPPORT v2.1 (dry-run — pas d'envoi Telegram) :")
                print("=" * 62)
                print(report)
                print("=" * 62)
            else:
                import asyncio
                success = asyncio.run(self.send_telegram(report))
                if not success:
                    logger.error("❌ Échec envoi Telegram")
                    return 1

            # Archivage local
            report_path = Path(f"rapports/rapport_{datetime.now().strftime('%Y%m%d')}.md")
            report_path.parent.mkdir(exist_ok=True)
            report_path.write_text(report, encoding="utf-8")
            logger.info(f"  💾 Rapport archivé : {report_path}")

            logger.info("✅ Pipeline VeilleurIA v2.2 terminé avec succès")
            return 0

        except Exception as e:
            logger.error(f"❌ Erreur pipeline : {e}", exc_info=True)
            return 1

        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()


# ─── Point d'entrée CLI ───────────────────────────────────────────────────────

def main() -> int:
    """Point d'entrée principal avec interface CLI."""
    parser = argparse.ArgumentParser(
        description="VeilleurIA v2.1 — Sonnet 4.6 + Extended Thinking + Passe critique",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
    python agent_veilleur_ia_v2_1.py                         # Production
    python agent_veilleur_ia_v2_1.py --test                  # Haiku partout, thinking off
    python agent_veilleur_ia_v2_1.py --dry-run               # Rapport sans Telegram
    python agent_veilleur_ia_v2_1.py --feedback like "Super insight OpenClaw"
    python agent_veilleur_ia_v2_1.py --feedback dislike "Trop de répétitions sur LangGraph"
    python agent_veilleur_ia_v2_1.py --feedback note "Ajouter section coûts API hebdo"
        """,
    )
    parser.add_argument("--test",     action="store_true", help="Mode test : Haiku partout, Extended Thinking désactivé")
    parser.add_argument("--dry-run",  action="store_true", help="Génère le rapport sans l'envoyer sur Telegram")
    parser.add_argument(
        "--feedback",
        nargs=2,
        metavar=("TYPE", "NOTE"),
        help="Enregistre feedback : --feedback like|dislike|note 'texte'",
    )

    args = parser.parse_args()

    if args.feedback:
        fb_type, fb_note = args.feedback
        if fb_type not in ("like", "dislike", "note"):
            print(f"❌ Type invalide : {fb_type}. Utiliser like / dislike / note")
            return 1
        agent = VeilleurIA(test_mode=True, dry_run=True)
        agent.save_feedback(fb_type, fb_note)
        print(f"✅ Feedback '{fb_type}' enregistré : {fb_note}")
        return 0

    agent = VeilleurIA(test_mode=args.test, dry_run=args.dry_run)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
