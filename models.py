from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model):
    """Modèle pour les utilisateurs"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=True)  # Nouveau champ username
    password_hash = db.Column(db.String(128), nullable=False)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    telephone = db.Column(db.String(20))
    is_admin = db.Column(db.Boolean, default=False)  # Nouveau champ pour les administrateurs
    current_session_token = db.Column(db.String(256), nullable=True)  # Token de session actuelle
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    orders = db.relationship('Order', backref='user', lazy=True)
    cart_items = db.relationship('CartItem', backref='user', lazy=True)
    favorites = db.relationship('Favorite', backref='user', lazy=True)
    addresses = db.relationship('Address', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.email}>'

class MobileSession(db.Model):
    """Modèle pour les sessions mobiles"""
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(128), unique=True, nullable=False)
    user_email = db.Column(db.String(120), db.ForeignKey('user.email'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<MobileSession {self.token[:10]}...>'

class ProductCategory(db.Model):
    """Modèle pour les catégories de produits"""
    id = db.Column(db.String(50), primary_key=True)  # rouge_levres, mascara, etc.
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Relations
    products = db.relationship('Product', backref='category', lazy=True)

    @property
    def predefined_products_count(self):
        """Compte le nombre de produits prédéfinis dans cette catégorie"""
        from app import PredefinedProduct
        return PredefinedProduct.query.filter(PredefinedProduct.categories.like(f'%{self.id}%')).count()

    def __repr__(self):
        return f'<ProductCategory {self.name}>'

class Product(db.Model):
    """Modèle pour les produits individuels"""
    id = db.Column(db.String(50), primary_key=True)  # rl1, m1, etc.
    name = db.Column(db.String(200), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500))
    category_id = db.Column(db.String(50), db.ForeignKey('product_category.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Product {self.name}>'

class ContainerType(db.Model):
    """Modèle pour les types de contenants"""
    id = db.Column(db.String(50), primary_key=True)  # carton, sac_plastique, goblet
    name = db.Column(db.String(100), nullable=False)
    base_price = db.Column(db.Float, nullable=False)
    max_products = db.Column(db.Integer, nullable=False)
    allowed_categories = db.Column(db.Text)  # JSON string des catégories autorisées
    image_url = db.Column(db.String(500))  # URL de l'image représentative

    # Relations
    orders = db.relationship('Order', backref='container_type', lazy=True)

    def __repr__(self):
        return f'<ContainerType {self.name}>'

class Container(db.Model):
    """Modèle pour les contenants personnalisés"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    container_type_id = db.Column(db.String(50), db.ForeignKey('container_type.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)  # Prix du contenant
    max_products = db.Column(db.Integer, nullable=False, default=10)  # Nombre maximum de produits
    description = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    is_customizable = db.Column(db.Boolean, default=True)  # Nouveau champ pour la personnalisation
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    container_type = db.relationship('ContainerType', backref='containers', lazy=True)
    products = db.relationship('ContainerProduct', back_populates='container', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Container {self.name}>'

class ContainerProduct(db.Model):
    """Modèle pour lier les produits aux contenants"""
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.Integer, db.ForeignKey('container.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('predefined_product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)

    # Relations
    container = db.relationship('Container', back_populates='products')
    product = db.relationship('PredefinedProduct', backref='container_products')

    def __repr__(self):
        return f'<ContainerProduct container={self.container_id}, product={self.product_id}>'

class PredefinedProduct(db.Model):
    """Modèle pour les produits prédéfinis"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    container_type_id = db.Column(db.String(50), db.ForeignKey('container_type.id'), nullable=True)  # Modifié pour permettre des produits sans contenant
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500))
    is_customizable = db.Column(db.Boolean, default=True)
    is_internal = db.Column(db.Boolean, default=False)  # Nouveau champ pour les produits internes
    categories = db.Column(db.Text)  # JSON string des catégories
    quantity_per_category = db.Column(db.Integer, default=1)
    initial_stock = db.Column(db.Integer, default=0)  # Stock initial
    current_stock = db.Column(db.Integer, default=0)  # Stock actuel
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    container_type = db.relationship('ContainerType', backref='predefined_products', lazy=True)

    def __repr__(self):
        return f'<PredefinedProduct {self.name}>'

class Order(db.Model):
    """Modèle pour les commandes"""
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), db.ForeignKey('user.email'), nullable=False)
    container_type_id = db.Column(db.String(50), db.ForeignKey('container_type.id'), nullable=True)
    total_price = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))  # Ajout du champ payment_method
    delivery_address = db.Column(db.Text)  # Adresse de livraison en JSON
    status = db.Column(db.String(50), default='pending')  # pending, confirmed, shipped, delivered
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    order_items = db.relationship('OrderItem', backref='order', lazy=True)

    def __repr__(self):
        return f'<Order {self.id}>'

class OrderItem(db.Model):
    """Modèle pour les éléments d'une commande"""
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.String(50), db.ForeignKey('product.id'), nullable=True)
    product_name = db.Column(db.String(100))  # Ajout du nom du produit
    product_image = db.Column(db.String(200))  # Ajout de l'image du produit
    product_data = db.Column(db.Text)  # JSON des données complètes du produit
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f'<OrderItem {self.product_id}>'

class CartItem(db.Model):
    """Modèle pour les éléments du panier"""
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), db.ForeignKey('user.email'), nullable=False)
    product_type = db.Column(db.String(50))  # 'predefined' ou 'custom'
    product_id = db.Column(db.String(100))  # ID du produit ou ID personnalisé
    product_data = db.Column(db.Text)  # JSON des données du produit
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CartItem {self.product_id}>'

class Address(db.Model):
    """Modèle pour les adresses de livraison et facturation"""
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), db.ForeignKey('user.email'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # Nom de l'adresse (Maison, Travail, etc.)
    recipient_name = db.Column(db.String(100), nullable=False)  # Nom du destinataire
    phone = db.Column(db.String(20))
    address_line_1 = db.Column(db.String(200), nullable=False)
    address_line_2 = db.Column(db.String(200))
    city = db.Column(db.String(100), nullable=False)
    region = db.Column(db.String(100))  # Région spécifique (Moroni, Mutsamudu, etc.)
    postal_code = db.Column(db.String(20))  # Code postal optionnel
    country = db.Column(db.String(100), nullable=False, default='Comores')
    is_default = db.Column(db.Boolean, default=False)
    address_type = db.Column(db.String(20), default='shipping')  # 'shipping' ou 'billing'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Address {self.name} - {self.user_email}>'

class Favorite(db.Model):
    """Modèle pour les produits favoris"""
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), db.ForeignKey('user.email'), nullable=False)
    product_type = db.Column(db.String(50))  # 'predefined' ou 'custom'
    product_id = db.Column(db.String(100))  # ID du produit ou ID personnalisé
    product_data = db.Column(db.Text)  # JSON des données du produit
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Favorite {self.product_id} - {self.user_email}>'

class Expense(db.Model):
    """Modèle pour les dépenses"""
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False)  # 'achat_materiel', 'salaire', 'loyer', 'transport', etc.
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(120), db.ForeignKey('user.email'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Expense {self.description} - {self.amount} KMF>'