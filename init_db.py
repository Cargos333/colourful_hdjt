#!/usr/bin/env python3
"""
Script d'initialisation de la base de données pour Colourful HDJT
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import *
import json

def init_database():
    """Initialise la base de données et la peuple avec les données existantes"""

    with app.app_context():
        # Créer toutes les tables
        db.create_all()
        print("✓ Tables créées")

        # Peupler les catégories de produits
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

        for cat_id, cat_name in categories_data.items():
            if not ProductCategory.query.get(cat_id):
                category = ProductCategory(id=cat_id, name=cat_name)
                db.session.add(category)

        db.session.commit()
        print("✓ Catégories de produits ajoutées")

        # Peupler les produits
        products_data = []

        for prod_data in products_data:
            if not Product.query.get(prod_data[0]):
                product = Product(
                    id=prod_data[0],
                    name=prod_data[1],
                    brand=prod_data[2],
                    price=prod_data[3],
                    image_url=prod_data[4],
                    category_id=prod_data[5]
                )
                db.session.add(product)

        db.session.commit()
        print("✓ Produits ajoutés")

        # Peupler les types de contenants
        containers_data = [
            ('carton', 'Carton', 25, 5, ['rouge_levres', 'mascara', 'fond_teint', 'creme_hydratante', 'serum', 'nettoyant', 'vernis'], '/static/images/container-carton.svg'),
            ('sac_plastique', 'Sac en plastique transparent', 15, 3, ['rouge_levres', 'mascara', 'fond_teint', 'creme_hydratante', 'serum', 'nettoyant'], '/static/images/container-sac-plastique.svg'),
            ('goblet', 'Goblet transparent', 10, 2, ['rouge_levres', 'mascara', 'fond_teint', 'creme_hydratante'], '/static/images/container-goblet.svg'),
        ]

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

        db.session.commit()
        print("✓ Types de contenants ajoutés")

        # Peupler les produits prédéfinis
        predefined_products_data = [
            (1, 'Set Maquillage Premium', 'Rouge à lèvres, mascara, et fond de teint', 'carton', 25, 'https://via.placeholder.com/300x300?text=Set+Maquillage', True, ['rouge_levres', 'mascara', 'fond_teint'], 1),
            (2, 'Collection Soins Visage', 'Crème hydratante, sérum, et nettoyant', 'sac_plastique', 15, 'https://via.placeholder.com/300x300?text=Soins+Visage', True, ['creme_hydratante', 'serum', 'nettoyant'], 1),
            (3, 'Kit Vernis à Ongles', '5 vernis colorés dans un goblet', 'goblet', 10, 'https://via.placeholder.com/300x300?text=Vernis', True, ['vernis'], 5),
            (4, 'Set Parfum Miniature', '3 parfums miniatures assortis', 'goblet', 10, 'https://via.placeholder.com/300x300?text=Parfums', True, ['parfum'], 3),
            (5, 'Collection Cheveux', 'Shampooing, après-shampooing, masque', 'carton', 25, 'https://via.placeholder.com/300x300?text=Soins+Cheveux', True, ['shampooing', 'apres_shampooing', 'masque_cheveux'], 1),
            (6, 'Set Brosses Maquillage', '7 brosses professionnelles', 'sac_plastique', 15, 'https://via.placeholder.com/300x300?text=Brosses', False, [], 1),
        ]

        for prod_data in predefined_products_data:
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

        db.session.commit()
        print("✓ Produits prédéfinis ajoutés")

        print("\n🎉 Base de données initialisée avec succès !")
        print("📊 Statistiques :")
        print(f"   • {ProductCategory.query.count()} catégories de produits")
        print(f"   • {Product.query.count()} produits individuels")
        print(f"   • {ContainerType.query.count()} types de contenants")
        print(f"   • {PredefinedProduct.query.count()} produits prédéfinis")

if __name__ == '__main__':
    init_database()