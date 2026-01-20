#!/usr/bin/env python3
"""
Configuration et initialisation de la base de données pour Colourful HDJT
"""

import os
import sys

# Ajouter le répertoire courant au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_migrate import Migrate
from models import db
from init_db import init_database

def create_app():
    """Créer et configurer l'application Flask"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fede9da25c0bbb833ba34d53498250b1')
    
    # Utiliser DATABASE_URL si disponible (pour production), sinon SQLite pour développement
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        basedir = os.path.abspath(os.path.dirname(__file__))
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'colourful_hdjt.db')
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialiser les extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    return app

def setup_database():
    """Configurer la base de données"""
    app = create_app()

    with app.app_context():
        print("🔧 Configuration de la base de données...")

        # Créer toutes les tables
        db.create_all()
        print("✅ Tables créées")

        # Peupler la base de données avec les données initiales
        init_database()

        print("🎉 Base de données configurée avec succès !")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'setup':
        setup_database()
    else:
        print("Usage: python setup_db.py setup")
        print("Cela va créer et initialiser la base de données avec toutes les données.")