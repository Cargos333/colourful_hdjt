# Déploiement sur Render.com - Colourful HDJT

## Étapes de déploiement

### 1. Préparer le projet
Tous les fichiers nécessaires sont déjà créés :
- ✅ `requirements.txt` - Dépendances Python
- ✅ `Procfile` - Commande de démarrage
- ✅ `runtime.txt` - Version Python
- ✅ `gunicorn_config.py` - Configuration Gunicorn
- ✅ `start.sh` - Script de démarrage

### 2. Créer un compte Render.com
1. Allez sur https://render.com
2. Créez un compte gratuit ou connectez-vous
3. Liez votre compte GitHub (recommandé) ou GitLab

### 3. Pousser le code sur GitHub
```bash
cd /Users/mohamedabdallah/Desktop/COLOURFUL_HDJT

# Initialiser git si ce n'est pas déjà fait
git init

# Ajouter tous les fichiers
git add .

# Faire un commit
git commit -m "Préparation pour déploiement sur Render.com"

# Ajouter le remote GitHub (remplacez par votre URL)
git remote add origin https://github.com/votre-username/colourful-hdjt.git

# Pousser sur GitHub
git push -u origin main
```

### 4. Créer un Web Service sur Render
1. Dans le dashboard Render, cliquez sur **"New +"** → **"Web Service"**
2. Connectez votre dépôt GitHub
3. Sélectionnez le dépôt **colourful-hdjt**
4. Configuration :
   - **Name**: `colourful-hdjt`
   - **Region**: Choisissez la région la plus proche
   - **Branch**: `main`
   - **Root Directory**: (laisser vide)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -c gunicorn_config.py app:app`

### 5. Variables d'environnement (optionnel)
Si vous avez des clés API ou secrets :
- Cliquez sur **"Environment"** dans le dashboard
- Ajoutez les variables nécessaires :
  - `SECRET_KEY` = votre_cle_secrete_longue_et_aleatoire
  - `DATABASE_URL` = (Render créera automatiquement une DB PostgreSQL si nécessaire)
  - `FLASK_ENV` = `production`

### 6. Déployer
1. Cliquez sur **"Create Web Service"**
2. Render va automatiquement :
   - Installer les dépendances
   - Initialiser la base de données
   - Démarrer l'application avec Gunicorn
3. Attendez que le déploiement soit terminé (quelques minutes)
4. Votre site sera disponible à : `https://colourful-hdjt.onrender.com`

### 7. Configuration de la base de données
Si vous voulez utiliser PostgreSQL (recommandé pour la production) :
1. Dans Render, créez une **PostgreSQL Database**
2. Copiez l'URL de connexion interne
3. Modifiez `app.py` pour utiliser cette URL au lieu de SQLite

### 8. Vérifications post-déploiement
- ✅ Testez l'accès au site
- ✅ Vérifiez que les images s'affichent
- ✅ Testez la connexion/inscription
- ✅ Vérifiez le panier
- ✅ Testez une commande

## Notes importantes

### Plan gratuit Render.com
- ✅ 750 heures/mois gratuites
- ⚠️ Le serveur s'endort après 15 minutes d'inactivité
- ⏱️ Premier chargement peut prendre 30-60 secondes
- 💾 Base de données SQLite persistante

### Stockage des fichiers
Les fichiers uploadés (images) sont stockés dans `/static/uploads/`. Sur le plan gratuit, ces fichiers peuvent être perdus lors d'un redéploiement. Pour une solution permanente :
- Utilisez un service comme Cloudinary ou AWS S3
- Ou passez à un plan payant Render avec persistent storage

### Logs et monitoring
- Dashboard Render → Votre service → **"Logs"** pour voir les logs en temps réel
- Dashboard Render → Votre service → **"Metrics"** pour les statistiques

## Mise à jour du site
Pour mettre à jour votre site après des modifications :
```bash
git add .
git commit -m "Description des modifications"
git push
```
Render redéploiera automatiquement !

## Support
- Documentation Render : https://render.com/docs
- Dashboard : https://dashboard.render.com
