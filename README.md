# 🤖 VeilleurIA v2.3

> **Agent de veille IA agentique quotidienne** — Sonnet 4.6 + Extended Thinking + Hub Notion

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6-D97706?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)
[![Notion](https://img.shields.io/badge/Notion-Hub_Central-000000?style=flat-square&logo=notion&logoColor=white)](https://notion.so)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)](LICENSE)

---

## ✦ Ce que fait VeilleurIA

Chaque soir à 20h, VeilleurIA génère automatiquement un **rapport de veille dense de 6000-7000 mots** sur l'IA agentique, structuré en 3 parties :

| Partie | Contenu |
|--------|---------|
| 🧠 **Agentique Générale** | Frameworks, releases, papers ArXiv, CVE sécurité |
| 🦞 **OpenClaw** | Releases, workflows communautaires, AgentSkills |
| 🛠️ **Skills Claude** | MCP, nouveaux outils, bonnes pratiques production |

Chaque partie comprend **4 sections** : `📰 Info` · `🎓 Pédagogie` · `⚙️ Système` · `🔗 Mise en place`

Le rapport est publié automatiquement dans **4 bases Notion dédiées**, et une notification Telegram avec lien direct est envoyée.

---

## ✦ Architecture

```
Cron 19h45 (KVM1 Hostinger — 24h/24)
    │
    ├─ [1/7] Collecte RSS      → Haiku 4.5    (10 sources + 3 Reddit)
    ├─ [2/7] Résumé brut       → Haiku 4.5    (3 parties × résumé)
    ├─ [3/7] Recherche web     → Sonnet 4.6   (12 requêtes ciblées)
    ├─ [4/7] Passe critique    → Haiku 4.5    (filtre top 5 par partie)
    ├─ [5/7] Synthèse rapport  → Sonnet 4.6   (+ Extended Thinking 3000 tokens)
    ├─ [6/7] Redistribution    → Haiku 4.5    (extrait → 4 bases Notion)
    └─ [7/7] Notification      → Telegram     (lien Notion direct)
```

**Principe clé** : Sonnet génère **une seule fois**. Haiku redistribue. Zéro doublon de coût.

---

## ✦ Hub Notion — 4 bases automatiques

```
📅 Rapports quotidiens   → 1 page complète par jour (archivage)
🎓 Base Pédagogie        → 1 concept/jour, code coloré, analogies terrain
⚙️  Base Système          → 1 snippet production-ready/jour, intégrable directement
🔗 Mise en place         → 1 action concrète/jour, actionnables le lendemain
```

Dans 6 mois : **180 concepts** · **180 snippets** · **180 actions** — une base de connaissances IA agentique unique.

---

## ✦ Sources

**Blogs & Publications**
- Anthropic Blog · LangChain Blog · Hugging Face Papers
- The Rundown AI · Latent Space

**Reddit (RSS natif, sans API)**
- r/LocalLLaMA · r/AIAgents · r/MachineLearning · r/ClaudeAI

**OpenClaw**
- GitHub Releases · Discussions communautaires

**Web Search** (12 requêtes quotidiennes via Sonnet 4.6)
- ArXiv papers agentique · benchmarks modèles · CVE sécurité · releases frameworks

---

## ✦ Stack technique

| Composant | Technologie |
|-----------|-------------|
| LLM Synthèse | Claude Sonnet 4.6 + Extended Thinking |
| LLM Collecte | Claude Haiku 4.5 |
| RSS | feedparser (10 sources + Reddit sans API) |
| Hub | Notion API (notion-client) |
| Notification | python-telegram-bot |
| Robustesse | tenacity (retry automatique) |
| Déploiement | Cron · VPS Linux (Hostinger KVM1) |

---

## ✦ Coût de fonctionnement

| Mode | Usage | Coût/jour | Coût/mois |
|------|-------|-----------|-----------|
| `--test` | Haiku partout, validation rapide | ~$0.01 | ~$0.30 |
| `--dry-run` | Rapport terminal, pas Notion | ~$0.35 | — |
| **Production** | Pipeline complet automatique | **~$0.35** | **~$10.50** |

---

## ✦ Installation

### Prérequis
- Python 3.11+
- Compte Anthropic (clé API)
- Bot Telegram (via @BotFather)
- Workspace Notion + intégration créée

### Déploiement local (test)

```bash
# 1. Cloner le repo
git clone https://github.com/VladimirB-prog/veilleur-ia.git
cd veilleur-ia

# 2. Créer un venv dédié (isolé de tes autres projets)
python3 -m venv venv-veilleur
source venv-veilleur/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
nano .env   # Remplir les vraies valeurs

# 5. Valider sans dépenser de tokens
python agent_veilleur_ia_v2_3.py --dry-run

# 6. Valider avec envoi Telegram réel (Haiku partout, ~$0.01)
python agent_veilleur_ia_v2_3.py --test
```

### Déploiement production (VPS Linux)

```bash
# Sur ton VPS (SSH)
git clone https://github.com/VladimirB-prog/veilleur-ia.git
cd veilleur-ia
python3 -m venv venv-veilleur
source venv-veilleur/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env

# Poser le cron — rapport à 20h chaque soir
crontab -e
# Ajouter :
# 45 19 * * * /root/veilleur-ia/venv-veilleur/bin/python /root/veilleur-ia/agent_veilleur_ia_v2_3.py >> /root/veilleur-ia/veilleur_ia_cron.log 2>&1
```

---

## ✦ Configuration Notion

1. Créer une intégration : [notion.so/my-integrations](https://www.notion.so/my-integrations) → New integration → copier le token
2. Créer 4 bases de données dans Notion (voir `.env.example` pour les propriétés)
3. Dans chaque base → "..." → "Add connections" → sélectionner ton intégration
4. Copier les IDs de chaque base (URL → 32 derniers caractères) dans `.env`

---

## ✦ Commandes disponibles

```bash
# Production complète
python agent_veilleur_ia_v2_3.py

# Mode test — Haiku partout, rapide, ~$0.01
python agent_veilleur_ia_v2_3.py --test

# Mode dry-run — rapport terminal, pas Notion/Telegram
python agent_veilleur_ia_v2_3.py --dry-run

# Feedback — amélioration continue du rapport
python agent_veilleur_ia_v2_3.py --feedback like "Super section Skills Claude"
python agent_veilleur_ia_v2_3.py --feedback dislike "Trop générique sur LangChain"
python agent_veilleur_ia_v2_3.py --feedback note "Ajouter focus sur MCP tools"
```

Le feedback est stocké dans `feedback_history.json` et injecté dans le prompt sur une fenêtre glissante de 14 jours.

---

## ✦ Structure du repo

```
veilleur-ia/
├── agent_veilleur_ia_v2_3.py   # Script principal (910 lignes)
├── requirements.txt             # Dépendances Python
├── .env.example                 # Template variables (commenté)
├── .gitignore                   # Protège .env et données sensibles
├── README.md                    # Ce fichier
├── rapports/                    # Archivage local (.gitignore)
└── feedback_history.json        # Généré automatiquement (.gitignore)
```

---

## ✦ Roadmap

- [x] v2.0 — Architecture de base RSS + Telegram
- [x] v2.1 — Extended Thinking + 9 requêtes web + passe critique Haiku
- [x] v2.2 — Rapport 6000-7000 mots + prompt éditorial structuré
- [x] v2.3 — Hub Notion + Reddit RSS + Partie 3 Skills Claude
- [ ] v2.4 — Batch API Anthropic (~50% réduction coût)
- [ ] v2.5 — Bot Telegram interactif (`/like`, `/dislike` sans CLI)
- [ ] v2.6 — Dashboard visualisation qualité rapports

---

## ✦ Auteur

**Vlad B.** — Conducteur de travaux TP en reconversion ingénieur IA agentique

Projet construit dans le cadre d'une reconversion professionnelle vers l'ingénierie IA.
L'expertise terrain BTP (rigueur, gestion de projet, documentation technique) appliquée
à la construction de systèmes IA production-ready.

[![GitHub](https://img.shields.io/badge/GitHub-VladimirB--prog-181717?style=flat-square&logo=github)](https://github.com/VladimirB-prog)

---

*VeilleurIA v2.3 — Projet Agentic IA 2026 | Claude Sonnet 4.6 + Extended Thinking*
