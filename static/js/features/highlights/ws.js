import { eventBus } from "/static/js/core/event-bus.js";

// Funzione per loggare lo stato del DOM
function logDOMState(prefix) {
    const cards = document.querySelectorAll('.highlight-card, .card');
    console.log(`🏠 [DEBUG-WS-${prefix}] Stato DOM:`, {
        timestamp: new Date().toISOString(),
        cards: Array.from(cards).map(card => ({
            id: card.dataset.id,
            type: card.dataset.type,
            title: card.querySelector('.card-title')?.textContent,
            branch: card.dataset.branch,
            employmentType: card.dataset.employmentType,
            html: card.outerHTML.substring(0, 500) + (card.outerHTML.length > 500 ? '...' : '')
        })),
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
}

// Osservatore per le mutazioni DOM
const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        console.log('🏠 [DEBUG-WS-MUTATION] Mutazione DOM:', {
            timestamp: new Date().toISOString(),
            type: mutation.type,
            target: {
                id: mutation.target.id,
                className: mutation.target.className,
                html: mutation.target.outerHTML?.substring(0, 500)
            },
            addedNodes: Array.from(mutation.addedNodes).map(node => ({
                type: node.nodeType,
                html: node.outerHTML?.substring(0, 500)
            })),
            removedNodes: Array.from(mutation.removedNodes).map(node => ({
                type: node.nodeType,
                html: node.outerHTML?.substring(0, 500)
            }))
        });
    });
});

// Inizia a osservare le mutazioni quando il DOM è pronto
document.addEventListener('DOMContentLoaded', () => {
    const highlightsContainer = document.getElementById('home-page-highlights');
    if (highlightsContainer) {
        observer.observe(highlightsContainer, { 
            childList: true, 
            subtree: true, 
            attributes: true,
            characterData: true 
        });
        console.log('🏠 [DEBUG-WS-INIT] Observer attivato per #home-page-highlights');
    }
});

// Funzione per aggiornare gli highlights
async function refreshHighlights() {
    console.log('🏠 [DEBUG-WS-REFRESH-START] Inizio refresh highlights');
    
    // Log dello stato pre-refresh
    logDOMState('PRE-REFRESH');
    
    try {
        console.log('🏠 [DEBUG-WS-FETCH-START] Inizio fetch /home/highlights/partial');
        const response = await fetch('/home/highlights/partial');
        
        // Debug response object
        console.log('🏠 [DEBUG-WS-RESPONSE] Dettagli risposta:', {
            timestamp: new Date().toISOString(),
            ok: response.ok,
            status: response.status,
            statusText: response.statusText,
            headers: Object.fromEntries(response.headers.entries())
        });

        // Debug response text
        const responseText = await response.text();
        console.log('🏠 [DEBUG-WS-RESPONSE-TEXT] Contenuto risposta:', {
            timestamp: new Date().toISOString(),
            length: responseText.length,
            preview: responseText.substring(0, 100),
            isHtml: responseText.trim().startsWith('<'),
            containsScript: responseText.includes('<script>'),
            containsHighlightCard: responseText.includes('highlight-card')
        });
        
        console.log('🏠 [DEBUG-WS-FETCH-END] Risposta ricevuta:', {
            timestamp: new Date().toISOString(),
            responseLength: response.headers.get('content-length'),
            responsePreview: responseText.substring(0, 100)
        });

        console.log('🏠 [DEBUG-WS-UPDATE-START] Aggiornamento DOM');
        const container = document.getElementById('home-page-highlights');
        
        // Debug container pre-update
        console.log('🏠 [DEBUG-WS-CONTAINER-PRE] Stato container pre-update:', {
            timestamp: new Date().toISOString(),
            found: !!container,
            id: container?.id,
            childNodes: container?.childNodes.length,
            innerHTML: container?.innerHTML.substring(0, 100),
            cards: container?.querySelectorAll('.highlight-card, .card').length
        });

        if (!container) {
            throw new Error('Container highlights non trovato');
        }
        
        // Debug pre-assignment
        console.log('🏠 [DEBUG-WS-PRE-ASSIGN] Pre assegnazione innerHTML:', {
            timestamp: new Date().toISOString(),
            currentLength: container.innerHTML.length,
            newLength: responseText.length,
            currentCards: container.querySelectorAll('.highlight-card, .card').length
        });

        container.innerHTML = responseText;
        
        // Debug post-assignment
        console.log('🏠 [DEBUG-WS-POST-ASSIGN] Post assegnazione innerHTML:', {
            timestamp: new Date().toISOString(),
            success: true,
            newLength: container.innerHTML.length,
            newCards: container.querySelectorAll('.highlight-card, .card').length
        });
        
        // Log dello stato post-refresh
        logDOMState('POST-REFRESH');
        
        console.log('🏠 [DEBUG-WS-UPDATE-END] DOM aggiornato con successo');
    } catch (error) {
        console.error('🏠 [DEBUG-WS-ERROR] Errore durante il refresh:', {
            timestamp: new Date().toISOString(),
            error: error.message,
            stack: error.stack
        });
    }
}

// Registra handler per gli eventi WebSocket
eventBus.on('highlights.refresh', () => {
    console.log('🏠 [DEBUG-WS-EVENT] Ricevuto evento highlights.refresh');
    refreshHighlights();
});

// Debug iniziale
console.log('🏠 [DEBUG-WS-LOAD] Script WS highlights caricato');
logDOMState('INITIAL');

// Intercetta TUTTI gli eventi che potrebbero aggiornare la home
eventBus.on('resource/add', function(data) {
    console.log('🏠 [DEBUG-HOME-EVENT-ADD]', {
        timestamp: new Date().toISOString(),
        eventData: data,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
    refreshHighlights();
});

eventBus.on('resource/delete', refreshHighlights);
eventBus.on('resource/update', refreshHighlights);
eventBus.on('refresh_home_highlights', function(data) {
    console.log('🏠 [DEBUG-HOME-EVENT-REFRESH]', {
        timestamp: new Date().toISOString(),
        eventData: data,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
    refreshHighlights();
}); 