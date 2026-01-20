from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
import os
import re
import hashlib
import secrets
from models import db, User, MobileSession, ProductCategory, Product, ContainerType, Container, ContainerProduct, PredefinedProduct, Order, OrderItem, CartItem, Address, Favorite, Expense
import json
from flask_cors import CORS
from sqlalchemy import or_ as sql_or
from settings_utils import load_settings, save_settings, get_shipping_price, update_shipping_prices
from collections import defaultdict
import time

app = Flask(__name__)
CORS(app)  # Activer CORS pour toutes les routes
app.secret_key = 'fede9da25c0bbb833ba34d53498250b1'

# Rate limiting pour les tentatives d'authentification échouées
failed_auth_attempts = defaultdict(lambda: {'count': 0, 'first_attempt': 0, 'last_logged': 0})

def cleanup_rate_limit_data():
    """Nettoie les anciennes entrées du dictionnaire de rate limiting (> 1 heure)"""
    current_time = time.time()
    keys_to_delete = []
    for key, data in failed_auth_attempts.items():
        if current_time - data['last_logged'] > 3600:  # 1 heure
            keys_to_delete.append(key)
    for key in keys_to_delete:
        del failed_auth_attempts[key]
    if keys_to_delete:
        print(f"🧹 Nettoyage: {len(keys_to_delete)} entrées rate-limit supprimées")

# Configuration de la base de données
import os
basedir = os.path.abspath(os.path.dirname(__file__))

# Utiliser DATABASE_URL si disponible (pour production), sinon SQLite pour développement
database_url = os.environ.get('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'colourful_hdjt.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialiser SQLAlchemy
db.init_app(app)

# Créer les tables automatiquement si elles n'existent pas
with app.app_context():
    try:
        db.create_all()
        print("✅ Tables de base de données vérifiées/créées")
    except Exception as e:
        print(f"⚠️ Erreur lors de la création des tables: {e}")

# Ajouter le filtre from_json à Jinja2
@app.template_filter('from_json')
def from_json_filter(value):
    if value:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return []

# Configuration
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# NOTE: Les fonctions load_settings() et save_settings() sont maintenant 
# importées depuis settings_utils.py pour utiliser le même fichier
# instance/settings.json partout dans l'application

# Fonctions utilitaires pour l'authentification
def hash_password(password):
    """Hash un mot de passe avec SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_password_hash(hashed_password, password):
    """Vérifie si un mot de passe correspond à son hash"""
    return hashed_password == hash_password(password)

def generate_token():
    """Génère un token de session aléatoire"""
    return secrets.token_urlsafe(32)


def slugify(text):
    """Create a simple ASCII slug for category ids."""
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower().strip())
    slug = slug.strip('-') or 'category'

    # Ensure uniqueness by suffixing a counter if needed
    base_slug = slug
    counter = 1
    while db.session.get(ProductCategory, slug):
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug

def is_logged_in():
    """Vérifie si un utilisateur est connecté"""
    return 'user_email' in session

def get_user_by_email(email):
    """Récupère un utilisateur par email"""
    return User.query.filter_by(email=email).first()

def get_user_by_username(username):
    """Récupère un utilisateur par username"""
    return User.query.filter_by(username=username).first()

def get_user_by_email_or_username(identifier):
    """Récupère un utilisateur par email ou username"""
    user = get_user_by_email(identifier)
    if user:
        return user
    return get_user_by_username(identifier)

def get_user_by_token(token):
    """Récupère un utilisateur par token de session mobile et vérifie que c'est la session active"""
    # Rate limiting: limiter le logging des échecs répétés
    token_key = f"{token[:20]}"
    current_time = time.time()
    attempt_data = failed_auth_attempts[token_key]
    
    # Nettoyage périodique toutes les 100 tentatives
    if len(failed_auth_attempts) > 100 and hash(token_key) % 100 == 0:
        cleanup_rate_limit_data()
    
    session = MobileSession.query.filter_by(token=token).first()
    if session:
        if session.expires_at < datetime.utcnow():
            # Token expiré - logger seulement une fois par minute
            if current_time - attempt_data['last_logged'] > 60:
                print(f"⏰ Token expiré pour {session.user_email}: {token[:20]}...")
                attempt_data['last_logged'] = current_time
            return None
        user = get_user_by_email(session.user_email)
        if user and user.current_session_token == token:
            # Succès - réinitialiser le compteur
            if token_key in failed_auth_attempts:
                del failed_auth_attempts[token_key]
            return user
        else:
            # Le token existe mais ce n'est plus la session active (connexion depuis un autre appareil)
            # Logger seulement une fois par minute
            if current_time - attempt_data['last_logged'] > 60:
                print(f"⚠️ Session inactive détectée pour {session.user_email}: {token[:20]}... (autre appareil connecté)")
                attempt_data['last_logged'] = current_time
            return None
    else:
        # Token introuvable - logger seulement une fois par minute
        if current_time - attempt_data['last_logged'] > 60:
            print(f"❌ Token introuvable dans la base: {token[:20]}...")
            attempt_data['last_logged'] = current_time
        return None
    return None

def create_mobile_session(user_email):
    """Crée une nouvelle session mobile pour un utilisateur et invalide les anciennes"""
    # Supprimer toutes les anciennes sessions de cet utilisateur (déconnexion des autres appareils)
    MobileSession.query.filter_by(user_email=user_email).delete()
    
    # Supprimer les anciennes sessions expirées de tous les utilisateurs
    MobileSession.query.filter(MobileSession.expires_at < datetime.utcnow()).delete()

    # Créer une nouvelle session
    token = generate_token()
    expires_at = datetime.utcnow() + timedelta(days=30)  # 30 jours

    session = MobileSession(
        token=token,
        user_email=user_email,
        expires_at=expires_at
    )
    db.session.add(session)
    
    # Mettre à jour le current_session_token de l'utilisateur
    user = get_user_by_email(user_email)
    if user:
        user.current_session_token = token
    
    db.session.commit()

    return token

# Fonctions pour charger les données depuis la base de données
def get_contenants():
    """Récupère tous les types de contenants"""
    containers = ContainerType.query.all()
    result = {}
    for container in containers:
        result[container.id] = {
            'nom': container.name,
            'prix': container.base_price
        }
    return result

def get_options_produits():
    """Récupère toutes les options de produits organisées par catégorie depuis PredefinedProduct"""
    categories = ProductCategory.query.all()
    result = {}

    for category in categories:
        # Récupérer les produits prédéfinis qui contiennent cette catégorie
        all_predefined_products = PredefinedProduct.query.filter(
            PredefinedProduct.is_internal == False,  # Exclure les produits internes
            PredefinedProduct.image_url.isnot(None),
            PredefinedProduct.image_url != ''
        ).all()
        
        # Filtrer les produits qui appartiennent à cette catégorie
        category_products = []
        for product in all_predefined_products:
            if product.categories:
                try:
                    product_categories = json.loads(product.categories)
                    if category.id in product_categories:
                        # Vérifier que l'image est valide
                        if product.image_url and product.image_url.strip() and (
                            product.image_url.startswith('http') or 
                            product.image_url.startswith('/') or 
                            product.image_url.startswith('data:')
                        ):
                            category_products.append(product)
                except (json.JSONDecodeError, TypeError):
                    continue
        
        result[category.id] = {
            'nom': category.name,
            'options': [{
                'id': f'predefined_{product.id}',
                'nom': product.name,
                'marque': 'COLOURFUL HDJT',  # Marque par défaut
                'prix': product.price,
                'image': product.image_url
            } for product in category_products]
        }

    return result

def get_compatibilite_contenants():
    """Récupère la compatibilité entre contenants et produits"""
    containers = ContainerType.query.all()
    result = {}

    for container in containers:
        allowed_categories = json.loads(container.allowed_categories) if container.allowed_categories else []
        result[container.id] = {
            'nom': container.name,
            'prix_base': container.base_price,
            'max_produits': container.max_products,
            'categories_autorisees': allowed_categories,
            'image': container.image_url if hasattr(container, 'image_url') else None
        }

    return result

def get_produits_exemple():
    """Récupère les produits prédéfinis et les contenants (uniquement les éléments publics)"""
    result = []

    # Récupérer les produits prédéfinis
    products = PredefinedProduct.query.filter_by(is_internal=False).all()
    for product in products:
        categories = json.loads(product.categories) if product.categories else []
        result.append({
            'id': f'product_{product.id}',
            'nom': product.name,
            'description': product.description,
            'contenant': product.container_type_id,
            'prix': product.price,
            'image': product.image_url,
            'categories': categories,
            'personnalisable': product.is_customizable,
            'quantite_par_categorie': product.quantity_per_category,
            'type': 'product'
        })

    # Récupérer les contenants
    containers = Container.query.all()
    for container in containers:
        # Utiliser le prix spécifique du contenant personnalisé
        total_price = container.price

        # Récupérer les catégories des produits dans ce contenant
        categories = []
        for container_product in container.products:
            product_categories = json.loads(container_product.product.categories) if container_product.product.categories else []
            categories.extend(product_categories)
        categories = list(set(categories))  # Supprimer les doublons

        # Récupérer les informations des produits contenus
        contained_products = []
        for container_product in container.products:
            contained_products.append({
                'id': container_product.product.id,
                'name': container_product.product.name,
                'image_url': container_product.product.image_url,
                'price': container_product.product.price
            })

        result.append({
            'id': f'container_{container.id}',
            'nom': container.name,
            'description': container.description,
            'contenant': container.container_type_id,
            'prix': total_price,
            'image': container.image_url,
            'categories': categories,
            'personnalisable': False,  # Les contenants sont déjà personnalisés
            'quantite_par_categorie': 1,
            'type': 'container',
            'contained_products': contained_products
        })

    return result

# Chargement des données depuis la base de données (lazy loading)
def get_global_data():
    """Charge les données globales depuis la base de données"""
    return {
        'CONTENANTS': get_contenants(),
        'OPTIONS_PRODUITS': get_options_produits(),
        'COMPATIBILITE_CONTENANTS': get_compatibilite_contenants(),
        'PRODUITS_EXEMPLE': get_produits_exemple()
    }

@app.route('/')
def index():
    """Page d'accueil avec les produits en vedette"""
    data = get_global_data()

    # Calculer les statistiques dynamiques
    total_produits = len(data['PRODUITS_EXEMPLE'])
    total_contenants = len(data['CONTENANTS'])

    return render_template('index.html',
                         produits=data['PRODUITS_EXEMPLE'],
                         contenants=data['CONTENANTS'],
                         total_produits=total_produits,
                         total_contenants=total_contenants)

@app.route('/produits')
def produits():
    """Page listant tous les produits"""
    data = get_global_data()
    contenant_filtre = request.args.get('contenant', None)
    page = request.args.get('page', 1, type=int)
    per_page = 14

    if contenant_filtre:
        produits_filtres = [p for p in data['PRODUITS_EXEMPLE'] if p['contenant'] == contenant_filtre]
    else:
        produits_filtres = data['PRODUITS_EXEMPLE']

    # Pagination
    total_produits = len(produits_filtres)
    start = (page - 1) * per_page
    end = start + per_page
    produits_page = produits_filtres[start:end]

    # Calculer le nombre total de pages
    total_pages = (total_produits + per_page - 1) // per_page

    return render_template('produits.html',
                         produits=produits_page,
                         contenants=data['CONTENANTS'],
                         page=page,
                         total_pages=total_pages,
                         total_produits=total_produits,
                         per_page=per_page,
                         contenant_filtre=contenant_filtre)

@app.route('/search')
def search():
    """Page de résultats de recherche"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 14
    data = get_global_data()

    if not query:
        return redirect(url_for('produits'))

    # Recherche dans les produits
    produits_resultats = []
    for produit in data['PRODUITS_EXEMPLE']:
        if (query.lower() in produit['nom'].lower() or
            query.lower() in produit.get('description', '').lower() or
            query.lower() in produit.get('categorie', '').lower()):
            produits_resultats.append(produit)

    # Pagination pour les résultats de recherche
    total_produits = len(produits_resultats)
    start = (page - 1) * per_page
    end = start + per_page
    produits_page = produits_resultats[start:end]

    # Calculer le nombre total de pages
    total_pages = (total_produits + per_page - 1) // per_page

    return render_template('search.html',
                         query=query,
                         produits=produits_page,
                         contenants=data['CONTENANTS'],
                         page=page,
                         total_pages=total_pages,
                         total_produits=total_produits,
                         per_page=per_page)

@app.route('/api/search-suggestions')
def search_suggestions():
    """API pour les suggestions de recherche"""
    query = request.args.get('q', '').strip().lower()

    if not query or len(query) < 2:
        return jsonify([])

    data = get_global_data()
    suggestions = []

    # Collecter les suggestions des produits
    for produit in data['PRODUITS_EXEMPLE']:
        # Suggestion par nom de produit
        if query in produit['nom'].lower():
            suggestions.append({
                'text': produit['nom'],
                'type': 'product',
                'url': url_for('produit_detail', produit_id=produit['id'])
            })

        # Suggestion par description
        if produit.get('description') and query in produit.get('description', '').lower():
            if produit['nom'] not in [s['text'] for s in suggestions]:
                suggestions.append({
                    'text': f"{produit['nom']} - {produit.get('description', '')[:50]}...",
                    'type': 'product',
                    'url': url_for('produit_detail', produit_id=produit['id'])
                })

        # Suggestion par catégorie
        if produit.get('categorie') and query in produit.get('categorie', '').lower():
            category_suggestion = f"Catégorie: {produit.get('categorie')}"
            if category_suggestion not in [s['text'] for s in suggestions]:
                suggestions.append({
                    'text': category_suggestion,
                    'type': 'category',
                    'url': url_for('search') + f"?q={produit.get('categorie')}"
                })

    # Limiter à 8 suggestions maximum
    suggestions = suggestions[:8]

    return jsonify(suggestions)

@app.route('/produit/<produit_id>')
def produit_detail(produit_id):
    """Page de détail d'un produit ou contenant"""
    data = get_global_data()

    # Gérer les nouveaux formats d'ID
    if produit_id.startswith('product_'):
        actual_id = int(produit_id.split('_')[1])
        produit = next((p for p in data['PRODUITS_EXEMPLE'] if p['id'] == produit_id), None)
    elif produit_id.startswith('container_'):
        # Pour les contenants, récupérer depuis la base de données
        try:
            container_id = int(produit_id.split('_')[1])
            container = db.session.get(Container, container_id)
            if container:
                produit = {
                    'id': produit_id,
                    'nom': container.name,
                    'description': container.description,
                    'prix': container.price,
                    'image': container.image_url,
                    'contenant': container.container_type_id,
                    'personnalisable': container.is_customizable,
                    'categories': [],  # Sera rempli plus bas
                    'type': 'container'
                }
            else:
                produit = None
        except (ValueError, IndexError):
            produit = None
    else:
        # Pour la compatibilité avec l'ancien format
        try:
            produit_id_int = int(produit_id)
            produit = next((p for p in data['PRODUITS_EXEMPLE'] if isinstance(p['id'], int) and p['id'] == produit_id_int), None)
        except ValueError:
            produit = None

    if not produit:
        flash('Produit non trouvé', 'error')
        return redirect(url_for('produits'))

    # Récupérer les produits inclus pour les contenants
    produits_inclus = []
    if produit_id.startswith('container_'):
        try:
            container_id = int(produit_id.split('_')[1])
            container = db.session.get(Container, container_id)
            if container:
                categories = set()
                for container_product in container.products:
                    produits_inclus.append({
                        'id': container_product.product.id,
                        'nom': container_product.product.name,
                        'image': container_product.product.image_url,
                        'prix': container_product.product.price,
                        'quantite': container_product.quantity
                    })
                    # Ajouter les catégories du produit
                    if container_product.product.categories:
                        try:
                            product_categories = json.loads(container_product.product.categories)
                            categories.update(product_categories)
                        except (json.JSONDecodeError, TypeError):
                            pass
                
                # Mettre à jour les catégories du produit
                if produit:
                    produit['categories'] = list(categories)
        except (ValueError, IndexError):
            pass

    return render_template('produit_detail.html',
                         produit=produit,
                         contenants=data['CONTENANTS'],
                         produits=data['PRODUITS_EXEMPLE'],
                         produits_inclus=produits_inclus)

@app.route('/personnaliser/<produit_id>')
def personnaliser_produit(produit_id):
    """Page de personnalisation d'un produit"""
    data = get_global_data()

    # Gérer les nouveaux formats d'ID
    if produit_id.startswith('product_'):
        produit = next((p for p in data['PRODUITS_EXEMPLE'] if p['id'] == produit_id), None)
    elif produit_id.startswith('container_'):
        # Gérer la personnalisation des contenants depuis la base de données
        try:
            actual_id = int(produit_id.split('_')[1])
            container = db.session.get(Container, actual_id)
            if not container or not container.is_customizable:
                flash('Ce contenant n\'est pas personnalisable', 'error')
                return redirect(url_for('produits'))

            # Récupérer les catégories et les prix des produits du contenant
            categories = []
            prices_by_category = {}  # Prix par catégorie
            
            for container_product in container.products:
                product_categories = json.loads(container_product.product.categories) if container_product.product.categories else []
                categories.extend(product_categories)
                
                # Enregistrer le prix pour chaque catégorie
                for cat in product_categories:
                    if cat not in prices_by_category:
                        prices_by_category[cat] = container_product.product.price
            
            categories = list(set(categories))

            # Construire les options_produits pour chaque catégorie
            options_produits = {}
            for category in categories:
                # Récupérer le prix de référence pour cette catégorie
                reference_price = prices_by_category.get(category)
                
                # Récupérer tous les produits de cette catégorie depuis la base de données
                all_products = PredefinedProduct.query.filter_by(is_internal=False).all()
                category_products = []
                
                for product in all_products:
                    if product.categories:
                        try:
                            product_categories = json.loads(product.categories)
                            # Filtrer par catégorie ET par prix
                            if category in product_categories:
                                if reference_price is None or product.price == reference_price:
                                    category_products.append(product)
                        except (json.JSONDecodeError, TypeError):
                            continue
                
                options_produits[category] = {
                    'nom': category.replace('_', ' ').title(),
                    'options': [{
                        'id': product.id,
                        'nom': product.name,
                        'marque': 'COLOURFUL HDJT',  # Marque par défaut
                        'prix': product.price,
                        'image': product.image_url or '/static/images/default-product.jpg'
                    } for product in category_products]
                }

            # Créer l'objet produit pour le template
            produit = {
                'id': produit_id,
                'nom': container.name,
                'description': container.description,
                'prix': container.price,
                'image': container.image_url,
                'categories': categories,
                'personnalisable': True,
                'quantite_par_categorie': 1,  # Par défaut 1 produit par catégorie
                'type': 'container'
            }

            return render_template('personnaliser.html',
                                 produit=produit,
                                 contenants=data['CONTENANTS'],
                                 options_produits=options_produits)

        except (ValueError, IndexError):
            flash('ID de contenant invalide', 'error')
            return redirect(url_for('produits'))
    else:
        # Pour la compatibilité avec l'ancien format
        try:
            produit_id_int = int(produit_id)
            produit = next((p for p in data['PRODUITS_EXEMPLE'] if isinstance(p['id'], int) and p['id'] == produit_id_int), None)
        except ValueError:
            produit = None

    if not produit or not produit.get('personnalisable', False):
        flash('Ce produit n\'est pas personnalisable', 'error')
        return redirect(url_for('produits'))

    # Filtrer les options selon les catégories du produit
    options_filtrees = {cat: data['OPTIONS_PRODUITS'][cat] for cat in produit['categories'] if cat in data['OPTIONS_PRODUITS']}

    return render_template('personnaliser.html',
                         produit=produit,
                         contenants=data['CONTENANTS'],
                         options_produits=options_filtrees)

@app.route('/creer-contenant', methods=['GET'])
def creer_contenant():
    """Page de création d'un contenant personnalisé"""
    data = get_global_data()
    return render_template('creer_contenant.html',
                         contenants=data['COMPATIBILITE_CONTENANTS'],
                         options_produits=data['OPTIONS_PRODUITS'])

@app.route('/panier')
def panier():
    """Page du panier d'achat"""
    return render_template('panier.html')

@app.route('/checkout')
def checkout():
    """Page de paiement"""
    if not is_logged_in():
        flash('Veuillez vous connecter pour accéder à la page de paiement.', 'error')
        return redirect(url_for('login'))
    
    # Récupérer les adresses de l'utilisateur
    user_addresses = Address.query.filter_by(user_email=session['user_email']).all()
    default_address = next((addr for addr in user_addresses if addr.is_default), None)
    
    return render_template('checkout.html', addresses=user_addresses, default_address=default_address)


@app.route('/contact')
def contact():
    """Page de contact"""
    return render_template('contact.html')

@app.context_processor
def inject_year():
    """Injecter l'année actuelle dans tous les templates"""
    return {'current_year': datetime.now().year}

# API Routes
@app.route('/api/products')
def api_products():
    """API pour récupérer tous les produits"""
    data = get_global_data()
    return jsonify(data['PRODUITS_EXEMPLE'])

@app.route('/api/product/<product_id>')
def api_product_detail(product_id):
    """API pour récupérer les détails d'un produit ou contenant"""
    print(f"🔍 [API] Requête pour le produit avec ID: '{product_id}' (type: {type(product_id).__name__})")
    
    # Vérifier si c'est un produit personnalisé (commence par "custom-")
    if product_id.startswith('custom-'):
        print(f"  → Type: Produit personnalisé")
        # Chercher le produit personnalisé dans le panier
        panier = session.get('panier', [])
        product = next((p for p in panier if p['id'] == product_id), None)
        if not product:
            print(f"  ❌ Produit personnalisé non trouvé")
            return jsonify({'error': 'Produit personnalisé non trouvé'}), 404
        print(f"  ✅ Produit personnalisé trouvé: {product.get('nom', 'N/A')}")
        return jsonify(product)

    # Gérer les nouveaux formats d'ID (product_{id} et container_{id})
    if product_id.startswith('product_'):
        print(f"  → Type: Produit prédéfini")
        try:
            actual_id = int(product_id.split('_')[1])
            print(f"  → ID numérique: {actual_id}")
            product = db.session.get(PredefinedProduct, actual_id)
            if not product or product.is_internal:
                print(f"  ❌ Produit non trouvé ou interne")
                return jsonify({'error': 'Produit non trouvé'}), 404
            
            print(f"  ✅ Produit trouvé: {product.name}")

            categories = json.loads(product.categories) if product.categories else []
            return jsonify({
                'id': product_id,
                'nom': product.name,
                'description': product.description,
                'contenant': product.container_type_id,
                'prix': product.price,
                'image': product.image_url,
                'categories': categories,
                'personnalisable': product.is_customizable,
                'quantite_par_categorie': product.quantity_per_category,
                'type': 'product'
            })
        except (ValueError, IndexError) as e:
            print(f"  ❌ Erreur de parsing de l'ID: {e}")
            return jsonify({'error': 'ID de produit invalide'}), 400

    # Gérer les IDs numériques directs (pour compatibilité)
    print(f"  → Tentative d'interprétation comme ID numérique direct")
    try:
        actual_id = int(product_id)
        print(f"  → ID numérique: {actual_id}")
        product = db.session.get(PredefinedProduct, actual_id)
        if product and not product.is_internal:
            print(f"  ✅ Produit trouvé (ancien format): {product.name}")
            categories = json.loads(product.categories) if product.categories else []
            return jsonify({
                'id': f'product_{product_id}',  # Normaliser l'ID retourné
                'nom': product.name,
                'description': product.description,
                'contenant': product.container_type_id,
                'prix': product.price,
                'image': product.image_url,
                'categories': categories,
                'personnalisable': product.is_customizable,
                'quantite_par_categorie': product.quantity_per_category,
                'type': 'product'
            })
    except (ValueError, TypeError):
        pass  # Pas un ID numérique, continuer

    if product_id.startswith('container_'):
        print(f"  → Type: Contenant")
        try:
            actual_id = int(product_id.split('_')[1])
            print(f"  → ID numérique: {actual_id}")
            container = db.session.get(Container, actual_id)
            if not container:
                print(f"  ❌ Contenant non trouvé")
                return jsonify({'error': 'Contenant non trouvé'}), 404
            
            print(f"  ✅ Contenant trouvé: {container.name}")

            # Utiliser le prix spécifique du contenant
            total_price = container.price

            # Récupérer les catégories
            categories = []
            for container_product in container.products:
                product_categories = json.loads(container_product.product.categories) if container_product.product.categories else []
                categories.extend(product_categories)
            categories = list(set(categories))

            # Récupérer les informations des produits contenus
            contained_products = []
            for container_product in container.products:
                contained_products.append({
                    'id': container_product.product.id,
                    'name': container_product.product.name,
                    'image_url': container_product.product.image_url,
                    'price': container_product.product.price
                })

            return jsonify({
                'id': product_id,
                'nom': container.name,
                'description': container.description,
                'contenant': container.container_type_id,
                'prix': total_price,
                'image': container.image_url,
                'categories': categories,
                'personnalisable': container.is_customizable,
                'quantite_par_categorie': 1,
                'type': 'container',
                'contained_products': contained_products
            })
        except (ValueError, IndexError) as e:
            print(f"  ❌ Erreur de parsing de l'ID du contenant: {e}")
            return jsonify({'error': 'ID de contenant invalide'}), 400

    # Gérer les types de contenants simples (IDs comme "carton", "bouteille", etc.)
    print(f"  → Tentative d'interprétation comme type de contenant simple")
    data = get_global_data()
    container_info = data['COMPATIBILITE_CONTENANTS'].get(product_id)
    if container_info:
        print(f"  ✅ Type de contenant trouvé: {container_info['nom']}")
        return jsonify({
            'id': product_id,
            'nom': container_info['nom'],
            'description': f'Contenant {container_info["nom"]} - Prix de base: {container_info["prix_base"]} KMF',
            'contenant': product_id,
            'prix': container_info['prix_base'],
            'image': container_info.get('image', f'https://via.placeholder.com/300x300?text={container_info["nom"]}'),
            'categories': container_info['categories_autorisees'],
            'personnalisable': True,
            'quantite_par_categorie': 1,
            'type': 'container_type',
            'max_produits': container_info['max_produits']
        })

    # Pour la compatibilité avec l'ancien format (IDs entiers)
    print(f"  → Tentative d'interprétation comme ancien format (ID entier)")
    try:
        product_id_int = int(product_id)
        print(f"  → ID numérique: {product_id_int}")
        data = get_global_data()
        product = next((p for p in data['PRODUITS_EXEMPLE'] if isinstance(p['id'], int) and p['id'] == product_id_int), None)
        if not product:
            print(f"  ❌ Produit non trouvé dans l'ancien format")
            return jsonify({'error': 'Produit non trouvé'}), 404
        print(f"  ✅ Produit trouvé (ancien format): {product.get('nom', 'N/A')}")
        return jsonify(product)
    except ValueError as e:
        print(f"  ❌ ID invalide: {e}")
        return jsonify({'error': f'ID de produit invalide: {product_id}'}), 400

@app.route('/api/options')
def api_options():
    """API pour récupérer toutes les options de produits filtrées par container_id"""
    container_type = request.args.get('container_type')
    container_id = request.args.get('container_id')  # Nouveau paramètre
    data = get_global_data()

    # Si un container_id est spécifié, filtrer par catégories et prix du contenant
    if container_id:
        try:
            # Extraire l'ID numérique du container_id (format: "container_1")
            actual_id = int(container_id.split('_')[1]) if container_id.startswith('container_') else int(container_id)
            container = db.session.get(Container, actual_id)
            
            if container:
                # Récupérer les catégories et prix des produits du contenant
                categories = []
                prices_by_category = {}
                
                for container_product in container.products:
                    product_categories = json.loads(container_product.product.categories) if container_product.product.categories else []
                    categories.extend(product_categories)
                    
                    # Enregistrer le prix pour chaque catégorie
                    for cat in product_categories:
                        if cat not in prices_by_category:
                            prices_by_category[cat] = container_product.product.price
                
                categories = list(set(categories))
                
                # Construire les options filtrées par catégorie et prix
                filtered_options = {}
                for category in categories:
                    reference_price = prices_by_category.get(category)
                    
                    # Récupérer tous les produits de cette catégorie
                    all_products = PredefinedProduct.query.filter_by(is_internal=False).all()
                    category_products = []
                    
                    for product in all_products:
                        if product.categories:
                            try:
                                product_categories = json.loads(product.categories)
                                # Filtrer par catégorie ET par prix
                                if category in product_categories:
                                    if reference_price is None or product.price == reference_price:
                                        if product.image_url and product.image_url.strip():
                                            category_products.append(product)
                            except (json.JSONDecodeError, TypeError):
                                continue
                    
                    if category in data['OPTIONS_PRODUITS']:
                        filtered_options[category] = {
                            'nom': data['OPTIONS_PRODUITS'][category]['nom'],
                            'options': [{
                                'id': f'predefined_{product.id}',
                                'nom': product.name,
                                'marque': 'COLOURFUL HDJT',
                                'prix': product.price,
                                'image': product.image_url
                            } for product in category_products]
                        }
                
                return jsonify(filtered_options)
        except (ValueError, IndexError, AttributeError):
            pass  # Si erreur, continuer avec la logique normale
    
    if container_type and container_type in data['COMPATIBILITE_CONTENANTS']:
        # Filtrer les produits selon les catégories autorisées pour ce type de contenant
        allowed_categories = data['COMPATIBILITE_CONTENANTS'][container_type]['categories_autorisees']
        filtered_options = {cat: data['OPTIONS_PRODUITS'][cat] for cat in allowed_categories if cat in data['OPTIONS_PRODUITS']}
        return jsonify(filtered_options)
    else:
        # Retourner toutes les options si aucun type de contenant n'est spécifié
        return jsonify(data['OPTIONS_PRODUITS'])

@app.route('/api/containers')
def api_containers():
    """API pour récupérer les types de contenants"""
    data = get_global_data()
    return jsonify(data['COMPATIBILITE_CONTENANTS'])

@app.route('/api/create-container', methods=['POST'])
def api_create_container():
    """API pour créer un contenant personnalisé"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401
    
    api_data = get_global_data()
    data = request.get_json()
    contenant_type = data.get('contenant_type')
    selected_products = data.get('produits', [])
    
    if not contenant_type or contenant_type not in api_data['COMPATIBILITE_CONTENANTS']:
        return jsonify({'error': 'Type de contenant invalide'}), 400
    
    contenant_info = api_data['COMPATIBILITE_CONTENANTS'][contenant_type]
    
    if len(selected_products) > contenant_info['max_produits']:
        return jsonify({'error': f'Vous ne pouvez sélectionner que {contenant_info["max_produits"]} produits maximum'}), 400
    
    # Calculer le prix total : prix du contenant + somme des prix des produits sélectionnés
    prix_total = contenant_info['prix_base']
    
    # Créer la liste détaillée des produits inclus
    produits_inclus_details = []
    for product_id in selected_products:
        if product_id.startswith('predefined_'):
            actual_id = int(product_id.replace('predefined_', ''))
            product = db.session.get(PredefinedProduct, actual_id)
            if product:
                prix_total += product.price
                produits_inclus_details.append({
                    'id': product_id,
                    'nom': product.name,
                    'marque': 'COLOURFUL HDJT',
                    'prix': product.price,
                    'image': product.image_url
                })
    
    # Créer le produit personnalisé
    product_id = f'custom-{int(datetime.now().timestamp() * 1000)}'
    
    # S'assurer que l'image du contenant est définie
    container_image = contenant_info.get('image')
    if not container_image:
        # Fallback vers un SVG data URL
        container_image = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect width="100" height="100" fill="%23ff6b9d"/%3E%3Ctext x="50" y="50" text-anchor="middle" dy=".3em" fill="white" font-size="14" font-family="Arial"%3EContenant%3C/text%3E%3C/svg%3E'
    
    produit_personnalise = {
        'id': product_id,
        'product_id': product_id,
        'nom': f'Contenant {contenant_info["nom"]} personnalisé',
        'description': f'Contenant personnalisé avec {len(selected_products)} produits',
        'contenant': contenant_type,
        'prix': prix_total,
        'image': container_image,
        'quantite': 1,
        'type': 'contenant_personnalise',
        'product_type': 'contenant_personnalise',
        'produits_inclus': produits_inclus_details
    }
    
    try:
        print(f"CREATE CONTAINER - User: {user_email}, Container: {produit_personnalise}")
        print(f"Produits inclus: {produits_inclus_details}")
        print(f"Image du contenant: {produit_personnalise['image']}")
        
        # Créer un nouvel item du panier
        cart_item = CartItem(
            user_email=user_email,
            product_type='contenant_personnalise',
            product_id=product_id,
            product_data=json.dumps(produit_personnalise),
            quantity=1
        )
        db.session.add(cart_item)
        db.session.commit()
        
        # Récupérer tous les items du panier
        cart_items = CartItem.query.filter_by(user_email=user_email).all()
        cart_data = []
        for item in cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            cart_item_data = {
                'id': item.id,  # ID réel de la base de données (priorité absolue)
                'product_id': item.product_id,
                'product_type': item.product_type,
                'quantite': item.quantity,
                **product_data,  # Données du produit (mais id sera écrasé)
                'id': item.id  # Forcer l'ID réel à la fin pour s'assurer qu'il n'est pas écrasé
            }
            cart_data.append(cart_item_data)
        
        return jsonify({
            'message': 'Contenant personnalisé ajouté au panier',
            'produit': produit_personnalise,
            'cart': cart_data
        })
    except Exception as e:
        print(f"ERROR in create-container: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Erreur interne du serveur'}), 500
        print(f"Error creating container: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/cart')
def api_get_cart():
    """API pour récupérer le panier"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
        else:
            # Rate limiting: limiter le logging
            token_key = f"{token[:20]}"
            current_time = time.time()
            attempt_data = failed_auth_attempts[token_key]
            
            if current_time - attempt_data['last_logged'] > 60:
                print(f"Token invalide ou expiré: {token[:20]}...")
                attempt_data['last_logged'] = current_time
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        # Rate limiting: limiter le logging des échecs d'authentification
        token_key = f"{token[:20] if token else 'no-token'}"
        current_time = time.time()
        attempt_data = failed_auth_attempts[token_key]
        
        if current_time - attempt_data['last_logged'] > 60:
            print(f"Authentification échouée - Token: {token[:20] if token else 'None'}, User: {user_email}")
            attempt_data['last_logged'] = current_time
        
        return jsonify({'error': 'Authentification requise', 'message': 'Token invalide ou expiré'}), 401

    # Récupérer le panier de l'utilisateur depuis la base de données
    try:
        cart_items = CartItem.query.filter_by(user_email=user_email).all()
        
        cart_data = []
        for item in cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            
            # Pour les produits prédéfinis, récupérer les informations depuis la base de données
            if item.product_type == 'predefined' and item.product_id:
                try:
                    # Essayer de récupérer depuis PredefinedProduct
                    if item.product_id.startswith('product_'):
                        actual_id = int(item.product_id.split('_')[1])
                        product = db.session.get(PredefinedProduct, actual_id)
                        if not product:
                            print(f"Product not found for id {actual_id}")
                    else:
                        # Essayer avec l'ID numérique direct
                        actual_id = int(item.product_id)
                        product = db.session.get(PredefinedProduct, actual_id)
                        if not product:
                            print(f"Product not found for id {actual_id}")
                    
                    if product and not product.is_internal:
                        # Utiliser les données de la base de données comme base
                        base_product_data = {
                            'nom': product.name,
                            'description': product.description,
                            'prix': product.price,
                            'image': product.image_url,
                            'categories': json.loads(product.categories) if product.categories else [],
                            'personnalisable': product.is_customizable,
                            'quantite_par_categorie': product.quantity_per_category,
                            'type': 'product'
                        }
                        # Fusionner avec les données stockées (qui peuvent contenir des personnalisations)
                        product_data = {**base_product_data, **product_data}
                except (ValueError, TypeError):
                    pass  # Garder les données stockées si la récupération échoue
            
            # Fusionner les données en s'assurant que la quantité de la BD prévaut
            cart_item_data = {
                'id': item.id,  # ID réel de la base de données (priorité absolue)
                'product_id': item.product_id,
                'product_type': item.product_type,
                **product_data,  # Données du produit (mais id sera écrasé)
                'quantite': item.quantity,  # Quantité réelle de la BD
                'id': item.id  # Forcer l'ID réel à la fin pour s'assurer qu'il n'est pas écrasé
            }
            cart_data.append(cart_item_data)
        
        return jsonify(cart_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cart', methods=['POST'])
def api_add_to_cart():
    """API pour ajouter un produit au panier"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
        else:
            pass
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
        else:
            pass
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400
    
    try:
        
        # Vérifier si le produit existe déjà dans le panier
        existing_item = CartItem.query.filter_by(
            user_email=user_email,
            product_id=str(data.get('product_id', '')),
            product_type=data.get('type', 'predefined')
        ).first()
        
        if existing_item:
            # Mettre à jour la quantité si le produit existe déjà
            existing_item.quantity += data.get('quantite', 1)
            existing_item.product_data = json.dumps(data)  # Mettre à jour les données du produit
            db.session.commit()
        else:
            # Créer un nouvel item du panier
            cart_item = CartItem(
                user_email=user_email,
                product_type=data.get('type', 'predefined'),
                product_id=str(data.get('product_id', data.get('id', ''))),
                product_data=json.dumps(data),
                quantity=data.get('quantite', 1)
            )
            db.session.add(cart_item)
            db.session.commit()
        
        # Récupérer tous les items du panier
        cart_items = CartItem.query.filter_by(user_email=user_email).all()
        cart_data = []
        for item in cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            # Fusionner les données en s'assurant que la quantité de la BD prévaut
            cart_item_data = {
                'id': item.id,  # ID réel de la base de données (priorité absolue)
                'product_id': item.product_id,
                'product_type': item.product_type,
                **product_data,  # Données du produit (mais id sera écrasé)
                'quantite': item.quantity,  # Quantité réelle de la BD
                'id': item.id  # Forcer l'ID réel à la fin pour s'assurer qu'il n'est pas écrasé
            }
            cart_data.append(cart_item_data)
        
        return jsonify({
            'message': 'Produit ajouté au panier',
            'cart': cart_data
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/cart/<int:item_id>', methods=['PUT'])
def api_update_cart_item(item_id):
    """API pour mettre à jour la quantité d'un item du panier"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400
    
    try:
        
        # Récupérer l'item du panier
        cart_item = CartItem.query.filter_by(id=item_id, user_email=user_email).first()
        
        if not cart_item:
            return jsonify({'error': 'Item non trouvé'}), 404
        
        # Mettre à jour la quantité
        new_quantity = data.get('quantite', 1)
        
        if new_quantity <= 0:
            # Si la quantité est 0 ou négative, supprimer l'item
            db.session.delete(cart_item)
        else:
            cart_item.quantity = new_quantity
        
        db.session.commit()
        
        # Retourner le panier mis à jour
        cart_items = CartItem.query.filter_by(user_email=user_email).all()
        cart_data = []
        for item in cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            
            # Pour les produits prédéfinis, récupérer les informations depuis la base de données
            if item.product_type == 'predefined' and item.product_id:
                try:
                    if item.product_id.startswith('product_'):
                        actual_id = int(item.product_id.split('_')[1])
                        product = db.session.get(PredefinedProduct, actual_id)
                        if not product:
                            print(f"Product not found for id {actual_id}")
                    else:
                        actual_id = int(item.product_id)
                        product = db.session.get(PredefinedProduct, actual_id)
                        if not product:
                            print(f"Product not found for id {actual_id}")
                    
                    if product and not product.is_internal:
                        base_product_data = {
                            'nom': product.name,
                            'description': product.description,
                            'prix': product.price,
                            'image': product.image_url,
                            'categories': json.loads(product.categories) if product.categories else [],
                            'personnalisable': product.is_customizable,
                            'quantite_par_categorie': product.quantity_per_category,
                            'type': 'product'
                        }
                        product_data = {**base_product_data, **product_data}
                except (ValueError, TypeError):
                    pass
            
            cart_item_data = {
                'id': item.id,  # ID réel de la base de données (priorité absolue)
                'product_id': item.product_id,
                'product_type': item.product_type,
                'quantite': item.quantity,
                **product_data,  # Données du produit (mais id sera écrasé)
                'id': item.id  # Forcer l'ID réel à la fin pour s'assurer qu'il n'est pas écrasé
            }
            cart_data.append(cart_item_data)
        
        return jsonify({'cart': cart_data})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/cart/<int:item_id>', methods=['DELETE'])
def api_delete_cart_item(item_id):
    """API pour supprimer un item spécifique du panier"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401
    
    try:
        # Récupérer et supprimer l'item
        cart_item = CartItem.query.filter_by(id=item_id, user_email=user_email).first()
        
        if not cart_item:
            return jsonify({'error': 'Item non trouvé'}), 404
        
        db.session.delete(cart_item)
        db.session.commit()
        
        # Retourner le panier mis à jour
        cart_items = CartItem.query.filter_by(user_email=user_email).all()
        cart_data = []
        for item in cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            
            # Pour les produits prédéfinis, récupérer les informations depuis la base de données
            if item.product_type == 'predefined' and item.product_id:
                try:
                    if item.product_id.startswith('product_'):
                        actual_id = int(item.product_id.split('_')[1])
                        product = db.session.get(PredefinedProduct, actual_id)
                    else:
                        actual_id = int(item.product_id)
                        product = db.session.get(PredefinedProduct, actual_id)
                    
                    if product and not product.is_internal:
                        base_product_data = {
                            'nom': product.name,
                            'description': product.description,
                            'prix': product.price,
                            'image': product.image_url,
                            'categories': json.loads(product.categories) if product.categories else [],
                            'personnalisable': product.is_customizable,
                            'quantite_par_categorie': product.quantity_per_category,
                            'type': 'product'
                        }
                        product_data = {**base_product_data, **product_data}
                except (ValueError, TypeError):
                    pass
            
            cart_item_data = {
                'id': item.id,  # ID réel de la base de données (priorité absolue)
                'product_id': item.product_id,
                'product_type': item.product_type,
                'quantite': item.quantity,
                **product_data,  # Données du produit (mais id sera écrasé)
                'id': item.id  # Forcer l'ID réel à la fin pour s'assurer qu'il n'est pas écrasé
            }
            cart_data.append(cart_item_data)
        
        return jsonify({'cart': cart_data})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/cart/product/<product_id>', methods=['DELETE'])
def api_remove_product_from_cart(product_id):
    """API pour supprimer un produit du panier (tous les items de ce produit)"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401
    
    try:
        
        # Trouver et supprimer tous les items de ce produit pour cet utilisateur
        cart_items = CartItem.query.filter_by(
            user_email=user_email,
            product_id=product_id
        ).all()
        
        if not cart_items:
            return jsonify({'error': 'Produit non trouvé dans le panier'}), 404
        
        deleted_count = 0
        for item in cart_items:
            db.session.delete(item)
            deleted_count += 1
        
        db.session.commit()
        
        # Récupérer le panier mis à jour
        cart_items = CartItem.query.filter_by(user_email=user_email).all()
        cart_data = []
        for item in cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            cart_data.append({
                'id': item.id,
                'product_id': item.product_id,
                'product_type': item.product_type,
                'quantite': item.quantity,
                **product_data
            })
        
        return jsonify({
            'message': f'{deleted_count} produit(s) retiré(s) du panier',
            'cart': cart_data
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/cart/sync', methods=['POST'])
def api_sync_cart():
    """API pour synchroniser le panier local avec le serveur"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401
    
    data = request.get_json()
    if not data or 'local_cart' not in data:
        return jsonify({'error': 'Données manquantes'}), 400
    
    local_cart = data['local_cart']
    
    try:
        
        # Récupérer le panier actuel du serveur
        server_cart_items = CartItem.query.filter_by(user_email=user_email).all()
        server_cart = []
        for item in server_cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            server_cart.append({
                'id': item.id,
                'product_id': item.product_id,
                'product_type': item.product_type,
                'quantite': item.quantity,
                **product_data
            })
        
        # Fusionner les paniers
        merged_cart = []
        
        # Ajouter tous les items du serveur d'abord
        for server_item in server_cart:
            merged_cart.append(server_item)
        
        # Ajouter les items locaux qui ne sont pas déjà sur le serveur
        for local_item in local_cart:
            exists = False
            for server_item in server_cart:
                # Comparer par product_id et type
                if ((server_item.get('product_id') == local_item.get('product_id') or 
                     server_item.get('id') == local_item.get('id')) and
                    server_item.get('type') == local_item.get('type') and
                    server_item.get('product_type') == local_item.get('product_type')):
                    exists = True
                    break
            
            if not exists:
                print(f"Ajout de l'item local au serveur: {local_item}")
                # Créer un nouvel item dans la base de données
                cart_item = CartItem(
                    user_email=user_email,
                    product_type=local_item.get('type', local_item.get('product_type', 'predefined')),
                    product_id=str(local_item.get('product_id', local_item.get('id', ''))),
                    product_data=json.dumps(local_item),
                    quantity=local_item.get('quantite', 1)
                )
                db.session.add(cart_item)
                # Ne pas commiter ici, on le fait après
        
        db.session.commit()
        
        # Maintenant construire merged_cart avec les vrais IDs
        merged_cart = []
        # Ajouter tous les items du serveur d'abord
        for server_item in server_cart:
            merged_cart.append(server_item)
        
        # Ajouter les nouveaux items locaux avec leurs vrais IDs
        for local_item in local_cart:
            exists = False
            for server_item in server_cart:
                # Comparer par product_id et type
                if ((server_item.get('product_id') == local_item.get('product_id') or 
                     server_item.get('id') == local_item.get('id')) and
                    server_item.get('type') == local_item.get('type') and
                    server_item.get('product_type') == local_item.get('product_type')):
                    exists = True
                    break
            
            if not exists:
                # Trouver l'item que nous venons de créer
                cart_item = CartItem.query.filter_by(
                    user_email=user_email,
                    product_id=str(local_item.get('product_id', local_item.get('id', ''))),
                    product_type=local_item.get('type', local_item.get('product_type', 'predefined'))
                ).first()
                if cart_item:
                    merged_cart.append({
                        'id': cart_item.id,
                        'product_id': cart_item.product_id,
                        'product_type': cart_item.product_type,
                        'quantite': cart_item.quantity,
                        **local_item
                    })
        
        # Récupérer le panier final après commit
        final_cart_items = CartItem.query.filter_by(user_email=user_email).all()
        final_cart = []
        for item in final_cart_items:
            product_data = json.loads(item.product_data) if item.product_data else {}
            final_cart.append({
                'id': item.id,
                'product_id': item.product_id,
                'product_type': item.product_type,
                'quantite': item.quantity,
                **product_data
            })
        
        return jsonify({
            'message': 'Panier synchronisé avec succès',
            'cart': final_cart
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ==================== Routes d'authentification ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Vérifier les informations dans la base de données
        user = get_user_by_email_or_username(email)
        if user and user.password_hash == hash_password(password):
            session['user_email'] = user.email
            session['user_nom'] = user.nom
            session['user_prenom'] = user.prenom
            session['user_telephone'] = user.telephone
            session['user_username'] = user.username
            session['user_id'] = user.id
            flash('Connexion réussie !', 'success')
            return redirect(url_for('index'))
        else:
            flash('Email ou mot de passe incorrect', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Page d'inscription"""
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        nom = request.form.get('nom')
        prenom = request.form.get('prenom')
        telephone = request.form.get('telephone', '')

        # Validation
        if not all([email, username, password, nom, prenom]):
            flash('Tous les champs sont requis', 'error')
        elif password != password_confirm:
            flash('Les mots de passe ne correspondent pas', 'error')
        elif get_user_by_email(email):
            flash('Cet email est déjà utilisé', 'error')
        elif get_user_by_username(username):
            flash('Ce nom d\'utilisateur est déjà pris', 'error')
        elif len(username) < 3 or len(username) > 20:
            flash('Le nom d\'utilisateur doit contenir entre 3 et 20 caractères', 'error')
        elif not username.replace('_', '').isalnum():
            flash('Le nom d\'utilisateur ne peut contenir que des lettres, chiffres et underscores', 'error')
        else:
            # Créer le nouvel utilisateur dans la base de données
            new_user = User(
                email=email,
                username=username,
                password_hash=hash_password(password),
                nom=nom,
                prenom=prenom,
                telephone=telephone
            )
            db.session.add(new_user)
            db.session.commit()

            flash('Inscription réussie ! Vous pouvez maintenant vous connecter', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    """Déconnexion"""
    session.clear()
    flash('Vous avez été déconnecté', 'info')
    return redirect(url_for('index'))

@app.route('/terms')
def terms():
    """Page des conditions d'utilisation"""
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    """Page de politique de confidentialité"""
    return render_template('privacy.html')

@app.route('/profile')
def profile():
    """Page de profil utilisateur - Vue d'ensemble"""
    if not is_logged_in():
        flash('Vous devez être connecté pour accéder à cette page', 'error')
        return redirect(url_for('login'))

    # Rafraîchir les données de session avec les dernières infos utilisateur
    user = get_user_by_email(session['user_email'])
    if user:
        session['user_nom'] = user.nom
        session['user_prenom'] = user.prenom
        session['user_telephone'] = user.telephone
        session['user_username'] = user.username

    return render_template('profile.html')

@app.route('/profile/orders')
def profile_orders():
    """Page des commandes de l'utilisateur"""
    if not is_logged_in():
        flash('Vous devez être connecté pour accéder à cette page', 'error')
        return redirect(url_for('login'))

    # Calculer le total dépensé (commandes en cours + terminées)
    user_email = session['user_email']
    total_spent = db.session.query(db.func.sum(Order.total_price)).filter(
        Order.user_email == user_email,
        Order.status.in_(['confirmed', 'shipped', 'delivered'])
    ).scalar() or 0

    return render_template('profile_orders.html', total_spent=total_spent)

@app.route('/profile/favorites')
def profile_favorites():
    """Page des favoris de l'utilisateur"""
    if not is_logged_in():
        flash('Vous devez être connecté pour accéder à cette page', 'error')
        return redirect(url_for('login'))

    return render_template('profile_favorites.html')

@app.route('/profile/settings')
def profile_settings():
    """Page des paramètres de l'utilisateur"""
    if not is_logged_in():
        flash('Vous devez être connecté pour accéder à cette page', 'error')
        return redirect(url_for('login'))

    return render_template('profile_settings.html')

@app.route('/profile/addresses')
def profile_addresses():
    """Page des adresses de l'utilisateur"""
    if not is_logged_in():
        flash('Vous devez être connecté pour accéder à cette page', 'error')
        return redirect(url_for('login'))

    return render_template('profile_addresses.html')

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """API d'inscription pour mobile"""
    data = request.get_json()

    email = data.get('email')
    username = data.get('username')
    password = data.get('password')
    nom = data.get('nom')
    prenom = data.get('prenom')
    telephone = data.get('telephone', '')

    # Validation
    if not all([email, password, nom, prenom]):
        return jsonify({'error': 'Tous les champs sont requis'}), 400

    if get_user_by_email(email):
        return jsonify({'error': 'Cet email est déjà utilisé'}), 400

    if username and get_user_by_username(username):
        return jsonify({'error': 'Ce nom d\'utilisateur est déjà utilisé'}), 400

    # Créer l'utilisateur dans la base de données
    new_user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        nom=nom,
        prenom=prenom,
        telephone=telephone
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        'message': 'Inscription réussie',
        'user': {
            'id': new_user.id,
            'email': email,
            'username': username,
            'first_name': prenom,
            'last_name': nom,
            'phone': telephone
        }
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """API de connexion pour mobile"""
    data = request.get_json()

    identifier = data.get('email')  # Peut être email ou username
    password = data.get('password')

    if not identifier or not password:
        return jsonify({'error': 'Identifiant et mot de passe requis'}), 400

    # Vérifier les informations dans la base de données
    user = get_user_by_email_or_username(identifier)
    if user and user.password_hash == hash_password(password):
        # Créer une session mobile
        token = create_mobile_session(user.email)

        return jsonify({
            'message': 'Connexion réussie',
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'first_name': user.prenom,
                'last_name': user.nom,
                'phone': user.telephone
            }
        }), 200
    else:
        return jsonify({'error': 'Identifiant ou mot de passe incorrect'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """API de déconnexion pour mobile"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')

    # Supprimer la session de la base de données
    session = MobileSession.query.filter_by(token=token).first()
    if session:
        db.session.delete(session)
        db.session.commit()
        return jsonify({'message': 'Déconnexion réussie'})

    return jsonify({'error': 'Token invalide'}), 401

@app.route('/api/auth/me', methods=['GET'])
def api_get_user():
    """API pour obtenir les informations de l'utilisateur connecté"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')

    # Vérifier le token dans la base de données
    user = get_user_by_token(token)
    if not user:
        # Vérifier si le token existe mais est expiré ou inactif
        session = MobileSession.query.filter_by(token=token).first()
        if session:
            if session.expires_at < datetime.utcnow():
                print(f"Token expiré pour {session.user_email}, expiration: {session.expires_at}")
                return jsonify({'error': 'Token expiré, veuillez vous reconnecter', 'expired': True}), 401
            else:
                # Token valide mais plus la session active (connexion depuis un autre appareil)
                print(f"Session inactive pour {session.user_email} - connexion depuis un autre appareil")
                return jsonify({'error': 'Votre compte est connecté sur un autre appareil', 'session_replaced': True}), 401
        print(f"Token invalide ou inexistant: {token[:20] if token else 'None'}...")
        return jsonify({'error': 'Token invalide, veuillez vous reconnecter', 'invalid': True}), 401

    return jsonify({
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'first_name': user.prenom,
            'last_name': user.nom,
            'phone': user.telephone
        }
    })

@app.route('/api/auth/update-profile', methods=['PUT'])
def api_update_profile():
    """API pour mettre à jour les informations du profil utilisateur"""
    # Support pour mobile (token) et web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token:
        # Authentification mobile
        user = get_user_by_token(token)
    else:
        # Authentification web via session
        if not is_logged_in():
            return jsonify({'error': 'Non authentifié'}), 401
        user = get_user_by_email(session['user_email'])
    
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json()

    # Mettre à jour les champs fournis
    if 'prenom' in data:
        user.prenom = data['prenom']
    if 'nom' in data:
        user.nom = data['nom']
    if 'username' in data:
        # Vérifier que le username n'est pas déjà utilisé par un autre utilisateur
        existing_user = get_user_by_username(data['username'])
        if existing_user and existing_user.id != user.id:
            return jsonify({'error': 'Ce nom d\'utilisateur est déjà utilisé'}), 400
        user.username = data['username']
    if 'telephone' in data:
        user.telephone = data['telephone']

    try:
        db.session.commit()
        return jsonify({
            'message': 'Profil mis à jour avec succès',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'first_name': user.prenom,
                'last_name': user.nom,
                'phone': user.telephone
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Erreur lors de la mise à jour'}), 500

@app.route('/api/auth/change-password', methods=['PUT'])
def api_change_password():
    """API pour changer le mot de passe de l'utilisateur"""
    # Support pour mobile (token) et web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token:
        # Authentification mobile
        user = get_user_by_token(token)
    else:
        # Authentification web via session
        if not is_logged_in():
            return jsonify({'error': 'Non authentifié'}), 401
        user = get_user_by_email(session['user_email'])
    
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json()

    current_password = data.get('current_password')
    new_password = data.get('new_password')

    # Validation
    if not current_password or not new_password:
        return jsonify({'error': 'Mot de passe actuel et nouveau mot de passe requis'}), 400

    # Vérifier que le mot de passe actuel est correct
    if user.password_hash != hash_password(current_password):
        return jsonify({'error': 'Mot de passe actuel incorrect'}), 401

    # Vérifier que le nouveau mot de passe est différent
    if current_password == new_password:
        return jsonify({'error': 'Le nouveau mot de passe doit être différent de l\'actuel'}), 400

    # Vérifier la longueur minimale du mot de passe
    if len(new_password) < 6:
        return jsonify({'error': 'Le nouveau mot de passe doit contenir au moins 6 caractères'}), 400

    # Mettre à jour le mot de passe
    user.password_hash = hash_password(new_password)

    try:
        db.session.add(user)  # S'assurer que l'objet est dans la session
        db.session.flush()  # Forcer l'écriture
        db.session.commit()
        
        return jsonify({'message': 'Mot de passe changé avec succès'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Erreur lors du changement de mot de passe'}), 500

@app.route('/api/auth/delete-account', methods=['DELETE'])
def api_delete_account():
    """API pour supprimer définitivement le compte utilisateur"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')

    print(f"DEBUG delete-account: token={bool(token)}, session_keys={list(session.keys())}, user_email_in_session={'user_email' in session}")

    user = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        print(f"DEBUG delete-account: mobile auth, user={user is not None}")
    else:
        # Web
        if is_logged_in():
            user_email = session.get('user_email')
            print(f"DEBUG delete-account: looking for user with email: '{user_email}'")
            user = get_user_by_email(user_email)
            print(f"DEBUG delete-account: user found: {user is not None}")
            if user:
                print(f"DEBUG delete-account: user details: id={user.id}, email={user.email}")
            else:
                print(f"DEBUG delete-account: user not found in database - clearing invalid session")
                # Clear the invalid session
                session.clear()
                return jsonify({'error': 'Session invalide - veuillez vous reconnecter'}), 401
        else:
            print("DEBUG delete-account: not logged in")

    if not user:
        print("DEBUG delete-account: returning 401 - not authenticated")
        return jsonify({'error': 'Non authentifié'}), 401

    try:
        # Supprimer toutes les données liées à l'utilisateur
        # 1. Sessions mobiles
        MobileSession.query.filter_by(user_email=user.email).delete()

        # 2. Items du panier
        CartItem.query.filter_by(user_email=user.email).delete()

        # 3. Favoris
        Favorite.query.filter_by(user_email=user.email).delete()

        # 4. Adresses
        Address.query.filter_by(user_email=user.email).delete()

        # 5. Commandes et leurs items (supprimer les items d'abord)
        orders = Order.query.filter_by(user_email=user.email).all()
        for order in orders:
            OrderItem.query.filter_by(order_id=order.id).delete()
        Order.query.filter_by(user_email=user.email).delete()

        # 6. Supprimer l'utilisateur
        db.session.delete(user)
        db.session.commit()

        return jsonify({'message': 'Compte supprimé définitivement avec succès'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Erreur lors de la suppression du compte'}), 500

# Routes API pour les commandes
@app.route('/api/commandes', methods=['GET', 'POST'])
@app.route('/api/orders', methods=['GET', 'POST'])  # Alias pour compatibilité mobile
def api_commandes():
    """API pour gérer les commandes"""
    if request.method == 'GET':
        # Authentification pour mobile (token) ou web (session)
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if token:
            # Mobile
            user = get_user_by_token(token)
        else:
            # Web
            if not is_logged_in():
                return jsonify({'error': 'Non authentifié'}), 401
            user = get_user_by_email(session['user_email'])
        
        if not user:
            return jsonify({'error': 'Non authentifié'}), 401

        # Récupérer les commandes de l'utilisateur
        try:
            orders = Order.query.filter_by(user_email=user.email).order_by(Order.created_at.desc()).all()
            orders_data = []
            for order in orders:
                order_items = []
                for item in order.order_items:
                    # Charger les données complètes du produit depuis product_data
                    product_data = json.loads(item.product_data) if item.product_data else {}
                    order_items.append({
                        **product_data,  # Inclure toutes les données du produit
                        'id': item.product_id,
                        'nom': item.product_name,
                        'prix': item.price,
                        'quantite': item.quantity,
                        'image': item.product_image or '/static/images/placeholder.jpg'
                    })
                
                orders_data.append({
                    'id': str(order.id),
                    'items': order_items,
                    'totalPrice': order.total_price,
                    'paymentMethod': order.payment_method,
                    'deliveryAddress': json.loads(order.delivery_address) if order.delivery_address else None,
                    'status': 'completed' if order.status == 'delivered' else order.status,
                    'createdAt': order.created_at.isoformat()
                })
            
            return jsonify(orders_data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        # Authentification pour mobile (token) ou web (session)
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        user_email = None
        if token:
            # Mobile
            user = get_user_by_token(token)
            if user:
                user_email = user.email
        else:
            # Web
            if is_logged_in():
                user_email = session['user_email']
        
        if not user_email:
            return jsonify({'error': 'Non authentifié'}), 401

        # Créer une nouvelle commande
        try:
            data = request.get_json()
            
            # Créer la commande
            new_order = Order(
                user_email=user_email,
                total_price=data['totalPrice'],
                payment_method=data['paymentMethod'],
                delivery_address=json.dumps(data.get('deliveryAddress', {})),
                status=data.get('status', 'pending')
            )
            db.session.add(new_order)
            db.session.flush()  # Pour obtenir l'ID de la commande
            
            # Ajouter les items
            for item in data['items']:
                order_item = OrderItem(
                    order_id=new_order.id,
                    product_id=str(item.get('id')) if item.get('id') else None,
                    product_name=item['nom'],
                    product_image=item.get('image', '/static/images/placeholder.jpg'),
                    product_data=json.dumps(item),  # Sauvegarder toutes les données du produit
                    price=item['prix'],
                    quantity=item.get('quantite', 1)
                )
                db.session.add(order_item)
            
            db.session.commit()
            
            # Vider le panier après une commande réussie
            try:
                CartItem.query.filter_by(user_email=user_email).delete()
                db.session.commit()
            except Exception as cart_error:
                pass
            
            return jsonify({
                'id': str(new_order.id),
                'message': 'Commande créée avec succès'
            }), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

@app.route('/api/commandes/<order_id>', methods=['PUT'])
def api_update_order(order_id):
    """API pour mettre à jour le statut d'une commande"""
    try:
        order = db.session.get(Order, int(order_id))
        if not order:
            return jsonify({'error': 'Commande non trouvée'}), 404
        
        data = request.get_json()
        if 'status' in data:
            # Mapper les statuts de l'app mobile vers la base de données
            status_mapping = {
                'completed': 'delivered',
                'pending': 'pending',
                'cancelled': 'cancelled'
            }
            order.status = status_mapping.get(data['status'], data['status'])
            db.session.commit()
            return jsonify({'message': 'Statut mis à jour avec succès'})
        
        return jsonify({'error': 'Aucune donnée à mettre à jour'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/addresses', methods=['GET', 'POST'])
def api_addresses():
    """API pour gérer les adresses"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401

    if request.method == 'GET':
        # Récupérer toutes les adresses de l'utilisateur
        try:
            print(f"GET /api/addresses - User: {user_email}")
            addresses = Address.query.filter_by(user_email=user_email).order_by(Address.created_at.desc()).all()
            print(f"Found {len(addresses)} addresses for user {user_email}")
            addresses_data = []
            for addr in addresses:
                print(f"Address: id={addr.id}, name={addr.name}, user_email={addr.user_email}")
                addresses_data.append({
                    'id': addr.id,
                    'name': addr.name,
                    'recipient_name': addr.recipient_name,
                    'phone': addr.phone,
                    'address_line_1': addr.address_line_1,
                    'address_line_2': addr.address_line_2,
                    'city': addr.city,
                    'region': addr.region,
                    'postal_code': addr.postal_code,
                    'country': addr.country,
                    'is_default': addr.is_default,
                    'address_type': addr.address_type,
                    'created_at': addr.created_at.isoformat()
                })
            
            return jsonify(addresses_data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif request.method == 'POST':
        # Créer une nouvelle adresse
        try:
            data = request.get_json()
            print(f"POST /api/addresses - User: {user_email}, Data: {data}")
            
            # Si c'est l'adresse par défaut, retirer le flag par défaut des autres
            if data.get('is_default', False):
                Address.query.filter_by(user_email=user_email).update({'is_default': False})
            
            new_address = Address(
                user_email=user_email,
                name=data['name'],
                recipient_name=data['recipient_name'],
                phone=data.get('phone'),
                address_line_1=data['address_line_1'],
                address_line_2=data.get('address_line_2'),
                city=data['city'],
                region=data.get('region'),
                postal_code=data.get('postal_code'),
                country=data.get('country', 'Comores'),
                is_default=data.get('is_default', False),
                address_type=data.get('address_type', 'shipping')
            )
            db.session.add(new_address)
            db.session.commit()
            
            return jsonify({
                'id': new_address.id,
                'message': 'Adresse créée avec succès'
            }), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

@app.route('/api/addresses/<int:address_id>', methods=['PUT', 'DELETE'])
def api_address_detail(address_id):
    """API pour modifier ou supprimer une adresse"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    user_email = None
    if token:
        # Mobile
        user = get_user_by_token(token)
        if user:
            user_email = user.email
    else:
        # Web
        if is_logged_in():
            user_email = session['user_email']
    
    if not user_email:
        return jsonify({'error': 'Authentification requise'}), 401

    try:
        address = Address.query.filter_by(id=address_id, user_email=user_email).first()
        if not address:
            return jsonify({'error': 'Adresse non trouvée'}), 404

        if request.method == 'PUT':
            # Mettre à jour l'adresse
            data = request.get_json()
            
            # Si c'est l'adresse par défaut, retirer le flag par défaut des autres
            if data.get('is_default', False):
                Address.query.filter_by(user_email=user_email).filter(Address.id != address_id).update({'is_default': False})
            
            # Mettre à jour les champs
            for field in ['name', 'recipient_name', 'phone', 'address_line_1', 'address_line_2', 'city', 'region', 'postal_code', 'country', 'is_default', 'address_type']:
                if field in data:
                    setattr(address, field, data[field])
            
            db.session.commit()
            return jsonify({'message': 'Adresse mise à jour avec succès'})

        elif request.method == 'DELETE':
            # Supprimer l'adresse
            db.session.delete(address)
            db.session.commit()
            return jsonify({'message': 'Adresse supprimée avec succès'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/shipping-prices', methods=['GET'])
def api_shipping_prices():
    """API pour récupérer tous les prix de livraison"""
    from settings_utils import load_settings, normalize_shipping_prices
    
    settings = load_settings()
    raw_shipping_prices = settings.get('shipping', {
        'Moroni': 1500,
        'Hors Moroni': 2000,
        'Mutsamudu': 2500,
        'Hors Mutsamudu': 3000,
        'Fomboni': 3200,
        'Hors Fomboni': 3500
    })
    
    # Normaliser les clés pour garantir le format correct
    shipping_prices = normalize_shipping_prices(raw_shipping_prices)
    
    return jsonify({
        'success': True,
        'prices': shipping_prices
    })

@app.route('/api/shipping-price', methods=['POST'])
def api_shipping_price():
    """API pour calculer le prix de livraison basé sur la région"""
    data = request.get_json()
    region = data.get('region', '')
    country = data.get('country', 'Comores')
    
    # Obtenir le prix de livraison
    shipping_price = get_shipping_price(region, country)
    
    return jsonify({
        'shipping_price': shipping_price,
        'region': region,
        'country': country
    })

@app.route('/api/login_status')
def api_login_status():
    """Vérifie si l'utilisateur est connecté"""
    if is_logged_in():
        return jsonify({'logged_in': True, 'user_email': session['user_email']})
    else:
        return jsonify({'logged_in': False}), 401

@app.route('/api/favorites', methods=['GET', 'POST'])
def api_favorites():
    """API pour gérer les favoris"""
    # Authentification pour mobile (token) ou web (session)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token:
        # Mobile
        user = get_user_by_token(token)
    else:
        # Web
        if not is_logged_in():
            return jsonify({'error': 'Non authentifié'}), 401
        user = get_user_by_email(session['user_email'])
    
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    if request.method == 'GET':
        # Récupérer tous les favoris de l'utilisateur
        try:
            favorites = Favorite.query.filter_by(user_email=user.email).order_by(Favorite.added_at.desc()).all()
            favorites_data = []
            for fav in favorites:
                favorites_data.append({
                    'id': fav.id,
                    'product_type': fav.product_type,
                    'product_id': fav.product_id,
                    'product_data': json.loads(fav.product_data) if fav.product_data else None,
                    'added_at': fav.added_at.isoformat()
                })
            
            return jsonify(favorites_data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif request.method == 'POST':
        # Ajouter ou supprimer un favori
        try:
            data = request.get_json()
            product_id = data['product_id']
            
            # Vérifier si le favori existe déjà
            existing_fav = Favorite.query.filter_by(
                user_email=user.email,
                product_id=product_id
            ).first()
            
            if existing_fav:
                # Supprimer le favori
                db.session.delete(existing_fav)
                db.session.commit()
                return jsonify({'message': 'Favori supprimé', 'action': 'removed'})
            else:
                # Ajouter le favori
                new_fav = Favorite(
                    user_email=user.email,
                    product_type=data.get('product_type', 'predefined'),
                    product_id=product_id,
                    product_data=json.dumps(data.get('product_data', {}))
                )
                db.session.add(new_fav)
                db.session.commit()
                return jsonify({'message': 'Favori ajouté', 'action': 'added'}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

@app.route('/api/favorites/sync', methods=['POST'])
def api_sync_favorites():
    """API pour synchroniser les favoris depuis localStorage"""
    if not is_logged_in():
        return jsonify({'error': 'Non authentifié'}), 401

    user_email = session['user_email']
    
    try:
        data = request.get_json()
        local_favorites = data.get('favorites', [])
        
        # Supprimer tous les favoris existants
        Favorite.query.filter_by(user_email=user_email).delete()
        
        # Ajouter les favoris locaux
        for fav_data in local_favorites:
            new_fav = Favorite(
                user_email=user_email,
                product_type=fav_data.get('product_type', 'predefined'),
                product_id=fav_data['product_id'],
                product_data=json.dumps(fav_data.get('product_data', {}))
            )
            db.session.add(new_fav)
        
        db.session.commit()
        return jsonify({'message': 'Favoris synchronisés avec succès'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ===== Routes Admin =====
def is_admin():
    """Vérifie si l'utilisateur connecté est un administrateur"""
    if not session.get('user_email'):
        return False
    user = get_user_by_email(session['user_email'])
    return user and user.is_admin

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Page de connexion administrateur"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Vérifier les informations dans la base de données
        user = get_user_by_email_or_username(email)
        if user and user.password_hash == hash_password(password):
            session['user_email'] = user.email
            session['user_nom'] = user.nom
            session['user_prenom'] = user.prenom
            session['user_username'] = user.username
            session['user_id'] = user.id
            session['is_admin'] = True
            flash('Connexion administrateur réussie !', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Email ou mot de passe incorrect', 'error')

    return render_template('admin/admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    """Dashboard administrateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Statistiques de base
    try:
        total_users = User.query.filter_by(is_admin=False).count()
        total_orders = Order.query.count()
        total_products = len(get_global_data()['PRODUITS_EXEMPLE'])
        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    except:
        total_users = 0
        total_orders = 0
        total_products = 0
        recent_orders = []

    return render_template('admin/admin_dashboard.html',
                         total_users=total_users,
                         total_orders=total_orders,
                         total_products=total_products,
                         recent_orders=recent_orders)

# ===== Routes Gestion Produits =====

@app.route('/admin/products')
def admin_products():
    """Liste des produits"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Récupérer tous les types de produits
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    # Query de base
    query = PredefinedProduct.query

    if search_query:
        query = query.filter(
            db.or_(
                PredefinedProduct.name.ilike(f'%{search_query}%'),
                PredefinedProduct.description.ilike(f'%{search_query}%')
            )
        )

    if category_filter:
        # Filtrer par catégorie (recherche dans le JSON)
        query = query.filter(PredefinedProduct.categories.like(f'%{category_filter}%'))

    products = query.order_by(PredefinedProduct.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # Récupérer les catégories pour le filtre
    categories = ProductCategory.query.all()

    return render_template('admin/admin_products.html',
                         products=products,
                         categories=categories,
                         search_query=search_query,
                         category_filter=category_filter)

@app.route('/admin/products/add', methods=['GET', 'POST'])
def admin_product_add():
    """Ajouter un nouveau produit"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        container_type_id = request.form.get('container_type_id')
        price = request.form.get('price')
        image_url = request.form.get('image_url')
        is_customizable = request.form.get('is_customizable') == 'on'
        is_internal = request.form.get('is_internal') == 'on'
        categories = request.form.getlist('categories')
        quantity_per_category = request.form.get('quantity_per_category', 1, type=int)
        initial_stock = request.form.get('initial_stock', 0, type=int)
        current_stock = request.form.get('current_stock', 0, type=int)

        # Validation
        required_fields = [name, price]
            
        if not all(required_fields):
            flash('Veuillez remplir tous les champs obligatoires', 'error')
            return redirect(request.url)

        try:
            price = float(price)
        except ValueError:
            flash('Prix invalide', 'error')
            return redirect(request.url)

        # Créer le produit
        new_product = PredefinedProduct(
            name=name,
            description=description,
            container_type_id=None,  # Plus de container_type_id dans le formulaire
            price=price,
            image_url=image_url,
            is_customizable=is_customizable,
            is_internal=is_internal,
            categories=json.dumps(categories) if categories else None,
            quantity_per_category=quantity_per_category,
            initial_stock=initial_stock,
            current_stock=current_stock
        )

        try:
            db.session.add(new_product)
            db.session.commit()
            flash('Produit créé avec succès', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la création du produit', 'error')

    # Données pour le formulaire
    container_types = ContainerType.query.all()
    categories = ProductCategory.query.all()

    return render_template('admin/admin_product_add.html',
                         container_types=container_types,
                         categories=categories)

@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
def admin_product_edit(product_id):
    """Modifier un produit"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    product = PredefinedProduct.query.get_or_404(product_id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        container_type_id = request.form.get('container_type_id')
        price = request.form.get('price')
        image_url = request.form.get('image_url')
        is_customizable = request.form.get('is_customizable') == 'on'
        is_internal = request.form.get('is_internal') == 'on'
        categories = request.form.getlist('categories')
        quantity_per_category = request.form.get('quantity_per_category', 1, type=int)
        initial_stock = request.form.get('initial_stock', 0, type=int)
        current_stock = request.form.get('current_stock', 0, type=int)

        # Validation
        required_fields = [name, price]
            
        if not all(required_fields):
            flash('Veuillez remplir tous les champs obligatoires', 'error')
            return redirect(request.url)

        try:
            price = float(price)
        except ValueError:
            flash('Prix invalide', 'error')
            return redirect(request.url)

        # Mettre à jour le produit
        product.name = name
        product.description = description
        product.container_type_id = None  # Plus de container_type_id dans le formulaire
        product.price = price
        product.image_url = image_url
        product.is_customizable = is_customizable
        product.is_internal = is_internal
        product.categories = json.dumps(categories) if categories else None
        product.quantity_per_category = quantity_per_category
        product.initial_stock = initial_stock
        product.current_stock = current_stock

        try:
            db.session.commit()
            flash('Produit modifié avec succès', 'success')
            return redirect(url_for('admin_product_detail', product_id=product.id))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la modification du produit', 'error')

    # Données pour le formulaire
    container_types = ContainerType.query.all()
    categories = ProductCategory.query.all()
    selected_categories = json.loads(product.categories) if product.categories else []

    return render_template('admin/admin_product_edit.html',
                         product=product,
                         container_types=container_types,
                         categories=categories,
                         selected_categories=selected_categories)

@app.route('/admin/products/<int:product_id>')
def admin_product_detail(product_id):
    """Détails d'un produit"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    product = PredefinedProduct.query.get_or_404(product_id)
    categories = json.loads(product.categories) if product.categories else []

    return render_template('admin/admin_product_detail.html',
                         product=product,
                         categories=categories)

@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
def admin_product_delete(product_id):
    """Supprimer un produit"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    product = PredefinedProduct.query.get_or_404(product_id)

    try:
        db.session.delete(product)
        db.session.commit()
        flash('Produit supprimé avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de la suppression du produit', 'error')

    return redirect(url_for('admin_products'))

@app.route('/admin/finance')
def admin_finance():
    """Page finance administrateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Statistiques financières
    try:
        # Revenus totaux
        total_revenue = db.session.query(db.func.sum(Order.total_price)).scalar() or 0

        # Revenus par mode de paiement
        payment_methods = db.session.query(
            Order.payment_method,
            db.func.count(Order.id).label('count'),
            db.func.sum(Order.total_price).label('total')
        ).group_by(Order.payment_method).all()

        # Statistiques des commandes
        total_orders = Order.query.count()
        pending_orders = Order.query.filter_by(status='pending').count()
        confirmed_orders = Order.query.filter_by(status='confirmed').count()
        shipped_orders = Order.query.filter_by(status='shipped').count()
        delivered_orders = Order.query.filter_by(status='delivered').count()
        cancelled_orders = Order.query.filter_by(status='cancelled').count()

        # Revenus du mois en cours
        from datetime import datetime, timedelta
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_revenue = db.session.query(db.func.sum(Order.total_price)).filter(
            Order.created_at >= start_of_month
        ).scalar() or 0

        # Dépenses totales
        total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0

        # Dépenses du mois en cours
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
            Expense.date >= start_of_month
        ).scalar() or 0

        # Moyenne mensuelle des dépenses (sur les 6 derniers mois)
        six_months_ago = datetime.utcnow() - timedelta(days=180)
        total_expenses_last_6_months = db.session.query(db.func.sum(Expense.amount)).filter(
            Expense.date >= six_months_ago
        ).scalar() or 0
        avg_monthly_expenses = total_expenses_last_6_months / 6 if total_expenses_last_6_months > 0 else 0

        # Plus grosse dépense
        max_expense = db.session.query(db.func.max(Expense.amount)).scalar() or 0

        # Dernières dépenses (5 plus récentes)
        recent_expenses = Expense.query.order_by(Expense.created_at.desc()).limit(5).all()

        # Top produits vendus (basé sur les order_items)
        top_products = db.session.query(
            OrderItem.product_name,
            db.func.sum(OrderItem.quantity).label('total_quantity'),
            db.func.sum(OrderItem.price * OrderItem.quantity).label('total_revenue')
        ).group_by(OrderItem.product_name).order_by(db.desc('total_quantity')).limit(10).all()

    except Exception as e:
        print(f"Erreur lors du calcul des statistiques financières: {e}")
        total_revenue = 0
        payment_methods = []
        total_orders = 0
        pending_orders = 0
        confirmed_orders = 0
        shipped_orders = 0
        delivered_orders = 0
        cancelled_orders = 0
        monthly_revenue = 0
        total_expenses = 0
        monthly_expenses = 0
        avg_monthly_expenses = 0
        max_expense = 0
        recent_expenses = []
        top_products = []

    return render_template('admin/admin_finance.html',
                         total_revenue=total_revenue,
                         payment_methods=payment_methods,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         confirmed_orders=confirmed_orders,
                         shipped_orders=shipped_orders,
                         delivered_orders=delivered_orders,
                         cancelled_orders=cancelled_orders,
                         monthly_revenue=monthly_revenue,
                         total_expenses=total_expenses,
                         monthly_expenses=monthly_expenses,
                         avg_monthly_expenses=avg_monthly_expenses,
                         max_expense=max_expense,
                         recent_expenses=recent_expenses,
                         top_products=top_products)

# Routes pour la gestion des contenants

@app.route('/admin/logout')
def admin_logout():
    """Déconnexion administrateur"""
    session.clear()
    flash('Déconnexion réussie', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():
    """Profil de l'administrateur connecté"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Récupérer l'utilisateur admin connecté
    user = User.query.filter_by(email=session['user_email']).first()
    if not user:
        flash('Utilisateur non trouvé', 'error')
        return redirect(url_for('admin_logout'))

    if request.method == 'POST':
        # Mise à jour du profil
        nom = request.form.get('nom')
        prenom = request.form.get('prenom')
        telephone = request.form.get('telephone')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Déterminer si l'utilisateur modifie les infos personnelles ou le mot de passe
        modifying_personal_info = nom is not None or prenom is not None or telephone is not None
        changing_password = new_password and new_password.strip()

        # Validation pour les informations personnelles
        if modifying_personal_info:
            if not nom or not prenom:
                flash('Le nom et le prénom sont obligatoires', 'error')
                return redirect(url_for('admin_profile'))

            # Mise à jour des informations de base
            user.nom = nom
            user.prenom = prenom
            user.telephone = telephone

        # Changement de mot de passe si demandé
        if changing_password:
            if not current_password:
                flash('Le mot de passe actuel est requis pour changer de mot de passe', 'error')
                return redirect(url_for('admin_profile'))

            if not check_password_hash(user.password_hash, current_password):
                flash('Le mot de passe actuel est incorrect', 'error')
                return redirect(url_for('admin_profile'))

            if new_password != confirm_password:
                flash('Les nouveaux mots de passe ne correspondent pas', 'error')
                return redirect(url_for('admin_profile'))

            if len(new_password) < 6:
                flash('Le nouveau mot de passe doit contenir au moins 6 caractères', 'error')
                return redirect(url_for('admin_profile'))

            user.password_hash = hash_password(new_password)
            flash('Mot de passe changé avec succès', 'success')

        # Si aucune modification n'a été faite
        if not modifying_personal_info and not changing_password:
            flash('Aucune modification détectée', 'warning')
            return redirect(url_for('admin_profile'))

        try:
            db.session.commit()
            if modifying_personal_info:
                flash('Profil mis à jour avec succès', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la mise à jour du profil', 'error')

        return redirect(url_for('admin_profile'))

    return render_template('admin/admin_profile.html', user=user)

@app.route('/admin/users')
def admin_users():
    """Liste des utilisateurs (non-administrateurs)"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Récupérer uniquement les utilisateurs non-administrateurs avec pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Recherche
    search_query = request.args.get('search', '').strip()
    query = User.query.filter_by(is_admin=False)

    if search_query:
        # Rechercher dans nom, prénom et email
        query = query.filter(
            db.or_(
                User.nom.ilike(f'%{search_query}%'),
                User.prenom.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%')
            )
        )

    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/admin_users.html',
                         users=users,
                         search_query=search_query)

@app.route('/admin/admins')
def admin_admins():
    """Liste des administrateurs"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Récupérer uniquement les administrateurs avec pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Recherche
    search_query = request.args.get('search', '').strip()
    query = User.query.filter_by(is_admin=True)

    if search_query:
        # Rechercher dans nom, prénom et email
        query = query.filter(
            db.or_(
                User.nom.ilike(f'%{search_query}%'),
                User.prenom.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%')
            )
        )

    admins = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/admin_admins.html',
                         users=admins,
                         search_query=search_query)

@app.route('/admin/admins/add', methods=['GET', 'POST'])
def admin_admin_add():
    """Ajouter un nouvel administrateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        nom = request.form.get('nom')
        prenom = request.form.get('prenom')
        telephone = request.form.get('telephone', '')

        # Validation
        if not all([email, password, nom, prenom]):
            flash('Veuillez remplir tous les champs obligatoires', 'error')
            return redirect(request.url)

        if get_user_by_email(email):
            flash('Un utilisateur avec cet email existe déjà', 'error')
            return redirect(request.url)

        if username and get_user_by_username(username):
            flash('Un utilisateur avec ce nom d\'utilisateur existe déjà', 'error')
            return redirect(request.url)

        if len(password) < 6:
            flash('Le mot de passe doit contenir au moins 6 caractères', 'error')
            return redirect(request.url)

        # Créer le nouvel administrateur
        new_admin = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            nom=nom,
            prenom=prenom,
            telephone=telephone,
            is_admin=True
        )

        try:
            db.session.add(new_admin)
            db.session.commit()
            flash('Administrateur créé avec succès', 'success')
            return redirect(url_for('admin_admin_detail', admin_id=new_admin.id))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la création de l\'administrateur', 'error')

    return render_template('admin/admin_admin_add.html')

@app.route('/admin/users/<int:user_id>')
def admin_user_detail(user_id):
    """Détails d'un utilisateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    user = User.query.get_or_404(user_id)

    # Statistiques de l'utilisateur
    total_orders = len(user.orders)
    total_cart_items = len(user.cart_items)
    total_favorites = len(user.favorites)
    total_addresses = len(user.addresses)

    # Trier les commandes par date décroissante (plus récentes en premier)
    sorted_orders = sorted(user.orders, key=lambda x: x.created_at, reverse=True)

    # Parser les données JSON des favoris pour le template
    favorites_data = []
    for favorite in user.favorites:
        try:
            product_data = json.loads(favorite.product_data) if favorite.product_data else {}
        except (json.JSONDecodeError, TypeError):
            product_data = {}
        
        favorites_data.append({
            'id': favorite.id,
            'product_type': favorite.product_type,
            'product_id': favorite.product_id,
            'product_data': product_data,
            'added_at': favorite.added_at
        })

    # Parser les données JSON du panier pour le template
    cart_data = []
    for cart_item in user.cart_items:
        try:
            product_data = json.loads(cart_item.product_data) if cart_item.product_data else {}
        except (json.JSONDecodeError, TypeError):
            product_data = {}
        
        cart_data.append({
            'id': cart_item.id,
            'product_type': cart_item.product_type,
            'product_id': cart_item.product_id,
            'product_data': product_data,
            'quantity': cart_item.quantity,
            'added_at': cart_item.added_at
        })

    # Date actuelle pour les calculs
    current_date = datetime.now().date()

    return render_template('admin/admin_user_detail.html',
                         user=user,
                         total_orders=total_orders,
                         total_cart_items=total_cart_items,
                         total_favorites=total_favorites,
                         total_addresses=total_addresses,
                         favorites_data=favorites_data,
                         cart_data=cart_data,
                         sorted_orders=sorted_orders,
                         current_date=current_date)

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
def admin_user_edit(user_id):
    """Modifier un utilisateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        # Mettre à jour les informations
        user.email = request.form.get('email')
        user.username = request.form.get('username')
        user.nom = request.form.get('nom')
        user.prenom = request.form.get('prenom')
        user.telephone = request.form.get('telephone')

        try:
            db.session.commit()
            flash('Utilisateur modifié avec succès', 'success')
            return redirect(url_for('admin_user_detail', user_id=user.id))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la modification', 'error')

    return render_template('admin/admin_user_edit.html', user=user)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
def admin_user_delete(user_id):
    """Supprimer définitivement un utilisateur et toutes ses données"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    user = User.query.get_or_404(user_id)

    # Empêcher la suppression de l'admin actuel
    if user.id == session.get('user_id'):
        flash('Vous ne pouvez pas vous supprimer vous-même', 'error')
        return redirect(url_for('admin_users'))

    try:
        # Supprimer toutes les données liées à l'utilisateur
        # 1. Sessions mobiles
        MobileSession.query.filter_by(user_email=user.email).delete()

        # 2. Items du panier
        CartItem.query.filter_by(user_email=user.email).delete()

        # 3. Favoris
        Favorite.query.filter_by(user_email=user.email).delete()

        # 4. Adresses
        Address.query.filter_by(user_email=user.email).delete()

        # 5. Commandes et leurs items (supprimer les items d'abord)
        orders = Order.query.filter_by(user_email=user.email).all()
        for order in orders:
            OrderItem.query.filter_by(order_id=order.id).delete()
        Order.query.filter_by(user_email=user.email).delete()

        # 6. Supprimer l'utilisateur
        db.session.delete(user)
        db.session.commit()

        flash('Utilisateur supprimé définitivement avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de la suppression définitive de l\'utilisateur', 'error')

    return redirect(url_for('admin_users'))

@app.route('/admin/admins/<int:admin_id>')
def admin_admin_detail(admin_id):
    """Détails d'un administrateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    admin = User.query.filter_by(id=admin_id, is_admin=True).first_or_404()

    # Statistiques de l'administrateur
    total_orders = len(admin.orders)
    total_cart_items = len(admin.cart_items)
    total_favorites = len(admin.favorites)
    total_addresses = len(admin.addresses)

    # Parser les données JSON des favoris pour le template
    favorites_data = []
    for favorite in admin.favorites:
        try:
            product_data = json.loads(favorite.product_data) if favorite.product_data else {}
        except (json.JSONDecodeError, TypeError):
            product_data = {}
        
        favorites_data.append({
            'id': favorite.id,
            'product_type': favorite.product_type,
            'product_id': favorite.product_id,
            'product_data': product_data,
            'added_at': favorite.added_at
        })

    # Date actuelle pour les calculs
    current_date = datetime.now().date()

    return render_template('admin/admin_admin_detail.html',
                         user=admin,
                         total_orders=total_orders,
                         total_cart_items=total_cart_items,
                         total_favorites=total_favorites,
                         total_addresses=total_addresses,
                         favorites_data=favorites_data,
                         current_date=current_date)

@app.route('/admin/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
def admin_admin_edit(admin_id):
    """Modifier un administrateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    admin = User.query.filter_by(id=admin_id, is_admin=True).first_or_404()

    if request.method == 'POST':
        # Mettre à jour les informations
        admin.email = request.form.get('email')
        admin.username = request.form.get('username')
        admin.nom = request.form.get('nom')
        admin.prenom = request.form.get('prenom')
        admin.telephone = request.form.get('telephone')

        # Mettre à jour le mot de passe si fourni (seulement pour son propre compte)
        password = request.form.get('password')
        if password and password.strip():
            if session.get('user_id') != admin.id:
                flash('Vous ne pouvez modifier que votre propre mot de passe', 'error')
                return redirect(request.url)
            if len(password) < 6:
                flash('Le mot de passe doit contenir au moins 6 caractères', 'error')
                return redirect(request.url)
            admin.password_hash = hash_password(password)

        # Les admins gardent toujours leur statut admin

        try:
            db.session.commit()
            flash('Administrateur modifié avec succès', 'success')
            return redirect(url_for('admin_admin_detail', admin_id=admin.id))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la modification', 'error')

    return render_template('admin/admin_admin_edit.html', user=admin)

@app.route('/admin/admins/<int:admin_id>/delete', methods=['POST'])
def admin_admin_delete(admin_id):
    """Supprimer un administrateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    admin = User.query.filter_by(id=admin_id, is_admin=True).first_or_404()

    # Empêcher la suppression de l'admin actuel
    if admin.id == session.get('user_id'):
        flash('Vous ne pouvez pas vous supprimer vous-même', 'error')
        return redirect(url_for('admin_admins'))

    try:
        # Retirer le statut admin avant suppression
        admin.is_admin = False
        db.session.commit()
        
        flash('Administrateur supprimé avec succès (statut admin retiré)', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de la suppression', 'error')

    return redirect(url_for('admin_admins'))

@app.route('/admin/admins/<int:admin_id>/toggle-admin', methods=['POST'])
def admin_admin_toggle_admin(admin_id):
    """Retirer les droits admin à un administrateur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    admin = User.query.filter_by(id=admin_id, is_admin=True).first_or_404()

    # Empêcher de retirer les droits admin à soi-même
    if admin.id == session.get('user_id'):
        flash('Vous ne pouvez pas modifier vos propres droits admin', 'error')
        return redirect(url_for('admin_admins'))

    admin.is_admin = False
    db.session.commit()

    flash(f'Les droits administrateur ont été retirés à {admin.prenom} {admin.nom}', 'success')

    return redirect(url_for('admin_admins'))

@app.route('/admin/categories')
def admin_categories():
    """Gestion des catégories de produits"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    # Récupérer les catégories avec pagination et recherche
    query = ProductCategory.query

    if search:
        query = query.filter(ProductCategory.name.ilike(f'%{search}%'))

    categories = query.paginate(page=page, per_page=10, error_out=False)

    return render_template('admin/admin_categories.html',
                         categories=categories,
                         search=search)

@app.route('/admin/categories/add', methods=['GET', 'POST'])
def admin_category_add():
    """Ajouter une catégorie"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')

        if not name:
            flash('Le nom de la catégorie est requis', 'error')
            return redirect(url_for('admin_category_add'))

        # Vérifier si la catégorie existe déjà
        existing_category = ProductCategory.query.filter_by(name=name).first()
        if existing_category:
            flash('Une catégorie avec ce nom existe déjà', 'error')
            return redirect(url_for('admin_category_add'))

        category_id = slugify(name)

        category = ProductCategory(
            id=category_id,
            name=name,
            description=description
        )
        db.session.add(category)
        db.session.commit()

        flash('Catégorie ajoutée avec succès', 'success')
        return redirect(url_for('admin_categories'))

    return render_template('admin/admin_category_add.html')

@app.route('/admin/categories/<category_id>/edit', methods=['GET', 'POST'])
def admin_category_edit(category_id):
    """Modifier une catégorie"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    category = ProductCategory.query.get_or_404(category_id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')

        if not name:
            flash('Le nom de la catégorie est requis', 'error')
            return redirect(url_for('admin_category_edit', category_id=category_id))

        # Vérifier si le nom existe déjà (sauf pour cette catégorie)
        existing_category = ProductCategory.query.filter_by(name=name).filter(ProductCategory.id != category_id).first()
        if existing_category:
            flash('Une catégorie avec ce nom existe déjà', 'error')
            return redirect(url_for('admin_category_edit', category_id=category_id))

        category.name = name
        category.description = description
        db.session.commit()

        flash('Catégorie modifiée avec succès', 'success')
        return redirect(url_for('admin_categories'))

    return render_template('admin/admin_category_edit.html', category=category)

@app.route('/admin/categories/<category_id>/delete', methods=['GET', 'POST'])
def admin_category_delete(category_id):
    """Supprimer une catégorie"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    category = ProductCategory.query.get_or_404(category_id)

    # Récupérer les produits associés pour les afficher dans le template
    associated_products = Product.query.filter_by(category_id=category_id).all()
    products_count = len(associated_products)

    # Récupérer les autres catégories pour l'option de déplacement
    other_categories = ProductCategory.query.filter(ProductCategory.id != category_id).all()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'delete_products':
            # Supprimer tous les produits associés puis la catégorie
            for product in associated_products:
                db.session.delete(product)
            db.session.delete(category)
            db.session.commit()
            flash(f'Catégorie et {products_count} produit(s) supprimé(s) avec succès', 'success')

        elif action == 'move_products':
            target_category_id = request.form.get('target_category')
            if not target_category_id:
                flash('Veuillez sélectionner une catégorie cible', 'error')
                return redirect(url_for('admin_category_delete', category_id=category_id))

            # Vérifier que la catégorie cible existe
            target_category = db.session.get(ProductCategory, target_category_id)
            if not target_category:
                flash('Catégorie cible introuvable', 'error')
                return redirect(url_for('admin_category_delete', category_id=category_id))

            # Déplacer tous les produits vers la nouvelle catégorie
            for product in associated_products:
                product.category_id = target_category_id

            # Supprimer la catégorie
            db.session.delete(category)
            db.session.commit()
            flash(f'Catégorie supprimée et {products_count} produit(s) déplacé(s) vers "{target_category.name}"', 'success')

        else:
            flash('Action non reconnue', 'error')
            return redirect(url_for('admin_category_delete', category_id=category_id))

        return redirect(url_for('admin_categories'))

    return render_template('admin/admin_category_delete.html',
                         category=category,
                         products=associated_products,
                         products_count=products_count,
                         other_categories=other_categories)

@app.route('/admin/containers')
def admin_containers():
    """Gestion des conteneurs"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')

    # Récupérer les conteneurs avec pagination et recherche
    query = Container.query

    if search_query:
        query = query.filter(Container.name.ilike(f'%{search_query}%'))

    containers = query.paginate(page=page, per_page=10, error_out=False)

    return render_template('admin/admin_containers.html',
                         containers=containers,
                         search_query=search_query)

@app.route('/admin/containers/add', methods=['GET', 'POST'])
def admin_container_add():
    """Ajouter un conteneur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form.get('name')
        container_type_id = request.form.get('container_type_id')
        description = request.form.get('description')
        price = request.form.get('price')
        max_products = request.form.get('max_products')
        image_url = request.form.get('image_url')
        is_customizable = request.form.get('is_customizable') == '1'

        if not name or not container_type_id:
            flash('Le nom et le type de conteneur sont requis', 'error')
            return redirect(url_for('admin_container_add'))

        try:
            price = float(price) if price else 0.0
            max_products = int(max_products) if max_products else 10
        except ValueError:
            flash('Prix ou nombre maximum de produits invalide', 'error')
            return redirect(url_for('admin_container_add'))

        container = Container(
            name=name,
            container_type_id=container_type_id,
            description=description,
            price=price,
            max_products=max_products,
            image_url=image_url,
            is_customizable=is_customizable
        )
        db.session.add(container)
        db.session.flush()  # Pour obtenir l'ID du container

        # Traiter les produits sélectionnés
        selected_products = []
        for key, value in request.form.items():
            if key.startswith('selected_products_'):
                category_id = key.replace('selected_products_', '').replace('[]', '')
                product_ids = request.form.getlist(key)
                quantities = request.form.getlist(f'quantities_{category_id}[]')
                
                for i, product_id in enumerate(product_ids):
                    quantity = int(quantities[i]) if i < len(quantities) else 1
                    container_product = ContainerProduct(
                        container_id=container.id,
                        product_id=int(product_id),
                        quantity=quantity
                    )
                    db.session.add(container_product)

        db.session.commit()

        flash('Conteneur ajouté avec succès', 'success')
        return redirect(url_for('admin_containers'))

    # Récupérer les types de conteneurs, catégories et produits pour le formulaire
    container_types = ContainerType.query.all()
    categories = ProductCategory.query.all()
    products = PredefinedProduct.query.filter(PredefinedProduct.is_internal == False).all()
    return render_template('admin/admin_container_add.html', container_types=container_types, categories=categories, products=products)

@app.route('/admin/containers/<int:container_id>')
def admin_container_detail(container_id):
    """Détails d'un conteneur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    container = Container.query.get_or_404(container_id)
    
    # Calculer le prix total estimé (prix du contenant + prix des produits)
    total_price = container.price
    if hasattr(container, 'container_products'):
        for cp in container.container_products:
            total_price += cp.product.price * cp.quantity
    
    return render_template('admin/admin_container_detail.html', container=container, total_price=total_price)

@app.route('/admin/containers/<int:container_id>/edit', methods=['GET', 'POST'])
def admin_container_edit(container_id):
    """Modifier un conteneur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    container = Container.query.get_or_404(container_id)

    if request.method == 'POST':
        name = request.form.get('name')
        container_type_id = request.form.get('container_type_id')
        description = request.form.get('description')
        price = request.form.get('price')
        max_products = request.form.get('max_products')
        image_url = request.form.get('image_url')
        is_customizable = request.form.get('is_customizable') == '1'

        if not name or not container_type_id:
            flash('Le nom et le type de conteneur sont requis', 'error')
            return redirect(url_for('admin_container_edit', container_id=container_id))

        try:
            price = float(price) if price else container.price
            max_products = int(max_products) if max_products else container.max_products
        except ValueError:
            flash('Prix ou nombre maximum de produits invalide', 'error')
            return redirect(url_for('admin_container_edit', container_id=container_id))

        container.name = name
        container.container_type_id = container_type_id
        container.description = description
        container.price = price
        container.max_products = max_products
        container.image_url = image_url
        container.is_customizable = is_customizable

        # Supprimer les anciens produits
        ContainerProduct.query.filter_by(container_id=container.id).delete()

        # Récupérer toutes les catégories sélectionnées
        selected_categories = request.form.getlist('categories')
        print(f"DEBUG: Selected categories: {selected_categories}")

        # Pour chaque catégorie sélectionnée, récupérer les produits et quantités
        for category_id in selected_categories:
            # Récupérer les produits sélectionnés pour cette catégorie
            selected_products_key = f'selected_products_{category_id}[]'
            quantities_key = f'quantities_{category_id}[]'

            product_ids = request.form.getlist(selected_products_key)
            quantities = request.form.getlist(quantities_key)

            print(f"DEBUG: Category {category_id}: products={product_ids}, quantities={quantities}")

            # Les quantités et produits devraient maintenant être dans le même ordre
            for i, product_id in enumerate(product_ids):
                try:
                    quantity = int(quantities[i]) if i < len(quantities) else 1
                    container_product = ContainerProduct(
                        container_id=container.id,
                        product_id=int(product_id),
                        quantity=quantity
                    )
                    db.session.add(container_product)
                    print(f"DEBUG: Added product {product_id} with quantity {quantity}")
                except (ValueError, IndexError) as e:
                    print(f"DEBUG: Error adding product {product_id}: {e}")
                    continue

        db.session.commit()

        flash('Conteneur modifié avec succès', 'success')
        return redirect(url_for('admin_containers'))

    # Récupérer les types de conteneurs, catégories et produits pour le formulaire
    container_types = ContainerType.query.all()
    categories = ProductCategory.query.all()
    products = PredefinedProduct.query.filter(PredefinedProduct.is_internal == False).all()
    
    # Récupérer les catégories déjà sélectionnées (depuis les produits du container)
    selected_categories = set()
    for cp in container.products:
        if cp.product.categories:
            try:
                product_cats = json.loads(cp.product.categories)
                selected_categories.update(product_cats)
            except:
                pass
    
    return render_template('admin/admin_container_edit.html', 
                         container=container, 
                         container_types=container_types,
                         categories=categories,
                         products=products,
                         selected_categories=selected_categories)

@app.route('/admin/containers/<int:container_id>/delete', methods=['POST'])
def admin_container_delete(container_id):
    """Supprimer un conteneur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    container = Container.query.get_or_404(container_id)
    
    db.session.delete(container)
    db.session.commit()

    flash('Conteneur supprimé avec succès', 'success')
    return redirect(url_for('admin_containers'))

@app.route('/admin/container-types')
def admin_container_types():
    """Gestion des types de conteneurs"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    # Récupérer les types de conteneurs avec pagination et recherche
    query = ContainerType.query

    if search:
        query = query.filter(ContainerType.name.ilike(f'%{search}%'))

    container_types = query.paginate(page=page, per_page=10, error_out=False)

    return render_template('admin/admin_container_types.html',
                         container_types=container_types,
                         search=search)

@app.route('/admin/container-types/add', methods=['GET', 'POST'])
def admin_container_type_add():
    """Ajouter un type de conteneur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form.get('name')
        base_price = request.form.get('base_price', type=float)
        max_products = request.form.get('max_products', type=int)
        allowed_categories = request.form.getlist('allowed_categories[]')
        image_url = request.form.get('image_url')

        if not name or base_price is None or max_products is None:
            flash('Le nom, le prix de base et le nombre maximum de produits sont requis', 'error')
            return redirect(url_for('admin_container_type_add'))

        # Générer un ID basé sur le nom
        container_type_id = name.lower().replace(' ', '_').replace('é', 'e').replace('è', 'e').replace('à', 'a').replace('ç', 'c')

        # Vérifier que l'ID n'existe pas déjà
        if db.session.get(ContainerType, container_type_id):
            flash('Un type de contenant avec cet ID existe déjà', 'error')
            return redirect(url_for('admin_container_type_add'))

        container_type = ContainerType(
            id=container_type_id,
            name=name,
            base_price=base_price,
            max_products=max_products,
            allowed_categories=json.dumps(allowed_categories) if allowed_categories else None,
            image_url=image_url if image_url else None
        )
        db.session.add(container_type)
        db.session.commit()

        flash('Type de conteneur ajouté avec succès', 'success')
        return redirect(url_for('admin_container_types'))

    return render_template('admin/admin_container_type_add.html', categories=ProductCategory.query.all())

@app.route('/admin/container-types/<container_type_id>/edit', methods=['GET', 'POST'])
def admin_container_type_edit(container_type_id):
    """Modifier un type de conteneur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    container_type = ContainerType.query.get_or_404(container_type_id)

    if request.method == 'POST':
        name = request.form.get('name')
        base_price = request.form.get('base_price', type=float)
        max_products = request.form.get('max_products', type=int)
        allowed_categories = request.form.getlist('allowed_categories[]')
        image_url = request.form.get('image_url')

        if not name or base_price is None or max_products is None:
            flash('Le nom, le prix de base et le nombre maximum de produits sont requis', 'error')
            return redirect(url_for('admin_container_type_edit', container_type_id=container_type_id))

        container_type.name = name
        container_type.base_price = base_price
        container_type.max_products = max_products
        container_type.allowed_categories = json.dumps(allowed_categories) if allowed_categories else None
        container_type.image_url = image_url if image_url else None
        db.session.commit()

        flash('Type de conteneur modifié avec succès', 'success')
        return redirect(url_for('admin_container_types'))

    # Récupérer les catégories sélectionnées
    selected_categories = []
    if container_type.allowed_categories:
        try:
            selected_categories = json.loads(container_type.allowed_categories)
        except:
            selected_categories = []

    return render_template('admin/admin_container_type_edit.html', 
                         container_type=container_type, 
                         categories=ProductCategory.query.all(),
                         selected_categories=selected_categories)

@app.route('/admin/container-types/<container_type_id>/delete', methods=['POST'])
def admin_container_type_delete(container_type_id):
    """Supprimer un type de conteneur"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    container_type = ContainerType.query.get_or_404(container_type_id)
    
    # Vérifier s'il y a des contenants qui utilisent ce type
    if container_type.containers:
        flash(f'Impossible de supprimer ce type de conteneur car {len(container_type.containers)} contenant(s) l\'utilise(nt) encore.', 'error')
        return redirect(url_for('admin_container_types'))
    
    db.session.delete(container_type)
    db.session.commit()

    flash('Type de conteneur supprimé avec succès', 'success')
    return redirect(url_for('admin_container_types'))

@app.route('/admin/orders')
def admin_orders():
    """Gestion des commandes"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')

    # Récupérer les commandes avec pagination et filtres
    query = Order.query.join(User, Order.user_email == User.email).add_columns(
        User.nom, User.prenom, User.email
    )

    if search:
        query = query.filter(
            sql_or(
                Order.id.ilike(f'%{search}%'),
                User.nom.ilike(f'%{search}%'),
                User.prenom.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )

    if status_filter:
        query = query.filter(Order.status == status_filter)

    # Trier par date décroissante
    query = query.order_by(Order.created_at.desc())

    orders = query.paginate(page=page, per_page=20, error_out=False)

    # Statistiques
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    confirmed_orders = Order.query.filter_by(status='confirmed').count()
    shipped_orders = Order.query.filter_by(status='shipped').count()
    delivered_orders = Order.query.filter_by(status='delivered').count()

    return render_template('admin/admin_orders.html',
                         orders=orders,
                         search=search,
                         status_filter=status_filter,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         confirmed_orders=confirmed_orders,
                         shipped_orders=shipped_orders,
                         delivered_orders=delivered_orders)

@app.route('/admin/orders/<int:order_id>')
def admin_order_detail(order_id):
    """Détails d'une commande"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    order = Order.query.get_or_404(order_id)
    user = User.query.filter_by(email=order.user_email).first()
    
    # Récupérer les données des produits pour afficher les noms
    data = get_global_data()
    
    return render_template('admin/admin_order_detail.html', 
                         order=order, 
                         user=user,
                         produits_exemple=data['PRODUITS_EXEMPLE'])

@app.route('/admin/orders/<int:order_id>/status', methods=['POST'])
def admin_order_update_status(order_id):
    """Mettre à jour le statut d'une commande"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    old_status = order.status
    
    if new_status in ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']:
        order.status = new_status
        order.updated_at = datetime.utcnow()
        
        # Gestion du stock : décrémenter quand la commande est marquée comme livrée
        if new_status == 'delivered' and old_status != 'delivered':
            for item in order.order_items:
                if item.product_id:
                    product = None
                    try:
                        # Essayer d'abord avec l'ID direct (pour les nouvelles commandes)
                        if item.product_id.startswith('predefined_'):
                            actual_id = int(item.product_id.replace('predefined_', ''))
                            product = db.session.get(PredefinedProduct, actual_id)
                        else:
                            actual_id = int(item.product_id)
                            product = db.session.get(PredefinedProduct, actual_id)
                        
                        # Si l'ID direct ne marche pas, essayer de trouver par nom (pour les anciennes commandes)
                        if not product and item.product_name:
                            product = PredefinedProduct.query.filter_by(name=item.product_name).first()
                        
                        if product and product.current_stock is not None and product.current_stock > 0:
                            old_stock = product.current_stock
                            product.current_stock = max(0, product.current_stock - item.quantity)
                            db.session.add(product)
                            print(f"✅ Stock décrémenté pour produit {product.name} (ID: {product.id}): {old_stock} -> {product.current_stock} (quantité commandée: {item.quantity})")
                        else:
                            print(f"⚠️ Produit non trouvé ou stock insuffisant pour {item.product_name} (ID: {item.product_id})")
                    except (ValueError, TypeError) as e:
                        print(f"❌ Erreur traitement stock pour product_id {item.product_id}: {e}")
                        pass  # Ignore si l'ID n'est pas valide
        
        db.session.commit()
        flash(f'Statut de la commande mis à jour : {new_status}', 'success')
    else:
        flash('Statut invalide', 'error')
    
    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/settings')
def admin_settings():
    """Paramètres de l'application"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Charger les paramètres existants
    settings = load_settings()
    
    # Convertir les valeurs shipping en int pour éviter les problèmes d'affichage
    if 'shipping' in settings:
        for key in settings['shipping']:
            try:
                settings['shipping'][key] = int(settings['shipping'][key])
            except (ValueError, TypeError):
                settings['shipping'][key] = 0

    # Statistiques pour la maintenance
    try:
        # Taille de la base de données (estimation simple)
        db_size = 15.2  # MB - à calculer réellement plus tard

        # Nombre d'images
        image_count = len([f for f in os.listdir(app.config['UPLOAD_FOLDER'])
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))])

        # Dernière sauvegarde (simulation)
        last_backup = "2026-01-10 14:30"
    except:
        db_size = 0
        image_count = 0
        last_backup = "Jamais"

    return render_template('admin/admin_settings.html',
                         db_size=db_size,
                         image_count=image_count,
                         last_backup=last_backup,
                         settings=settings)

@app.route('/admin/settings/update', methods=['POST'])
def admin_update_settings():
    """Mettre à jour les paramètres"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    section = request.form.get('section')
    settings = load_settings()

    if section == 'general':
        # Sauvegarder les paramètres généraux
        settings['general'] = {
            'app_name': request.form.get('app_name'),
            'app_version': request.form.get('app_version'),
            'default_currency': request.form.get('default_currency'),
            'timezone': request.form.get('timezone')
        }
        flash('Paramètres généraux enregistrés avec succès', 'success')

    elif section == 'security':
        # Sauvegarder les paramètres de sécurité
        settings['security'] = {
            'session_timeout': request.form.get('session_timeout'),
            'max_login_attempts': request.form.get('max_login_attempts'),
            'require_special_chars': 'require_special_chars' in request.form,
            'require_numbers': 'require_numbers' in request.form,
            'require_uppercase': 'require_uppercase' in request.form
        }
        flash('Paramètres de sécurité enregistrés avec succès', 'success')

    elif section == 'emails':
        # Sauvegarder la configuration email
        settings['emails'] = {
            'smtp_server': request.form.get('smtp_server'),
            'smtp_port': request.form.get('smtp_port'),
            'smtp_username': request.form.get('smtp_username'),
            'smtp_password': request.form.get('smtp_password'),
            'from_email': request.form.get('from_email')
        }
        flash('Configuration email enregistrée avec succès', 'success')

    elif section == 'shipping':
        # Fonction pour nettoyer et valider les valeurs numériques
        def clean_numeric_value(value):
            if not value:
                return '0'
            # Supprimer tous les caractères non numériques sauf le point décimal
            cleaned = ''.join(c for c in str(value) if c.isdigit() or c == '.')
            try:
                # Convertir en float puis en int pour éviter les décimales
                return str(int(float(cleaned)))
            except (ValueError, TypeError):
                return '0'

        # Sauvegarder les prix de livraison par région avec validation
        settings['shipping'] = {
            'moroni': clean_numeric_value(request.form.get('shipping_moroni')),
            'hors_moroni': clean_numeric_value(request.form.get('shipping_hors_moroni')),
            'mutsamudu': clean_numeric_value(request.form.get('shipping_mutsamudu')),
            'hors_mutsamudu': clean_numeric_value(request.form.get('shipping_hors_mutsamudu')),
            'fomboni': clean_numeric_value(request.form.get('shipping_fomboni')),
            'hors_fomboni': clean_numeric_value(request.form.get('shipping_hors_fomboni'))
        }
        
        # Sauvegarder dans le fichier JSON
        if save_settings(settings):
            # Log pour vérification
            print(f"✅ Prix de livraison mis à jour: {settings['shipping']}")
            flash('Prix de livraison par région enregistrés avec succès. Les utilisateurs verront les nouveaux prix après avoir rechargé la page.', 'success')
        else:
            flash('Erreur lors de la sauvegarde des prix de livraison', 'error')
            return redirect(url_for('admin_settings'))

    # Sauvegarder dans le fichier JSON (pour les autres sections)
    if section != 'shipping':
        save_settings(settings)

    return redirect(url_for('admin_settings'))

# ===== Routes Gestion Dépenses =====

@app.route('/admin/expenses')
def admin_expenses():
    """Liste des dépenses"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    # Récupérer tous les paramètres de filtrage
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    # Query de base
    query = Expense.query

    if search_query:
        query = query.filter(
            db.or_(
                Expense.description.ilike(f'%{search_query}%'),
                Expense.notes.ilike(f'%{search_query}%')
            )
        )

    if category_filter:
        query = query.filter(Expense.category == category_filter)

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Expense.date >= date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(Expense.date <= date_to_obj)
        except ValueError:
            pass

    expenses = query.order_by(Expense.date.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # Statistiques des dépenses
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    monthly_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.date >= datetime(datetime.now().year, datetime.now().month, 1)
    ).scalar() or 0

    # Dépenses par catégorie
    expenses_by_category = db.session.query(
        Expense.category,
        db.func.sum(Expense.amount).label('total')
    ).group_by(Expense.category).order_by(db.desc('total')).limit(5).all()

    # Catégories disponibles
    categories = db.session.query(Expense.category).distinct().all()
    categories = [cat[0] for cat in categories]

    return render_template('admin/admin_expenses.html',
                         expenses=expenses,
                         total_expenses=total_expenses,
                         monthly_expenses=monthly_expenses,
                         expenses_by_category=expenses_by_category,
                         categories=categories,
                         search_query=search_query,
                         category_filter=category_filter,
                         date_from=date_from,
                         date_to=date_to)

@app.route('/admin/expenses/add', methods=['GET', 'POST'])
def admin_expense_add():
    """Ajouter une nouvelle dépense"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        description = request.form.get('description')
        category = request.form.get('category')
        amount = request.form.get('amount')
        date_str = request.form.get('date')
        notes = request.form.get('notes')

        # Validation
        if not all([description, category, amount]):
            flash('Veuillez remplir tous les champs obligatoires', 'error')
            return redirect(request.url)

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash('Montant invalide', 'error')
            return redirect(request.url)

        try:
            if date_str:
                date = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                date = datetime.utcnow()
        except ValueError:
            flash('Date invalide', 'error')
            return redirect(request.url)

        # Créer la dépense
        new_expense = Expense(
            description=description,
            category=category,
            amount=amount,
            date=date,
            notes=notes,
            created_by=session.get('user_email')
        )

        try:
            db.session.add(new_expense)
            db.session.commit()
            flash('Dépense ajoutée avec succès', 'success')
            return redirect(url_for('admin_expenses'))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de l\'ajout de la dépense', 'error')

    return render_template('admin/admin_expense_add.html', current_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/admin/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
def admin_expense_edit(expense_id):
    """Modifier une dépense"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    expense = Expense.query.get_or_404(expense_id)

    if request.method == 'POST':
        description = request.form.get('description')
        category = request.form.get('category')
        amount = request.form.get('amount')
        date_str = request.form.get('date')
        notes = request.form.get('notes')

        # Validation
        if not all([description, category, amount]):
            flash('Veuillez remplir tous les champs obligatoires', 'error')
            return redirect(request.url)

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash('Montant invalide', 'error')
            return redirect(request.url)

        try:
            if date_str:
                date = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                date = expense.date
        except ValueError:
            flash('Date invalide', 'error')
            return redirect(request.url)

        # Mettre à jour la dépense
        expense.description = description
        expense.category = category
        expense.amount = amount
        expense.date = date
        expense.notes = notes

        try:
            db.session.commit()
            flash('Dépense modifiée avec succès', 'success')
            return redirect(url_for('admin_expenses'))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la modification de la dépense', 'error')

    return render_template('admin/admin_expense_edit.html', expense=expense, current_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/admin/expenses/<int:expense_id>/delete', methods=['POST'])
def admin_expense_delete(expense_id):
    """Supprimer une dépense"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin_login'))

    expense = Expense.query.get_or_404(expense_id)

    try:
        db.session.delete(expense)
        db.session.commit()
        flash('Dépense supprimée avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de la suppression de la dépense', 'error')

    return redirect(url_for('admin_expenses'))

if __name__ == '__main__':
    # Créer le dossier uploads s'il n'existe pas
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Créer toutes les tables de la base de données
    with app.app_context():
        db.create_all()
        print("✅ Base de données initialisée avec succès!")
    
    app.run(debug=True, host='0.0.0.0', port=5002)
