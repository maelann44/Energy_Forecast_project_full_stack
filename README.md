# Energy Forecast Project Full Stack

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

## 11. Git et GitHub

Le projet doit etre versionne avec Git et pousse sur GitHub.

Commandes de base :

```powershell
git init
git branch -M main
git add .
git commit -m "Initial project setup"
git remote add origin https://github.com/maelann44/Energy_Forecast_project_full_stack.git
git push -u origin main
```

Si GitHub contient deja un README ou une licence :

```powershell
git pull origin main --allow-unrelated-histories
```

En cas de conflit dans `README.md`, supprimer les marqueurs :

```text
marqueur de debut de conflit
separateur entre les deux versions
marqueur de fin de conflit
```

puis :

```powershell
git add README.md
git commit -m "Resolve README merge conflict"
git push -u origin main
```

Verifier que `.env` n'est pas envoye :

```powershell
git check-ignore -v .env
git status
```

## 12. Deploiement low-cost sur VPS

Cette etape remplace le deploiement React + Express par l'architecture reelle du projet :

```text
Utilisateur
   |
   v
Streamlit Dashboard : port 8501
   |
   | lit les donnees
   v
PostgreSQL : conteneur prive

Streamlit Dashboard
   |
   | appelle /predict
   v
FastAPI + Chronos : port 8000
```

Le deploiement utilise Docker Compose pour garder le serveur simple :

- `postgres` : base de donnees PostgreSQL ;
- `fastapi` : API de prediction Chronos ;
- `streamlit` : dashboard web ;
- `worker` : service utilise ponctuellement par cron pour lancer les scripts.

### Choix economique du VPS

Pour reduire le prix, choisir un VPS Ubuntu avec au minimum :

- 2 vCPU ;
- 4 Go RAM ;
- 40 Go disque ;
- Ubuntu 22.04 ou 24.04 LTS.

Exemples de prix constates le 16 aout 2026 :

- OVHcloud VPS-1 : environ 4,57 EUR TTC/mois, 2 vCore, 4 Go RAM, 40 Go NVMe ;
- Hetzner CX23 : environ 5,49 EUR HT/mois hors IPv4, 2 vCPU, 4 Go RAM ;
- Scaleway Development Instance : prix tres bas possible, mais verifier les limites CPU/RAM dans la console.

Pour ce projet, le choix recommande low-cost est :

```text
OVHcloud VPS-1 ou Hetzner CX23
```

4 Go RAM peut suffire pour une demo, mais Chronos sur CPU peut etre lent. Si le serveur manque de memoire, passer a 8 Go RAM.

### Fichiers ajoutes pour le VPS

- `Dockerfile` : construit l'image Python du projet ;
- `docker-compose.vps.yml` : lance PostgreSQL, FastAPI et Streamlit sur le VPS ;
- `.dockerignore` : evite d'envoyer `.env`, les logs et les caches dans l'image Docker.

### 1. Creer le VPS

Dans le fournisseur choisi :

1. Creer un VPS Ubuntu LTS.
2. Ajouter votre cle SSH si possible.
3. Noter l'adresse IP publique du serveur.

Dans les exemples suivants, remplacer :

```text
VOTRE_IP_VPS
```

par l'adresse IP reelle.

### 2. Se connecter au serveur

Depuis PowerShell :

```powershell
ssh root@VOTRE_IP_VPS
```

### 3. Mettre a jour Ubuntu

Sur le VPS :

```bash
apt update
apt upgrade -y
```

### 4. Creer un utilisateur non-root

Remplacer `energy` par le nom voulu si necessaire :

```bash
adduser energy
usermod -aG sudo energy
```

Se reconnecter avec cet utilisateur :

```bash
exit
ssh energy@VOTRE_IP_VPS
```

### 5. Installer Docker et Git

Sur le VPS :

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
```

Installer Docker avec le script officiel :

```bash
curl -fsSL https://get.docker.com | sudo sh
```

Autoriser l'utilisateur courant a utiliser Docker :

```bash
sudo usermod -aG docker $USER
```

Se deconnecter puis se reconnecter :

```bash
exit
ssh energy@VOTRE_IP_VPS
```

Verifier Docker :

```bash
docker --version
docker compose version
```

### 6. Recuperer le projet depuis GitHub

Sur le VPS :

```bash
git clone https://github.com/maelann44/Energy_Forecast_project_full_stack.git
cd Energy_Forecast_project_full_stack
```

Si le depot est prive, GitHub demandera une authentification avec token.

### 7. Creer le fichier `.env` sur le VPS

Ne jamais envoyer `.env` sur GitHub. Le creer directement sur le serveur :

```bash
nano .env
```

Exemple :

```env
POSTGRES_DB=trading_data
POSTGRES_USER=dev_user
POSTGRES_PASSWORD=remplacer_par_un_mot_de_passe_solide
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

RTE_CLIENT_ID=remplacer_par_votre_client_id
RTE_CLIENT_SECRET=remplacer_par_votre_client_secret

CHRONOS_MODEL_NAME=amazon/chronos-t5-small
CHRONOS_DEVICE_MAP=cpu
PREDICTION_API_URL=http://fastapi:8000/predict
```

### 8. Lancer l'application sur le VPS

Construire et demarrer les conteneurs :

```bash
docker compose -f docker-compose.vps.yml up -d --build
```

Verifier :

```bash
docker compose -f docker-compose.vps.yml ps
```

Lire les logs :

```bash
docker compose -f docker-compose.vps.yml logs -f fastapi
```

Dans un autre terminal :

```bash
docker compose -f docker-compose.vps.yml logs -f streamlit
```

### 9. Acceder a l'application

Dashboard Streamlit :

```text
http://VOTRE_IP_VPS:8501
```

API FastAPI :

```text
http://VOTRE_IP_VPS:8000/docs
```

Health check :

```text
http://VOTRE_IP_VPS:8000/health
```

### 10. Charger des donnees dans PostgreSQL sur le VPS

Option rapide : copier le CSV local sur le VPS puis charger les donnees 2024.

Depuis PowerShell local, dans le dossier du projet :

```powershell
scp consumption_data_avg_hourly.csv energy@VOTRE_IP_VPS:/home/energy/Energy_Forecast_project_full_stack/
```

Sur le VPS :

```bash
docker cp consumption_data_avg_hourly.csv energy_postgres:/tmp/consumption_data_avg_hourly.csv
docker cp database/load_2024_historical_from_csv.sql energy_postgres:/tmp/load_2024_historical_from_csv.sql
docker exec energy_postgres psql -U dev_user -d trading_data -f /tmp/load_2024_historical_from_csv.sql
```

Verifier :

```bash
docker exec energy_postgres psql -U dev_user -d trading_data -c "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM historical_data;"
```

### 11. Tester une prediction sur le VPS

Verifier que FastAPI est actif :

```bash
curl http://localhost:8000/health
```

Lancer le batch de prediction sans insertion :

```bash
docker compose -f docker-compose.vps.yml run --rm worker python scripts/run_prediction_batch.py --api-url http://fastapi:8000/predict --context-length 168 --prediction-length 24 --dry-run
```

Insertion reelle :

```bash
docker compose -f docker-compose.vps.yml run --rm worker python scripts/run_prediction_batch.py --api-url http://fastapi:8000/predict --context-length 168 --prediction-length 24
```

Verifier la table `predictions` :

```bash
docker exec energy_postgres psql -U dev_user -d trading_data -c "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM predictions;"
```

### 12. Lancer une ingestion RTE sur le VPS

Test sans insertion :

```bash
docker compose -f docker-compose.vps.yml run --rm worker python scripts/ingest_rte_consumption.py --hours 24 --dry-run
```

Insertion reelle :

```bash
docker compose -f docker-compose.vps.yml run --rm worker python scripts/ingest_rte_consumption.py --hours 24
```

### 13. Cron plus tard

Le cron n'est pas obligatoire pour tester. Quand vous voudrez l'activer :

```bash
crontab -e
```

Exemple ingestion quotidienne a 23h30 :

```cron
30 23 * * * cd /home/energy/Energy_Forecast_project_full_stack && docker compose -f docker-compose.vps.yml run --rm worker python scripts/ingest_rte_consumption.py --hours 24 >> logs/cron_ingestion.log 2>&1
```

Exemple prediction quotidienne a 00h15 :

```cron
15 0 * * * cd /home/energy/Energy_Forecast_project_full_stack && docker compose -f docker-compose.vps.yml run --rm worker python scripts/run_prediction_batch.py --api-url http://fastapi:8000/predict --context-length 168 --prediction-length 24 >> logs/cron_prediction.log 2>&1
```

### 14. Redemarrer et mettre a jour

Apres une modification poussee sur GitHub :

```bash
git pull
docker compose -f docker-compose.vps.yml up -d --build
```

Redemarrer un service :

```bash
docker compose -f docker-compose.vps.yml restart streamlit
docker compose -f docker-compose.vps.yml restart fastapi
```

Arreter l'application sans supprimer les donnees :

```bash
docker compose -f docker-compose.vps.yml down
```

Ne pas utiliser cette commande sauf si vous voulez supprimer PostgreSQL :

```bash
docker compose -f docker-compose.vps.yml down -v
```

### 15. Securite minimale

Pour une demo low-cost sans nom de domaine, l'application sera accessible avec l'IP et les ports `8501` et `8000`.

Pour une version plus propre :

- acheter ou utiliser un nom de domaine ;
- installer Caddy ou Nginx comme reverse proxy ;
- activer HTTPS avec Let's Encrypt ;
- ne pas exposer FastAPI publiquement si seul Streamlit doit l'appeler ;
- mettre un mot de passe devant Streamlit ou limiter l'acces par firewall.
