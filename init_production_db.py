#!/usr/bin/env python3
"""
Script d'initialisation de la base de données pour production (Render.com)
Sans dépendance circulaire avec app.py
"""

import os
import sys
import json
import hashlib
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Configuration de l'application
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fede9da25c0bbb833ba34d53498250b1')

# Configuration de la base de données
database_url = os.environ.get('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'colourful_hdjt.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialiser la base de données
db = SQLAlchemy(app)

# Importer les modèles après l'initialisation de db
with app.app_context():
    # Importer tous les modèles
    from models import (
        User, ProductCategory, Product, ContainerType, 
        Container, ContainerProduct, PredefinedProduct
    )
    
    print("🚀 Initialisation de la base de données...")
    
    # Créer toutes les tables
    db.create_all()
    print("✅ Tables créées")
    
    # Vérifier et ajouter les catégories
    categories_data = {
        'rouge_levres': 'Rouge à lèvres',
        'mascara': 'Mascara',
        'fond_teint': 'Fond de teint',
        'creme_hydratante': 'Crème hydratante',
        'serum': 'Sérum',
        'nettoyant': 'Nettoyant',
        'vernis': 'Vernis à ongles',
        'shampooing': 'Shampooing',
        'apres_shampooing': 'Après-shampooing',
        'masque_cheveux': 'Masque cheveux'
    }
    
    categories_added = 0
    for cat_id, cat_name in categories_data.items():
        if not ProductCategory.query.get(cat_id):
            category = ProductCategory(id=cat_id, name=cat_name)
            db.session.add(category)
            categories_added += 1
    
    if categories_added > 0:
        db.session.commit()
        print(f"✅ {categories_added} catégories ajoutées")
    else:
        print("✅ Catégories déjà existantes")
    
    # Vérifier et ajouter les types de contenants
    containers_data = [
        ('carton', 'Carton', 25, 5, ['rouge_levres', 'mascara', 'fond_teint', 'creme_hydratante', 'serum', 'nettoyant', 'vernis'], '/static/images/container-carton.svg'),
        ('sac_plastique', 'Sac en plastique transparent', 15, 3, ['rouge_levres', 'mascara', 'fond_teint', 'creme_hydratante', 'serum', 'nettoyant'], '/static/images/container-sac-plastique.svg'),
        ('goblet', 'Goblet transparent', 10, 2, ['rouge_levres', 'mascara', 'fond_teint', 'creme_hydratante'], '/static/images/container-goblet.svg'),
    ]
    
    containers_added = 0
    for cont_data in containers_data:
        if not ContainerType.query.get(cont_data[0]):
            container = ContainerType(
                id=cont_data[0],
                name=cont_data[1],
                base_price=cont_data[2],
                max_products=cont_data[3],
                allowed_categories=json.dumps(cont_data[4]),
                image_url=cont_data[5]
            )
            db.session.add(container)
            containers_added += 1
    
    if containers_added > 0:
        db.session.commit()
        print(f"✅ {containers_added} types de contenants ajoutés")
    else:
        print("✅ Types de contenants déjà existants")
    
    # Vérifier et ajouter les produits prédéfinis
    predefined_products_data = [
        (1, 'Set Maquillage Premium', 'Rouge à lèvres, mascara, et fond de teint', 'carton', 25, 'https://via.placeholder.com/300x300?text=Set+Maquillage', True, ['rouge_levres', 'mascara', 'fond_teint'], 1),
        (2, 'Collection Soins Visage', 'Crème hydratante, sérum, et nettoyant', 'sac_plastique', 15, 'https://via.placeholder.com/300x300?text=Soins+Visage', True, ['creme_hydratante', 'serum', 'nettoyant'], 1),
        (3, 'Kit Vernis à Ongles', '5 vernis colorés dans un goblet', 'goblet', 10, 'https://via.placeholder.com/300x300?text=Vernis', True, ['vernis'], 5),
        (4, 'Set Parfum Miniature', '3 parfums miniatures assortis', 'goblet', 10, 'https://via.placeholder.com/300x300?text=Parfums', True, ['parfum'], 3),
        (5, 'Collection Cheveux', 'Shampooing, après-shampooing, masque', 'carton', 25, 'https://via.placeholder.com/300x300?text=Soins+Cheveux', True, ['shampooing', 'apres_shampooing', 'masque_cheveux'], 1),
        (6, 'Set Brosses Maquillage', '7 brosses professionnelles', 'sac_plastique', 15, 'https://via.placeholder.com/300x300?text=Brosses', False, [], 1),
    ]
    
    predefined_added = 0
    for prod_data in predefined_products_data:
        existing = PredefinedProduct.query.get(prod_data[0])
        if not existing:
            product = PredefinedProduct(
                id=prod_data[0],
                name=prod_data[1],
                description=prod_data[2],
                container_type_id=prod_data[3],
                price=prod_data[4],
                image_url=prod_data[5],
                is_customizable=prod_data[6],
                categories=json.dumps(prod_data[7]),
                quantity_per_category=prod_data[8]
            )
            db.session.add(product)
            predefined_added += 1
    
    if predefined_added > 0:
        db.session.commit()
        print(f"✅ {predefined_added} produits prédéfinis ajoutés")
    else:
        print("✅ Produits prédéfinis déjà existants")
    
    # Créer un compte administrateur par défaut
    admin_email = 'admin@colourful.com'
    admin_exists = User.query.filter_by(email=admin_email).first()
    
    if not admin_exists:
        admin_password = 'Admin@123456'
        admin_user = User(
            email=admin_email,
            username='admin',
            password_hash=hashlib.sha256(admin_password.encode()).hexdigest(),
            nom='Admin',
            prenom='Principal',
            telephone='',
            is_admin=True
        )
        db.session.add(admin_user)
        db.session.commit()
        print("✅ Compte administrateur créé")
        print(f"   📧 Email: {admin_email}")
        print(f"   🔑 Mot de passe: {admin_password}")
        print("   ⚠️  IMPORTANT: Changez ce mot de passe après votre première connexion!")
    else:
        print("✅ Compte administrateur déjà existant")
    
    print("\n🎉 Base de données initialisée avec succès!")
    print("📊 Statistiques:")
    print(f"   • {ProductCategory.query.count()} catégories de produits")
    print(f"   • {Product.query.count()} produits individuels")
    print(f"   • {ContainerType.query.count()} types de contenants")
    print(f"   • {PredefinedProduct.query.count()} produits prédéfinis")
    print(f"   • {User.query.filter_by(is_admin=True).count()} administrateur(s)")
