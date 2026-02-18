# VeilleurIA v2.0 — Guide de Déploiement
**Skill Claude natif | Sonnet 4.6 | Veille IA agentique quotidienne**

---

## 🎯 Ce que fait ce skill

Chaque soir à 20h, VeilleurIA te dépose sur Telegram un rapport de veille structuré en deux parties :
- **Agentique générale** : frameworks, releases, nouveaux patterns
- **OpenClaw** : releases GitHub, discussions communautaires, hacks et workflows

Chaque partie couvre : Information → Pédagogie → Système

**Stack technique :**
```
Cron 19h45 → Python script (GitHub)
    ├─ feedparser → collecte RSS 24h
    ├─ Haiku → résumé brut (coût minimal)
    ├─ Sonnet 4.6 + web_search → recherche ciblée (6 requêtes)
    ├─ Sonnet 4.6 → synthèse rapport final
    └─ Telegram Bot → push 20h00
```

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

### Étape 2 — Environnement virtuel

```bash
python3 -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

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
# Test complet sans Telegram (dry-run)
python agent_veilleur_ia_v2.py --dry-run

# Test avec Haiku partout (10x moins cher, validé l'envoi Telegram)
python agent_veilleur_ia_v2.py --test
```

Si le rapport s'affiche correctement → tout fonctionne.

### Étape 5 — Cron Mac Mini M4

```bash
# Éditer la crontab
crontab -e

# Ajouter cette ligne (19h45 chaque jour)
45 19 * * * /chemin/vers/venv/bin/python /chemin/vers/agent_veilleur_ia_v2.py >> /tmp/veilleur_ia_cron.log 2>&1
```

**Vérifier le chemin Python :**
```bash
which python3  # Utiliser ce chemin dans le cron
```

---

## 💬 Commandes de feedback

Après chaque rapport, tu peux entraîner l'agent via CLI :

```bash
# Approuver un aspect du rapport
python agent_veilleur_ia_v2.py --feedback like "Excellent focus sur les releases GitHub OpenClaw"

# Signaler ce qui ne convient pas
python agent_veilleur_ia_v2.py --feedback dislike "Trop générique sur LangChain, pas assez concret"

# Note libre pour orienter les prochains rapports
python agent_veilleur_ia_v2.py --feedback note "Ajouter une section sur les coûts API comparés"
```

Le feedback est stocké dans `feedback_history.json` et injecté dans le prompt de synthèse sur une fenêtre glissante de 14 jours. L'agent ajuste automatiquement son rapport sans que tu touches au code.

---

## 💰 Estimation des coûts

| Composant | Modèle | Tokens/jour | Coût/jour |
|---|---|---|---|
| Résumé RSS agentique | Haiku | ~2 000 | ~$0.0003 |
| Résumé RSS OpenClaw | Haiku | ~1 500 | ~$0.0002 |
| Recherche web agentique | Sonnet 4.6 | ~8 000 | ~$0.06 |
| Recherche web OpenClaw | Sonnet 4.6 | ~6 000 | ~$0.05 |
| Synthèse rapport final | Sonnet 4.6 | ~5 000 | ~$0.04 |
| **TOTAL** | | **~22 500** | **~$0.15/jour** |

**Soit ~$4.50/mois** pour un rapport quotidien complet. Comparable à un café.

En mode `--test` (Haiku partout) : ~$0.01/jour pour les phases de développement.

---

## 📁 Structure du repo GitHub

```
veilleur-ia/
├── agent_veilleur_ia_v2.py      # Script principal
├── requirements.txt              # Dépendances
├── .env.example                  # Template variables d'environnement
├── .gitignore                    # JAMAIS commiter .env ou feedback_history.json
├── README.md                     # Ce guide
├── rapports/                     # Archivage automatique des rapports
│   ├── rapport_20260217.md
│   └── ...
└── feedback_history.json         # Généré automatiquement (dans .gitignore)
```

**Contenu .gitignore minimal :**
```
.env
feedback_history.json
venv/
__pycache__/
*.log
rapports/
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

## 📈 Évolutions prévues (V2.1+)

- Bot Telegram interactif pour `/like`, `/dislike` directement dans le chat
- Ajout sources Reddit (r/LocalLLaMA, r/MachineLearning) via API Reddit
- Résumé hebdomadaire consolidé le dimanche soir
- Agent "FormationBot" qui transforme le rapport en exercice Python du jour

---

*VeilleurIA v2.0 — Projet Agentic IA SRC 2026 | Sonnet 4.6 native skill*
