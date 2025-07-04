/**
 * Punto di ingresso (entry-point) per i moduli JavaScript core dell'applicazione.
 * Il suo unico scopo è importare gli altri moduli essenziali per avviarli.
 */

// Importa il gestore WebSocket. L'atto stesso di importarlo
// avvierà la logica di connessione contenuta al suo interno.
import '/static/js/core/websocket.js';

// Importa il gestore per il "pallino" di stato del WebSocket.
// Si metterà in ascolto degli eventi emessi da websocket.js.
import '/static/js/core/ws-dot.js';

// Importa il bridge per HTMX, se necessario per la comunicazione
// da WebSocket a HTMX.
import '/static/js/core/htmx-ws.js';

// Importa il gestore dei redirect dopo le azioni CRUD
import '/static/js/core/redirects.js';

console.log('🔄 [DEBUG-LINK-FLOW] Inizio caricamento bootstrap');

// Intercetta tutte le richieste HTTP prima di qualsiasi altra cosa
const originalFetch = window.fetch;
window.fetch = async function(...args) {
    const url = args[0]?.url || args[0];
    console.log('🌐 [DEBUG-LINK-FLOW] Richiesta fetch:', {
        timestamp: new Date().toISOString(),
        url: url,
        options: args[1],
        stack: new Error().stack,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
    const response = await originalFetch.apply(this, args);
    const clone = response.clone();
    try {
        const text = await clone.text();
        console.log('🌐 [DEBUG-LINK-FLOW] Risposta fetch:', {
            timestamp: new Date().toISOString(),
            url: url,
            status: response.status,
            headers: Object.fromEntries(response.headers.entries()),
            body: text.substring(0, 1000) + (text.length > 1000 ? '...' : ''),
            utente: {
                branch: window.userInfo?.branch,
                employmentType: window.userInfo?.employment_type,
                role: window.userInfo?.role
            }
        });
    } catch (e) {
        console.error('🔴 [DEBUG-LINK-FLOW] Errore lettura risposta fetch:', e);
    }
    return response;
};

// Intercetta tutte le richieste XMLHttpRequest
const originalXHR = window.XMLHttpRequest;
window.XMLHttpRequest = function() {
    const xhr = new originalXHR();
    const originalOpen = xhr.open;
    const originalSend = xhr.send;

    xhr.open = function() {
        console.log('🌐 [DEBUG-LINK-FLOW] Richiesta XHR:', {
            timestamp: new Date().toISOString(),
            method: arguments[0],
            url: arguments[1],
            stack: new Error().stack,
            utente: {
                branch: window.userInfo?.branch,
                employmentType: window.userInfo?.employment_type,
                role: window.userInfo?.role
            }
        });
        return originalOpen.apply(this, arguments);
    };

    xhr.send = function() {
        this.addEventListener('load', function() {
            console.log('🌐 [DEBUG-LINK-FLOW] Risposta XHR:', {
                timestamp: new Date().toISOString(),
                url: this.responseURL,
                status: this.status,
                headers: this.getAllResponseHeaders(),
                body: this.responseText.substring(0, 1000) + (this.responseText.length > 1000 ? '...' : ''),
                utente: {
                    branch: window.userInfo?.branch,
                    employmentType: window.userInfo?.employment_type,
                    role: window.userInfo?.role
                }
            });
        });
        return originalSend.apply(this, arguments);
    };

    return xhr;
};

console.log('[Bootstrap] Moduli core inizializzati.'); 