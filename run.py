#!/usr/bin/env python3
"""
Script de démarrage pour Colourful HDJT
Initialise la base de données si nécessaire et lance l'application
"""

import os
import sys

def main():
    """Fonction principale"""
    print("🚀 Démarrage de Colourful HDJT...")

    # Vérifier si la base de données existe
    db_path = 'colourful_hdjt.db'
    if not os.path.exists(db_path):
        print("📊 Base de données non trouvée, initialisation...")
        os.system('python setup_db.py setup')
    else:
        print("📊 Base de données trouvée")

    # Lancer l'application
    print("🌐 Lancement de l'application Flask...")
    print("📱 Application accessible sur: http://127.0.0.1:5002")
    print("🛑 Pour arrêter: Ctrl+C")

    os.system('python app.py')

if __name__ == '__main__':
    main()