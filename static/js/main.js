// Gestion des messages flash
document.addEventListener('DOMContentLoaded', function() {
    // Fermer les alertes
    const closeButtons = document.querySelectorAll('.close-alert');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            this.parentElement.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                this.parentElement.remove();
            }, 300);
        });
    });
    
    // Auto-fermeture des alertes après 5 secondes
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                alert.remove();
            }, 300);
        }, 5000);
    });
});

// Animation pour le slideOutRight
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Gestion du panier (API)
class Panier {
    constructor() {
        this.items = [];
        this.loading = false;
        this.init();
    }
    
    async init() {
        await this.charger();
        this.mettreAJourBadge();
    }
    
    async charger() {
        if (this.loading) return;
        this.loading = true;
        
        try {
            const response = await fetch('/api/cart');
            if (response.ok) {
                this.items = await response.json();
            } else {
                console.error('Erreur lors du chargement du panier:', response.status);
                this.items = [];
            }
        } catch (error) {
            console.error('Erreur réseau:', error);
            this.items = [];
        } finally {
            this.loading = false;
        }
        
        return this.items;
    }
    
    async ajouter(produit) {
        console.log('🛒 Panier.ajouter appelé avec:', produit);
        try {
            const response = await fetch('/api/cart', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify(produit)
            });
            
            console.log('📡 Réponse serveur status:', response.status);
            
            if (response.ok) {
                const data = await response.json();
                console.log('✅ Données reçues:', data);
                this.items = data.cart || [];
                this.mettreAJourBadge();
                return true;
            } else {
                const errorData = await response.json().catch(() => ({}));
                console.error('❌ Erreur serveur:', response.status, errorData);
                
                // Si erreur 401 (non authentifié), rediriger vers la page de connexion
                if (response.status === 401) {
                    alert('Vous devez être connecté pour ajouter des produits au panier.');
                    window.location.href = '/login';
                    return false;
                }
                
                return false;
            }
        } catch (error) {
            console.error('💥 Erreur réseau:', error);
            return false;
        }
    }
    
    async retirer(itemId) {
        // Pour la compatibilité, on garde cette méthode mais elle utilise maintenant product_id
        // Trouver l'item dans la liste locale pour obtenir le product_id
        const item = this.items.find(item => item.id == itemId);
        if (!item) {
            await this.charger();
            return false;
        }
        
        const productId = item.product_id;
        
        try {
            const response = await fetch(`/api/cart/product/${productId}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                const data = await response.json();
                this.items = data.cart || [];
                this.mettreAJourBadge();
                return true;
            } else {
                console.error('Erreur lors de la suppression du panier:', response.status);
                // Recharger le panier en cas d'erreur
                await this.charger();
                return false;
            }
        } catch (error) {
            console.error('Erreur réseau:', error);
            // Recharger le panier en cas d'erreur réseau
            await this.charger();
            return false;
        }
    }
    
    async mettreAJourQuantite(itemId, quantite) {
        try {
            const item = this.items.find(item => item.id == itemId);
            if (!item) return false;
            
            const response = await fetch(`/api/cart/${itemId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ...item,
                    quantite: quantite
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.items = data.cart || [];
                this.mettreAJourBadge();
                return true;
            } else {
                console.error('Erreur lors de la mise à jour du panier:', response.status);
                return false;
            }
        } catch (error) {
            console.error('Erreur réseau:', error);
            return false;
        }
    }
    
    obtenirTotal() {
        return this.items.reduce((total, item) => {
            return total + (item.prix * item.quantite);
        }, 0);
    }
    
    obtenirNombreItems() {
        return this.items.reduce((total, item) => total + item.quantite, 0);
    }
    
    mettreAJourBadge() {
        const badge = document.querySelector('.badge');
        if (badge) {
            badge.textContent = this.obtenirNombreItems();
        }
    }
    
    async vider() {
        // Supprimer tous les items un par un
        const itemsToDelete = [...this.items];
        for (const item of itemsToDelete) {
            await this.retirer(item.id);
        }
    }
}

// Initialiser le panier
const panier = new Panier();

// Fonction pour ajouter au panier
async function ajouterAuPanier(produitId, nom, prix, image, contenant) {
    console.log('Tentative d\'ajout au panier pour produit:', produitId);
    
    // Vérifier si l'utilisateur est connecté
    try {
        console.log('Vérification de l\'authentification...');
        const authResponse = await fetch('/api/login_status');
        console.log('Réponse auth:', authResponse.status, authResponse.ok);
        
        if (!authResponse.ok) {
            console.log('Utilisateur non connecté, affichage du message');
            afficherMessage('Veuillez vous connecter pour ajouter des produits au panier.', 'error');
            // Rediriger vers la page de connexion immédiatement
            window.location.href = '/login';
            return;
        }
        
        const authData = await authResponse.json();
        console.log('Données auth:', authData);
        
    } catch (error) {
        console.error('Erreur lors de la vérification d\'authentification:', error);
        afficherMessage('Erreur de connexion. Veuillez réessayer.', 'error');
        return;
    }

    console.log('Utilisateur connecté, ajout du produit...');
    const success = await panier.ajouter({
        product_id: produitId,
        nom: nom,
        prix: prix,
        image: image,
        contenant: contenant,
        type: 'predefined',
        quantite: 1
    });
    
    if (success) {
        console.log('Produit ajouté avec succès');
        afficherMessage('Produit ajouté au panier !', 'success');
    } else {
        console.log('Échec de l\'ajout du produit');
        afficherMessage('Erreur lors de l\'ajout au panier. Veuillez réessayer.', 'error');
    }
}

// Fonction pour afficher un message
function afficherMessage(message, type = 'success') {
    const flashContainer = document.querySelector('.flash-messages') || createFlashContainer();
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        ${message}
        <button class="close-alert">&times;</button>
    `;
    
    flashContainer.appendChild(alert);
    
    // Ajouter l'événement de fermeture
    alert.querySelector('.close-alert').addEventListener('click', function() {
        alert.remove();
    });
    
    // Auto-suppression après 5 secondes
    setTimeout(() => {
        alert.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => alert.remove(), 300);
    }, 5000);
}

function createFlashContainer() {
    const container = document.createElement('div');
    container.className = 'flash-messages';
    document.body.appendChild(container);
    return container;
}

// Smooth scroll pour les liens d'ancre
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href !== '#') {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        }
    });
});

// Fonction pour voir le détail d'un produit (utilisée dans produits.html)
function voirProduit(produitId) {
    window.location.href = `/produit/${produitId}`;
}

// Fonction pour ajouter au panier depuis la page détail (avec quantité)
async function ajouterAuPanierDetail() {
    const btn = document.querySelector('.add-to-cart-detail');
    if (!btn) return;
    
    // Vérifier si l'utilisateur est connecté
    try {
        const authResponse = await fetch('/api/login_status');
        if (!authResponse.ok) {
            afficherMessage('Veuillez vous connecter pour ajouter des produits au panier.', 'error');
            // Rediriger vers la page de connexion après un court délai
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
            return;
        }
    } catch (error) {
        console.error('Erreur lors de la vérification d\'authentification:', error);
        afficherMessage('Erreur de connexion. Veuillez réessayer.', 'error');
        return;
    }
    
    const quantity = parseInt(document.getElementById('quantity').value);
    const produitId = parseInt(btn.dataset.productId);
    const nom = btn.dataset.productNom;
    const prix = parseFloat(btn.dataset.productPrix);
    const image = btn.dataset.productImage;
    const contenant = btn.dataset.productContenant;

    console.log('Ajout au panier depuis détail:', { produitId, nom, prix, image, contenant, quantity });

    for (let i = 0; i < quantity; i++) {
        await panier.ajouter({
            product_id: produitId,
            nom: nom,
            prix: prix,
            image: image,
            contenant: contenant,
            type: 'predefined',
            quantite: 1
        });
    }

    afficherMessage(`${quantity} produit${quantity > 1 ? 's' : ''} ajouté${quantity > 1 ? 's' : ''} au panier !`, 'success');

    // Animation du bouton
    if (btn) {
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> Ajouté !';
        btn.classList.add('btn-success');

        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.classList.remove('btn-success');
        }, 2000);
    }
}

// Gestion de la quantité dans la page détail
function changeQuantity(delta) {
    const input = document.getElementById('quantity');
    if (input) {
        const newValue = parseInt(input.value) + delta;
        if (newValue >= 1 && newValue <= 10) {
            input.value = newValue;
        }
    }
}

// Changer l'image principale (pour la page détail)
function changeImage(src) {
    const mainImage = document.getElementById('main-product-image');
    if (mainImage) {
        mainImage.src = src;
    }

    // Mettre à jour les thumbnails
    document.querySelectorAll('.thumbnail').forEach(thumb => {
        thumb.classList.remove('active');
    });
    if (event && event.target) {
        event.target.classList.add('active');
    }
}

// Initialisation au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    // Fermer les alertes
    const closeButtons = document.querySelectorAll('.close-alert');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            this.parentElement.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                this.parentElement.remove();
            }, 300);
        });
    });
    
    // Auto-fermeture des alertes après 5 secondes
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                alert.remove();
            }, 300);
        }, 5000);
    });

    // Gestion du tri des produits (page produits)
    const sortFilter = document.getElementById('sort-filter');
    if (sortFilter) {
        sortFilter.addEventListener('change', function() {
            const sortBy = this.value;
            const products = Array.from(document.querySelectorAll('.product-card'));
            const container = document.querySelector('.products-grid');

            if (container) {
                products.sort((a, b) => {
                    if (sortBy === 'nom') {
                        const titleA = a.querySelector('.product-title').textContent;
                        const titleB = b.querySelector('.product-title').textContent;
                        return titleA.localeCompare(titleB);
                    } else if (sortBy === 'prix-asc') {
                        return parseInt(a.dataset.prix) - parseInt(b.dataset.prix);
                    } else if (sortBy === 'prix-desc') {
                        return parseInt(b.dataset.prix) - parseInt(a.dataset.prix);
                    }
                    return 0;
                });

                products.forEach(product => container.appendChild(product));
            }
        });
    }

    // Gestion du filtre par contenant (page produits)
    const contenantFilter = document.getElementById('contenant-filter');
    if (contenantFilter) {
        contenantFilter.addEventListener('change', function() {
            const contenant = this.value;
            const url = new URL(window.location);
            if (contenant) {
                url.searchParams.set('contenant', contenant);
            } else {
                url.searchParams.delete('contenant');
            }
            window.location.href = url.toString();
        });
    }

    // Gestion du modal d'aperçu rapide
    const modal = document.getElementById('quick-view-modal');
    const closeBtn = document.querySelector('.close-modal');

    if (closeBtn && modal) {
        closeBtn.onclick = function() {
            modal.style.display = 'none';
        }

        window.onclick = function(event) {
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        }
    }
});

// Gestion des accordéons pour la personnalisation (mobile)
document.addEventListener('DOMContentLoaded', function() {
    // Ne gérer les accordéons que sur mobile
    if (window.innerWidth > 767) {
        return;
    }

    const accordionHeaders = document.querySelectorAll('.accordion-header');

    accordionHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const content = this.nextElementSibling;
            const isOpen = content.classList.contains('open');

            // Fermer tous les autres accordéons
            document.querySelectorAll('.accordion-content').forEach(otherContent => {
                if (otherContent !== content) {
                    otherContent.classList.remove('open');
                    otherContent.previousElementSibling.classList.remove('active');
                }
            });

            // Toggle l'accordéon actuel
            if (isOpen) {
                content.classList.remove('open');
                this.classList.remove('active');
            } else {
                content.classList.add('open');
                this.classList.add('active');
            }
        });
    });

    // Ouvrir le premier accordéon par défaut sur mobile
    const firstAccordion = document.querySelector('.accordion-header');
    if (firstAccordion) {
        firstAccordion.click();
    }
});

// ===== Gestion de la recherche =====
document.addEventListener('DOMContentLoaded', function() {
    console.log('Search functionality initializing...');
    const searchToggle = document.getElementById('search-toggle');
    const searchForm = document.getElementById('search-form');
    const searchInput = document.getElementById('search-input');
    const searchDropdown = document.getElementById('search-dropdown');

    console.log('Search elements found:', {
        searchToggle: !!searchToggle,
        searchForm: !!searchForm,
        searchInput: !!searchInput,
        searchDropdown: !!searchDropdown
    });

    let currentFocus = -1;
    let suggestions = [];

    // Ouvrir/fermer la recherche
    if (searchToggle) {
        console.log('Adding click event to search toggle');
        searchToggle.addEventListener('click', function(e) {
            console.log('Search toggle clicked');
            e.preventDefault();
            searchForm.classList.toggle('active');

            if (searchForm.classList.contains('active')) {
                if (searchInput) {
                    setTimeout(() => searchInput.focus(), 300);
                }
            } else {
                closeSearchDropdown();
            }
        });
    }

    // Gestion de la saisie dans le champ de recherche
    if (searchInput) {
        let searchTimeout;

        searchInput.addEventListener('input', function() {
            const query = this.value.trim();

            clearTimeout(searchTimeout);

            if (query.length >= 2) {
                searchTimeout = setTimeout(() => {
                    fetchSuggestions(query);
                }, 300); // Debounce de 300ms
            } else {
                closeSearchDropdown();
            }
        });

        // Navigation au clavier
        searchInput.addEventListener('keydown', function(e) {
            if (!searchDropdown.classList.contains('show')) return;

            const items = searchDropdown.querySelectorAll('.search-dropdown-item');

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                currentFocus = currentFocus < items.length - 1 ? currentFocus + 1 : 0;
                updateFocus(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                currentFocus = currentFocus > 0 ? currentFocus - 1 : items.length - 1;
                updateFocus(items);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (currentFocus >= 0 && items[currentFocus]) {
                    items[currentFocus].click();
                } else {
                    searchForm.submit();
                }
            } else if (e.key === 'Escape') {
                closeSearchDropdown();
            }
        });

        // Fermer le dropdown quand on perd le focus
        searchInput.addEventListener('blur', function() {
            setTimeout(() => {
                if (!searchDropdown.matches(':hover')) {
                    closeSearchDropdown();
                }
            }, 150);
        });
    }

    // Fermer la recherche en appuyant sur Échap
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && searchForm.classList.contains('active')) {
            searchForm.classList.remove('active');
            closeSearchDropdown();
        }
    });

    // Fermer la recherche en cliquant ailleurs
    document.addEventListener('click', function(e) {
        if (!searchForm.contains(e.target) && !searchToggle.contains(e.target) && searchForm.classList.contains('active')) {
            searchForm.classList.remove('active');
            closeSearchDropdown();
        }
    });

    // Fonction pour récupérer les suggestions
    function fetchSuggestions(query) {
        console.log('Fetching suggestions for query:', query);
        fetch(`/api/search-suggestions?q=${encodeURIComponent(query)}`)
            .then(response => {
                console.log('Response status:', response.status);
                return response.json();
            })
            .then(data => {
                console.log('Received suggestions:', data);
                suggestions = data;
                displaySuggestions(data);
            })
            .catch(error => {
                console.error('Erreur lors de la récupération des suggestions:', error);
                closeSearchDropdown();
            });
    }

    // Fonction pour afficher les suggestions
    function displaySuggestions(suggestions) {
        if (suggestions.length === 0) {
            closeSearchDropdown();
            return;
        }

        searchDropdown.innerHTML = '';

        suggestions.forEach((suggestion, index) => {
            const item = document.createElement('a');
            item.href = suggestion.url;
            item.className = 'search-dropdown-item';

            const icon = suggestion.type === 'product' ? 'fas fa-box' : 'fas fa-tag';
            const typeText = suggestion.type === 'product' ? 'Produit' : 'Catégorie';

            item.innerHTML = `
                <i class="${icon}"></i>
                <span class="suggestion-text">${suggestion.text}</span>
                <span class="suggestion-type">${typeText}</span>
            `;

            item.addEventListener('click', function(e) {
                closeSearchDropdown();
            });

            searchDropdown.appendChild(item);
        });

        searchDropdown.classList.add('show');
        currentFocus = -1;
    }

    // Fonction pour fermer le dropdown
    function closeSearchDropdown() {
        searchDropdown.classList.remove('show');
        searchDropdown.innerHTML = '';
        currentFocus = -1;
        suggestions = [];
    }

    // Fonction pour mettre à jour le focus
    function updateFocus(items) {
        // Retirer la classe active de tous les items
        items.forEach(item => item.classList.remove('active'));

        // Ajouter la classe active à l'item focus
        if (items[currentFocus]) {
            items[currentFocus].classList.add('active');
            items[currentFocus].scrollIntoView({ block: 'nearest' });
        }
    }
});
