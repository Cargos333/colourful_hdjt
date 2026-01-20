#!/bin/bash

# Script de démarrage pour Render.com
echo "🚀 Démarrage de l'application Colourful HDJT..."

# Créer les dossiers nécessaires
echo "📁 Création des dossiers..."
mkdir -p static/uploads
mkdir -p instance

# Initialiser la base de données si nécessaire
echo "📊 Initialisation de la base de données..."
python setup_db.py setup

# Lancer l'application avec Gunicorn
echo "🌐 Lancement du serveur avec Gunicorn..."
exec gunicorn -c gunicorn_config.py app:app
