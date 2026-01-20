#!/bin/bash

# Script de démarrage pour Render.com
echo "🚀 Démarrage de l'application Colourful HDJT..."

# Créer les dossiers nécessaires
echo "📁 Création des dossiers..."
mkdir -p static/uploads
mkdir -p instance

# Initialiser la base de données si nécessaire
echo "📊 Initialisation de la base de données..."
python init_production_db.py 2>&1 || echo "⚠️ Erreur lors de l'initialisation (peut-être déjà initialisée)"

# Vérifier/réparer le compte admin
echo "🔐 Vérification du compte administrateur..."
python check_admin.py 2>&1 || echo "⚠️ Impossible de vérifier le compte admin"

# Lancer l'application avec Gunicorn
echo "🌐 Lancement du serveur avec Gunicorn..."
exec gunicorn -c gunicorn_config.py app:app
