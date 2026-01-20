// ===== Admin JavaScript =====

document.addEventListener('DOMContentLoaded', function() {
    // Menu utilisateur déroulant
    const userMenuButton = document.getElementById('user-menu-button');
    const userMenu = document.getElementById('user-menu');

    if (userMenuButton && userMenu) {
        userMenuButton.addEventListener('click', function(e) {
            e.stopPropagation();
            userMenu.classList.toggle('hidden');
        });

        // Fermer le menu quand on clique ailleurs
        document.addEventListener('click', function(e) {
            if (!userMenuButton.contains(e.target) && !userMenu.contains(e.target)) {
                userMenu.classList.add('hidden');
            }
        });
    }

    // Menu mobile
    const mobileMenuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');

    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener('click', function() {
            mobileMenu.classList.toggle('hidden');
        });
    }

    // Animations d'entrée pour les cartes
    const cards = document.querySelectorAll('.admin-card');
    cards.forEach((card, index) => {
        card.style.animationDelay = `${index * 0.1}s`;
        card.style.animation = 'fadeIn 0.5s ease-out forwards';
        card.style.opacity = '0';
    });

    // Confirmation pour les actions dangereuses
    const dangerousButtons = document.querySelectorAll('[data-confirm]');
    dangerousButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Auto-refresh pour les statistiques (optionnel)
    function refreshStats() {
        // Cette fonction peut être appelée périodiquement pour mettre à jour les stats
        console.log('Refreshing admin stats...');
    }

    // Initialiser les tooltips si nécessaire
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(element => {
        element.setAttribute('title', element.getAttribute('data-tooltip'));
    });

    // Gestion des onglets si présents
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const tabId = this.getAttribute('data-tab');

            // Masquer tous les contenus
            tabContents.forEach(content => {
                content.classList.add('hidden');
            });

            // Désactiver tous les boutons
            tabButtons.forEach(btn => {
                btn.classList.remove('active');
            });

            // Afficher le contenu actif
            const activeContent = document.getElementById(tabId);
            if (activeContent) {
                activeContent.classList.remove('hidden');
            }

            // Activer le bouton
            this.classList.add('active');
        });
    });

    // Recherche en temps réel (si implémentée)
    const searchInputs = document.querySelectorAll('.admin-search');
    searchInputs.forEach(input => {
        let timeout;
        input.addEventListener('input', function() {
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                const query = this.value.toLowerCase();
                const rows = document.querySelectorAll('.admin-table tbody tr');

                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    if (text.includes(query)) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });
            }, 300);
        });
    });

    // Notifications toast (si utilisées)
    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    // Exposer des fonctions globales si nécessaire
    window.AdminUtils = {
        showToast: showToast,
        refreshStats: refreshStats
    };
});

// Fonction utilitaire pour formater les nombres
function formatNumber(num) {
    return new Intl.NumberFormat('fr-FR').format(num);
}

// Fonction utilitaire pour formater les dates
function formatDate(date) {
    return new Intl.DateTimeFormat('fr-FR', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(new Date(date));
}

// Fonction utilitaire pour le statut des commandes
function getStatusBadge(status) {
    const statusMap = {
        'pending': { text: 'En attente', class: 'status-warning' },
        'confirmed': { text: 'Confirmée', class: 'status-info' },
        'shipped': { text: 'Expédiée', class: 'status-info' },
        'delivered': { text: 'Livrée', class: 'status-success' },
        'cancelled': { text: 'Annulée', class: 'status-error' }
    };

    return statusMap[status] || { text: status, class: 'status-info' };
}