# Forecast de consommation electrique - infrastructure base de donnees

Ce projet vise a prevoir la consommation d'electricite en France, puis a afficher les resultats dans un dashboard Streamlit pour le trading de l'electricite.

Cette etape met uniquement en place la base PostgreSQL locale avec Docker. Aucun script d'ingestion automatique, aucune API et aucun cron job ne sont encore branches a la base.

## 1. Fichiers ajoutes

- `docker-compose.yml` lance PostgreSQL dans un conteneur Docker.
- `database/init/01_schema.sql` cree les tables de depart.
- `.env.example` montre les variables de configuration a utiliser.

## 2. Demarrer PostgreSQL

Copier le fichier d'exemple de configuration :

```powershell
Copy-Item .env.example .env
```

Lancer la base :

```powershell
docker compose up -d
```

Verifier que le conteneur tourne :

```powershell
docker ps
```

## 3. Connexion a la base

Parametres par defaut :

- Host : `localhost`
- Port : `5432`
- Database : `trading_data`
- User : `dev_user`
- Password : `my_strong_password`

Avec `psql`, la connexion ressemble a ceci :

```powershell
psql -h localhost -p 5432 -U dev_user -d trading_data
```

## 4. Tables creees

### `historical_data`

Cette table stockera les donnees historiques de consommation.

| Colonne | Type | Role |
| --- | --- | --- |
| `id` | `BIGSERIAL` | Identifiant unique cree automatiquement |
| `timestamp` | `TIMESTAMPTZ` | Date et heure de la mesure |
| `value` | `DOUBLE PRECISION` | Valeur mesuree, par exemple la consommation en MW |
| `source` | `TEXT` | Source de la donnee, par exemple `RTE` |
| `import_date` | `TIMESTAMPTZ` | Date d'import dans la base |

### `predictions`

Cette table stockera les previsions produites par les modeles.

| Colonne | Type | Role |
| --- | --- | --- |
| `id` | `BIGSERIAL` | Identifiant unique cree automatiquement |
| `timestamp` | `TIMESTAMPTZ` | Date et heure prevue |
| `predicted_value` | `DOUBLE PRECISION` | Valeur predite |
| `model_name` | `TEXT` | Nom ou version du modele |
| `horizon` | `TEXT` | Horizon de prediction, par exemple `D+1` ou `H+6` |
| `prediction_date` | `TIMESTAMPTZ` | Date de generation de la prediction |

## 5. Pourquoi `TIMESTAMPTZ` ?

Les donnees RTE contiennent des dates avec fuseau horaire. `TIMESTAMPTZ` permet a PostgreSQL de gerer correctement ces dates, ce qui est important pour les series temporelles.

## 6. Arreter la base

Arreter le conteneur sans supprimer les donnees :

```powershell
docker compose down
```

Supprimer aussi les donnees stockees dans le volume Docker :

```powershell
docker compose down -v
```

Attention : `docker compose down -v` efface le volume `pg_data`, donc les donnees PostgreSQL locales.

## 7. Diagnostic Docker sur Windows

Si `docker compose up -d` affiche `Docker Desktop is unable to start`, verifier d'abord WSL :

```powershell
wsl -l -v
```

Sur cette machine, le diagnostic actuel indique qu'aucune distribution Linux WSL n'est installee. Docker Desktop utilise generalement WSL 2 comme backend Linux ; il faut donc installer une distribution, par exemple Ubuntu, puis relancer Docker Desktop.

## 8. Ingestion automatique des donnees RTE

Le script `scripts/ingest_rte_consumption.py` recupere les donnees recentes de consommation RTE, les nettoie, les transforme en valeurs horaires, puis les insere dans PostgreSQL.

### Configuration

Completer le fichier `.env` avec vos identifiants RTE :

```env
RTE_CLIENT_ID=your_rte_client_id
RTE_CLIENT_SECRET=your_rte_client_secret
```

Les identifiants ne doivent pas etre ecrits directement dans les scripts Python.

### Installer les dependances Python

```powershell
py -m pip install -r requirements.txt
```

Sur Windows, `py` est le lanceur Python. Il evite souvent les problemes de `PATH` avec les commandes `python` ou `pip`.

### Tester sans inserer en base

Le mode `--dry-run` permet de verifier la recuperation et le nettoyage sans modifier PostgreSQL :

```powershell
py scripts/ingest_rte_consumption.py --hours 24 --dry-run
```

Avec `--hours 24`, le script prend les 24 dernieres heures completes. Par exemple, s'il est lance a `00:00:39`, il interroge RTE de `00:00:00` a `00:00:00`, sans secondes ni microsecondes parasites dans l'URL.

### Inserer les donnees dans PostgreSQL

```powershell
py scripts/ingest_rte_consumption.py --hours 24
```

Pour une periode precise :

```powershell
py scripts/ingest_rte_consumption.py --start-date "2024-10-01T00:00:00+02:00" --end-date "2024-10-02T00:00:00+02:00"
```

Le script utilise `ON CONFLICT (timestamp, source)` pour eviter les doublons. Si une mesure existe deja pour la meme heure et la meme source, la valeur est mise a jour au lieu de creer une deuxieme ligne.

### Logs

Les logs sont ecrits dans :

```text
logs/ingestion.log
```

Ce fichier permet de verifier le nombre de points recuperes, le nombre de lignes nettoyees et les erreurs eventuelles.

### Planification avec cron sur Linux

Sur un serveur Linux, ouvrir la crontab :

```bash
crontab -e
```

Ajouter par exemple :

```cron
30 23 * * * cd /home/user/projet && /usr/bin/python3 scripts/ingest_rte_consumption.py --hours 24 >> logs/cron_fetch.log 2>&1
```

Cette ligne execute l'ingestion tous les jours a 23h30.

### Planification sur Windows

Sur Windows, l'equivalent de cron est le Planificateur de taches. Il faut creer une tache qui lance :

```powershell
py H:\STAGES\Projet Energy Data\Projet_Final_ML_ALL\scripts\ingest_rte_consumption.py --hours 24
```

avec le dossier de demarrage :

```text
H:\STAGES\Projet Energy Data\Projet_Final_ML_ALL
```

## 9. API FastAPI pour servir le modele Chronos

Cette etape transforme le modele Chronos en service HTTP local. Le dashboard Streamlit pourra appeler cette API pour demander des predictions.

Architecture locale :

```text
Streamlit
   |
   v
FastAPI /predict
   |
   v
Modele Chronos charge en memoire
   |
   v
Reponse JSON avec les predictions
```

La base PostgreSQL reste le stockage central :

```text
historical_data -> contexte recent -> FastAPI -> predictions -> PostgreSQL
```

### Configuration du modele

Variables optionnelles dans `.env` :

```env
CHRONOS_MODEL_NAME=amazon/chronos-t5-small
CHRONOS_DEVICE_MAP=cpu
```

Avec `cpu`, le modele tourne sans GPU. Le premier lancement peut etre long, car les poids du modele doivent etre telecharges et mis en cache localement.

### Lancer l'API

Dans un premier terminal :

```powershell
py -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

La documentation interactive est ensuite disponible ici :

```text
http://localhost:8000/docs
```

### Verifier que l'API est active

Ouvrir dans le navigateur :

```text
http://localhost:8000/health
```

La reponse doit indiquer que le modele est charge.

### Tester une prediction depuis le CSV

Dans un deuxieme terminal :

```powershell
py scripts/test_prediction_api.py --context-length 168 --prediction-length 24
```

Ce script lit les dernieres valeurs de `consumption_data_avg_hourly.csv`, appelle `/predict`, puis affiche la reponse JSON.

### Endpoint `/predict`

Exemple de corps JSON :

```json
{
  "context": [52000, 51500, 50800, 50100],
  "prediction_length": 24,
  "quantiles": [0.1, 0.5, 0.9]
}
```

La reponse contient une liste de predictions :

```json
{
  "model_name": "amazon/chronos-t5-small",
  "prediction_length": 24,
  "context_length": 168,
  "predictions": [
    {
      "step": 1,
      "predicted_value": 51000.0,
      "quantiles": {
        "q10": 49000.0,
        "q50": 51000.0,
        "q90": 53000.0
      }
    }
  ]
}
```

### Automatiser les predictions en base

Le script `scripts/run_prediction_batch.py` lit les dernieres donnees de `historical_data`, appelle l'API FastAPI, puis insere le resultat dans la table `predictions`.

L'API doit deja etre lancee dans un terminal.

Test sans insertion :

```powershell
py scripts/run_prediction_batch.py --context-length 168 --prediction-length 24 --dry-run
```

Insertion reelle :

```powershell
py scripts/run_prediction_batch.py --context-length 168 --prediction-length 24
```

Le script utilise une contrainte unique sur `(timestamp, model_name, horizon)`. Si la meme prediction est relancee, la ligne existante est mise a jour au lieu d'etre dupliquee.

Verifier les predictions stockees :

```powershell
docker exec trading_pg_db psql -U dev_user -d trading_data -c "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM predictions;"
```

Voir les premieres predictions :

```powershell
docker exec trading_pg_db psql -U dev_user -d trading_data -c "SELECT timestamp, predicted_value, model_name, horizon, prediction_date FROM predictions ORDER BY timestamp LIMIT 10;"
```

Ce script est celui que l'on pourra ensuite lancer automatiquement avec le Planificateur de taches Windows ou avec cron sur un serveur Linux.

## 10. Dashboard Streamlit

Dans cette version du projet, Streamlit remplace le couple React + Express.

Architecture retenue :

```text
Streamlit Dashboard
   |
   | lit directement
   v
PostgreSQL

Streamlit Dashboard
   |
   | appelle si l'utilisateur clique sur "Generer et stocker"
   v
FastAPI /predict
   |
   v
Modele Chronos
```

Donc :

- pas d'API Express ;
- pas de React ;
- pas de Chart.js ;
- les graphiques sont faits avec Plotly ;
- Streamlit sert a la fois d'interface utilisateur et de couche de lecture PostgreSQL.

### Lancer le dashboard

Verifier que PostgreSQL tourne :

```powershell
docker ps
```

Installer les dependances si necessaire :

```powershell
py -m pip install -r requirements.txt
```

Lancer Streamlit :

```powershell
py -m streamlit run dashboard/app.py
```

Streamlit ouvrira normalement le navigateur automatiquement. Sinon, ouvrir l'URL affichee dans le terminal, souvent :

```text
http://localhost:8501
```

### Fonctionnalites disponibles

Le dashboard permet de :

- choisir une periode de visualisation ;
- afficher la consommation reelle depuis `historical_data` ;
- afficher les predictions depuis `predictions` ;
- comparer les courbes reelles et predites ;
- consulter les tables dans des onglets ;
- generer une nouvelle prediction en appelant FastAPI.

### Generer une prediction depuis le dashboard

Pour utiliser le bouton de generation, il faut lancer FastAPI dans un autre terminal :

```powershell
py -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Ensuite, dans Streamlit, cliquer sur :

```text
Generer et stocker
```

Le dashboard recupere alors les dernieres valeurs historiques, appelle `/predict`, puis insere ou met a jour les lignes dans `predictions`.
