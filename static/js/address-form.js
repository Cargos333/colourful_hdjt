// Définir les régions par île des Comores
const REGIONS_BY_COUNTRY = {
    'Grande Comore': [
        { value: 'Moroni', label: 'Moroni' },
        { value: 'Hors Moroni', label: 'Hors Moroni' }
    ],
    'Anjouan': [
        { value: 'Mutsamudu', label: 'Mutsamudu' },
        { value: 'Hors Mutsamudu', label: 'Hors Mutsamudu' }
    ],
    'Mohéli': [
        { value: 'Fomboni', label: 'Fomboni' },
        { value: 'Hors Fomboni', label: 'Hors Fomboni' }
    ]
};

// Prix de livraison par région - chargés dynamiquement depuis l'API
let SHIPPING_PRICES = {
    'Moroni': 1500,
    'Hors Moroni': 2000,
    'Mutsamudu': 2500,
    'Hors Mutsamudu': 3000,
    'Fomboni': 3200,
    'Hors Fomboni': 3500
};

// Charger les prix de livraison depuis l'API
async function loadShippingPrices() {
    try {
        // Ajouter un cache-busting timestamp pour forcer le rechargement
        const response = await fetch('/api/shipping-prices?t=' + Date.now());
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.prices) {
                SHIPPING_PRICES = data.prices;
                console.log('Prix de livraison chargés:', SHIPPING_PRICES);
                // Mettre à jour l'affichage si une région est déjà sélectionnée
                updateShippingPrice();
            }
        }
    } catch (error) {
        console.error('Erreur lors du chargement des prix de livraison:', error);
        // Garder les prix par défaut en cas d'erreur
    }
}

// Charger les prix au chargement de la page
if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadShippingPrices);
    } else {
        // Le DOM est déjà chargé, appeler immédiatement
        loadShippingPrices();
    }
}

function updateRegionOptions() {
    const countrySelect = document.getElementById('country-select');
    const regionSelect = document.getElementById('region-select');
    const country = countrySelect?.value;
    
    if (!regionSelect) return;
    
    const regions = REGIONS_BY_COUNTRY[country] || [];
    
    regionSelect.innerHTML = '<option value="">Sélectionner une région</option>';
    regions.forEach(region => {
        const option = document.createElement('option');
        option.value = region.value;
        option.textContent = region.label;
        regionSelect.appendChild(option);
    });
    
    // Si aux Comores, afficher le prix de livraison
    updateShippingPrice();
}

function updateShippingPrice() {
    const countrySelect = document.getElementById('country-select');
    const regionSelect = document.getElementById('region-select');
    
    // Vérifier si une île des Comores est sélectionnée
    const islands = ['Grande Comore', 'Anjouan', 'Mohéli'];
    if (islands.includes(countrySelect?.value) && regionSelect?.value) {
        const price = SHIPPING_PRICES[regionSelect.value];
        if (price) {
            // Afficher le prix de livraison
            let priceInfo = document.getElementById('shipping-price-info');
            if (!priceInfo) {
                priceInfo = document.createElement('div');
                priceInfo.id = 'shipping-price-info';
                priceInfo.className = 'mt-2 p-3 bg-green-50 border border-green-200 rounded-lg';
                regionSelect.parentElement.appendChild(priceInfo);
            }
            priceInfo.innerHTML = `
                <div class="flex items-center text-sm text-green-800">
                    <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M8 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM15 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z"/>
                        <path d="M3 4a1 1 0 00-1 1v10a1 1 0 001 1h1.05a2.5 2.5 0 014.9 0H10a1 1 0 001-1V5a1 1 0 00-1-1H3zM14 7a1 1 0 00-1 1v6.05A2.5 2.5 0 0115.95 16H17a1 1 0 001-1v-5a1 1 0 00-.293-.707l-2-2A1 1 0 0015 7h-1z"/>
                    </svg>
                    <span><strong>Frais de livraison:</strong> ${price.toLocaleString('fr-FR')} KMF</span>
                </div>
            `;
        }
    } else {
        const priceInfo = document.getElementById('shipping-price-info');
        if (priceInfo) {
            priceInfo.remove();
        }
    }
}

// Calculer les frais de livraison pour une région donnée
function getShippingPrice(country, region) {
    const islands = ['Grande Comore', 'Anjouan', 'Mohéli'];
    if (islands.includes(country) && region) {
        return SHIPPING_PRICES[region] || 0;
    }
    return 0;
}

// Exporter les fonctions si module
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        REGIONS_BY_COUNTRY,
        SHIPPING_PRICES,
        updateRegionOptions,
        updateShippingPrice,
        getShippingPrice
    };
}
