"""
Utilitaires pour gérer les paramètres de l'application
"""
import json
import os

# Fichier de configuration - chemin absolu basé sur la localisation de ce fichier
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, 'instance', 'settings.json')

# Paramètres par défaut
DEFAULT_SETTINGS = {
    'general': {
        'app_name': 'COLOURFUL HDJT',
        'app_version': '1.0.0',
        'default_currency': 'KMF',
        'timezone': 'Indian/Comoro'
    },
    'security': {
        'session_timeout': 60,
        'max_login_attempts': 5,
        'require_special_chars': True,
        'require_numbers': True,
        'require_uppercase': False
    },
    'shipping': {
        'Moroni': 1500,
        'Hors Moroni': 2000,
        'Mutsamudu': 2500,
        'Hors Mutsamudu': 3000,
        'Fomboni': 3200,
        'Hors Fomboni': 3500
    }
}

def load_settings():
    """Charger les paramètres depuis le fichier JSON"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Fusionner avec les paramètres par défaut pour les clés manquantes
                for section, values in DEFAULT_SETTINGS.items():
                    if section not in settings:
                        settings[section] = values
                    elif isinstance(values, dict) and section != 'shipping':
                        # Pour les sections autres que shipping, fusionner les clés
                        for key, default_value in values.items():
                            if key not in settings[section]:
                                settings[section][key] = default_value
                    # Pour shipping, ne pas fusionner pour éviter les doublons de clés
                return settings
        except Exception as e:
            print(f"Erreur lors du chargement des paramètres: {e}")
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Sauvegarder les paramètres dans le fichier JSON"""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des paramètres: {e}")
        return False

def normalize_shipping_prices(raw_prices):
    """Normaliser les clés des prix de livraison (minuscules -> format propre)"""
    # Mapping des clés minuscules vers les clés avec majuscules
    key_mapping = {
        'moroni': 'Moroni',
        'hors_moroni': 'Hors Moroni',
        'mutsamudu': 'Mutsamudu',
        'hors_mutsamudu': 'Hors Mutsamudu',
        'fomboni': 'Fomboni',
        'hors_fomboni': 'Hors Fomboni'
    }
    
    normalized = {}
    for key, value in raw_prices.items():
        # Convertir la clé en format propre
        proper_key = key_mapping.get(key.lower(), key)
        # Convertir la valeur en entier
        try:
            normalized[proper_key] = int(value) if isinstance(value, str) else value
        except (ValueError, TypeError):
            normalized[proper_key] = value
    
    return normalized

def get_shipping_price(region, country='Comores'):
    """Obtenir le prix de livraison pour une région donnée"""
    # Accepter "Comores" et les noms des îles (Grande Comore, Anjouan, Mohéli)
    valid_countries = ['comores', 'grande comore', 'anjouan', 'mohéli', 'moheli']
    if country and country.lower() not in valid_countries:
        return 0  # Gratuit ou à définir pour les autres pays
    
    settings = load_settings()
    raw_shipping_prices = settings.get('shipping', {})
    shipping_prices = normalize_shipping_prices(raw_shipping_prices)
    
    # Normaliser la région recherchée (remplacer _ par espace, insensible à la casse)
    region_normalized = region.replace('_', ' ').lower() if region else ''
    
    # Recherche insensible à la casse
    for key, value in shipping_prices.items():
        if key.lower() == region_normalized:
            return value
    
    return 0

def update_shipping_prices(prices):
    """Mettre à jour les prix de livraison"""
    settings = load_settings()
    settings['shipping'] = prices
    return save_settings(settings)
