# Colourful Beauty - E-commerce de Produits de Beauté

Site e-commerce Flask pour la vente de produits de beauté dans des contenants (cartons, sacs plastiques, gobelets) aux Comores.

## Installation

1. Créer un environnement virtuel :
```bash
python3 -m venv venv
source venv/bin/activate  # Sur macOS/Linux
```

2. Installer les dépendances :
```bash
pip install -r requirements.txt
```

3. **Configurer la base de données** :
```bash
# Initialiser et peupler la base de données
python setup_db.py setup
```

## Démarrage rapide

Pour démarrer l'application facilement (initialise automatiquement la base de données si nécessaire) :

```bash
python run.py
```

Ou lancer manuellement :

```bash
python app.py
```

5. Ouvrir le navigateur : http://127.0.0.1:5002

## Tests et validation

Après le démarrage, vous pouvez vérifier que tout fonctionne :

```bash
# Tester l'import de l'application
python -c "from app import app; print('✅ Import réussi')"

# Vérifier les données dans la base
python -c "
from app import app
with app.app_context():
    from models import Product, ProductCategory, ContainerType
    print(f'📊 {ProductCategory.query.count()} catégories, {Product.query.count()} produits, {ContainerType.query.count()} contenants')
"
```

## Base de données

Le projet utilise maintenant **SQLite** avec **SQLAlchemy** pour la persistance des données :

- **Utilisateurs** : Comptes clients avec authentification
- **Sessions mobiles** : Gestion des tokens d'API mobile
- **Produits** : Catalogue de produits de beauté
- **Contenants** : Types de contenants disponibles
- **Commandes** : Historique des achats
- **Panier** : Éléments du panier utilisateur

### Structure des tables

- `user` : Utilisateurs inscrits
- `mobile_session` : Sessions d'API mobile
- `product_category` : Catégories de produits (rouge à lèvres, mascara, etc.)
- `product` : Produits individuels
- `container_type` : Types de contenants
- `predefined_product` : Produits prédéfinis
- `order` : Commandes clients
- `order_item` : Éléments d'une commande
- `cart_item` : Éléments du panier

### Migration des données

Si vous aviez des données dans l'ancienne version (dictionnaires en mémoire), elles seront automatiquement migrées lors de l'initialisation.

## Structure du projet

```
COLOURFUL_HDJT/
├── app.py                 # Application Flask principale
├── requirements.txt       # Dépendances Python
├── static/
│   ├── css/
│   │   └── style.css     # Styles CSS
│   ├── js/
│   │   └── main.js       # JavaScript
│   └── uploads/          # Images uploadées
└── templates/
    ├── base.html         # Template de base
    ├── index.html        # Page d'accueil
    ├── produits.html     # Page liste des produits
    ├── produit_detail.html # Page détail produit
    ├── personnaliser.html # Page personnalisation produit
    ├── creer_contenant.html # Page création contenant personnalisé
    ├── panier.html       # Page panier d'achat
    └── contact.html      # Page de contact
```

## Fonctionnalités

## Fonctionnalités

- ✅ Page d'accueil attractive
- 🎨 Design moderne et responsive
- 📦 Trois types de contenants (Carton, Sac plastique, Goblet)
- 🛍️ **Page produits complète avec filtres et tri**
- 🔍 **Page de détail produit avec informations complètes**
- 🎨 **Personnalisation des produits** (choix des marques par catégorie)
- 🛒 **Système de panier fonctionnel (localStorage)**
- 📞 **Page de contact avec formulaire et FAQ**
- 🎯 Prix fixes par contenant en KMF (Franc comorien)
- 🛠️ **Création de contenants personnalisés** :
  - Choix du type de contenant (Carton/Sac/Goblet)
  - Sélection des produits compatibles avec le contenant
  - Limitation du nombre de produits selon le contenant
  - Calcul automatique du prix total
  - Ajout direct au panier

## Problèmes connus

### Application Mobile
- **Veille de l'écran** : Dans Expo Go (mode développement), l'écran peut ne pas se mettre en veille automatiquement. Ce problème est résolu dans les builds de production ou sur appareil physique.
- **Performance** : Certaines animations peuvent être lentes sur les appareils plus anciens.

## À venir

- Système de paiement intégré
- Gestion des commandes et suivi
- Interface d'administration
- Notifications par email
- Système de notation/commentaires
