# Atlas Terminal

Mini terminal financier façon terminal de marché (fond noir, texte ambre) : marchés US et Europe,
fondamentaux SEC, risque, news avec sentiment FinBERT, macro US et zone euro.
**Uniquement des données réelles** ; si une source échoue, le panneau affiche « DONNÉES INDISPONIBLES »
avec l'erreur et l'heure de la dernière mise à jour réussie.

## Comment ça marche

```
GitHub Actions (toutes les 15 min en semaine)
   └─ python -m pipeline.run   → décide quoi mettre à jour selon l'heure (pipeline/schedule.py)
        ├─ Yahoo Finance (yfinance)     prix différés, historique 5 ans
        ├─ Google News RSS + Yahoo      titres, notés par FinBERT (ProsusAI/finbert, CPU)
        ├─ SEC EDGAR                    fondamentaux, dépôts
        └─ FRED + BCE                   taux, inflation, chômage
   └─ écrit des fichiers JSON dans site/data/  → sauvegardés sur la branche "data"
   └─ publie site/ sur GitHub Pages
Le site (HTML/JS statique) ne lit que ces fichiers JSON.
```

Planning (heure de Paris, jours ouvrés) :

| Quand | Quoi |
|---|---|
| 08:30 | Gros chargement : historiques, risque, SEC, FRED/BCE, news, contrôle croisé |
| 09:00 → 17:30 | Cotations Europe toutes les 15 min |
| ouverture NYSE → 18:30 | Cotations US toutes les 15 min (calculé en heure de New York) |
| 17:40 | Clôture Europe : historiques + risque |
| 09:00 → 18:30 | News + sentiment toutes les heures |

## Mise en route (une seule fois)

1. **Settings → Secrets and variables → Actions → New repository secret** :
   `SEC_CONTACT_EMAIL` = ton email (exigé par la SEC dans l'en-tête des requêtes).
2. **Settings → Pages → Source : GitHub Actions**.
3. **Actions → Update data and deploy → Run workflow** pour le premier chargement complet.

## Tests

```
pip install -r requirements.txt
python -m pytest -q                 # métriques, SEC, planning, parsing, gestion des pannes
node --test tests/js/site.test.js   # traductions FR/EN, corrélation, barre de commande
```

Le contrôle croisé (dernier cours et volatilité 1 an d'AAPL et MC.PA recalculés indépendamment)
tourne à chaque chargement quotidien ; son résultat est affiché dans l'onglet RISK.

## Phases

- [x] Phase 1 : MKTS, QUOTE, FA, RISK, NEWS, ECO, roue crantée FR/EN, actions européennes
- [ ] Phase 2 : DEALS, COMPS
- [ ] Phase 3 : DCF, HELP détaillé
