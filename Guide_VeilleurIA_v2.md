# VeilleurIA v2.2 — Guide de Référence
**Skill Claude natif | Sonnet 4.6 + Extended Thinking | Veille IA agentique quotidienne**

---

## 🎯 Ce que fait ce skill

Chaque soir à 20h, VeilleurIA te dépose sur Telegram un rapport de veille dense de **4000-5000 mots** structuré en deux parties :
- **Agentique générale** : frameworks, releases, nouveaux patterns
- **OpenClaw** : releases GitHub, discussions communautaires, hacks et workflows

Chaque partie couvre : Information → Pédagogie (avec analogie BTP + code) → Système (production-ready)

**Stack technique v2.2 :**
```
Cron 19h45 → Python script (GitHub) → KVM1 Hostinger (24h/24)
    ├─ feedparser       → collecte RSS 24h (7 sources)
    ├─ Haiku 4.5        → résumé brut RSS (coût minimal)
    ├─ Sonnet 4.6       → recherche web ciblée (9 requêtes + web_search natif)
    ├─ Haiku 4.5        → passe critique (filtre top 5 par partie)
    ├─ Sonnet 4.6       → synthèse finale + Extended Thinking (3000 tokens)
    └─ Telegram Bot     → push 20h00 (4-5 messages découpés auto)
```

**3 leviers qualité Sonnet 4.6 :**
- **Extended Thinking** : Sonnet réfléchit avant de rédiger → rapport plus dense, moins de redondances
- **9 requêtes web_search** : couverture ArXiv papers, benchmarks, CVE sécurité (vs 6 en v2.1)
- **Passe critique Haiku** : filtre top 5 infos avant synthèse → zéro dilution

---

## 📦 Prérequis

- Python 3.11+
- Un compte Telegram et un bot créé (via @BotFather)
- Une clé API Anthropic active

---

## 🚀 Installation (15 minutes)

### Étape 1 — Cloner le repo

```bash
git clone https://github.com/[ton-username]/veilleur-ia.git
cd veilleur-ia
```

### Étape 2 — Environnement virtuel dédié

```bash
# venv DÉDIÉ — ne pas réutiliser celui de ta stack d'agents de code
python3 -m venv venv-veilleur
source venv-veilleur/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

Tu dois voir `(venv-veilleur)` dans ton prompt → environnement actif.

> ⚠️ Un venv par projet = isolation totale. Si une dépendance casse,
> seul VeilleurIA est affecté, pas ta stack d'agents.

**requirements.txt :**
```
anthropic>=0.50.0
feedparser>=6.0.0
python-telegram-bot>=22.0
python-dotenv>=1.0.0
tenacity>=9.0.0
```

### Étape 3 — Configuration .env

Créer le fichier `.env` à la racine (jamais commité) :

```bash
# API Anthropic — https://console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx

# Telegram Bot
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=-100123456789   # ID du groupe ou channel

# Optionnel — personnalisation
VEILLE_HOUR=20                   # Heure de push (défaut : 20)
LOG_LEVEL=INFO
```

**Obtenir ton TELEGRAM_CHAT_ID :**
```
1. Créer un bot via @BotFather → copier le token
2. Ajouter le bot dans ton groupe/channel
3. Envoyer un message dans le groupe
4. Appeler : https://api.telegram.org/bot[TOKEN]/getUpdates
5. Trouver "chat.id" dans la réponse JSON
```

### Étape 4 — Premier test

```bash
# Test complet sans Telegram (dry-run) — rapport affiché dans le terminal
python agent_veilleur_ia_v2_2.py --dry-run

# Test avec Haiku partout + envoi Telegram réel (validation chaîne complète)
python agent_veilleur_ia_v2_2.py --test
```

Si un rapport de 4000-5000 mots s'affiche → tout fonctionne. Passe à la Phase 2 (KVM1).

### Étape 5 — Cron KVM1 Hostinger (prod 24h/24)

```bash
crontab -e

# Ajouter cette ligne
45 19 * * * /root/veilleur-ia/venv-veilleur/bin/python /root/veilleur-ia/agent_veilleur_ia_v2_2.py >> /root/veilleur-ia/veilleur_ia_cron.log 2>&1
```

> 📖 Pour le déploiement complet MacBook → KVM1, voir **Guide_Deploy_VeilleurIA_v2_2.md**

---

## 💬 Commandes de feedback

Après chaque rapport, tu peux entraîner l'agent via CLI :

```bash
# Approuver un aspect du rapport
python agent_veilleur_ia_v2_2.py --feedback like "Excellent focus sur les releases GitHub OpenClaw"

# Signaler ce qui ne convient pas
python agent_veilleur_ia_v2_2.py --feedback dislike "Trop générique sur LangChain, pas assez concret"

# Note libre pour orienter les prochains rapports
python agent_veilleur_ia_v2_2.py --feedback note "Ajouter une section sur les coûts API comparés"
```

Le feedback est stocké dans `feedback_history.json` et injecté dans le prompt de synthèse sur une fenêtre glissante de 14 jours. L'agent ajuste automatiquement son rapport sans que tu touches au code.

---

## 💰 Estimation des coûts v2.2

**Tarifs officiels Anthropic (février 2026) :**
- Haiku 4.5 : $1 / $5 par million tokens (input / output)
- Sonnet 4.6 : $3 / $15 par million tokens (input / output)
- Extended Thinking : facturé au tarif **output** (pas une catégorie séparée)

| Étape | Modèle | Tokens/jour | Coût/jour |
|---|---|---|---|
| Résumé RSS x2 (agentique + OpenClaw) | Haiku 4.5 | ~8 200 | ~$0.013 |
| Passe critique x2 (filtre top 5) | Haiku 4.5 | ~11 000 | ~$0.015 |
| Recherche web 9 requêtes x2 | Sonnet 4.6 | ~14 000 | ~$0.108 |
| Extended Thinking (3 000 tokens budget) | Sonnet 4.6 | ~3 000 | ~$0.045 |
| Synthèse rapport final (~5 000 mots) | Sonnet 4.6 | ~6 000 | ~$0.040 |
| **TOTAL** | | **~42 200** | **~$0.28/jour** |

**Soit ~$8.50/mois** — deux cafés pour un cours quotidien dense sur l'IA agentique la plus récente.

| Mode | Usage | Coût/jour | Coût/mois |
|---|---|---|---|
| `--test` (Haiku partout, thinking off) | Développement / validation | ~$0.01 | ~$0.30 |
| `--dry-run` (Sonnet 4.6, pas Telegram) | Vérification qualité rapport | ~$0.28 | — |
| Production (cron 19h45) | Rapport quotidien complet | ~$0.28 | **~$8.50** |

> 💡 **Optimisation future v2.3** : activer le Batch API Anthropic (50% de réduction)
> → descendre à ~$4.25/mois. Le pipeline tourne en asynchrone, rapport prêt à 20h quand même.

---

## 📁 Structure du repo GitHub

```
veilleur-ia/
├── agent_veilleur_ia_v2_2.py    # Script principal v2.2 (839 lignes)
├── requirements.txt              # Dépendances Python
├── .env.example                  # Template variables d'environnement
├── .gitignore                    # JAMAIS commiter .env ou feedback_history.json
├── Guide_VeilleurIA_v2.md        # Ce guide
├── Guide_Deploy_VeilleurIA_v2_2.md # Guide déploiement MacBook → KVM1
├── rapports/                     # Archivage automatique des rapports (.gitignore)
│   ├── rapport_20260217.md
│   └── ...
└── feedback_history.json         # Généré automatiquement (.gitignore)
```

**Contenu .gitignore :**
```
.env
feedback_history.json
venv-veilleur/
__pycache__/
*.pyc
*.log
rapports/
.DS_Store
```

---

## 🔧 Troubleshooting

**"Variables manquantes dans .env"**
→ Vérifier que le fichier `.env` est dans le même dossier que le script et que les variables sont correctement nommées.

**"Erreur RSS [source]"**
→ Certaines sources RSS peuvent être temporairement indisponibles. L'agent continue avec les autres — log en WARNING, pas en ERROR.

**"Erreur envoi Telegram"**
→ Vérifier que le bot est bien admin du channel/groupe et que le CHAT_ID est correct (format : `-100XXXXXXXXXX` pour les channels).

**"Lock file présent"**
→ Supprimer manuellement `/tmp/veilleur_ia.lock` si le script précédent a planté.

**Rapport trop long / coupé sur Telegram**
→ Normal si > 4000 caractères : le script découpe automatiquement en plusieurs messages numérotés.

---

## 📈 Évolutions prévues

**V2.3 (prochaine)**
- Batch API Anthropic → 50% de réduction → ~$4.25/mois
- Bot Telegram interactif : `/like`, `/dislike` directement dans le chat (sans CLI)
- Ajout sources Reddit (r/LocalLLaMA, r/MachineLearning) via API Reddit

**V2.4+**
- Résumé hebdomadaire consolidé le dimanche soir
- Agent "FormationBot" : transforme le rapport en exercice Python du jour
- Dashboard de suivi des feedbacks et de la qualité des rapports

---

*VeilleurIA v2.2 — Projet Agentic IA SRC 2026 | Sonnet 4.6 + Extended Thinking + Passe critique*
