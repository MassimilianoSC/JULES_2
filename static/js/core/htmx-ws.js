/**
 * Bridge per connettere i messaggi WebSocket in arrivo a HTMX.
 * Questo modulo ascolta i messaggi sull'istanza globale WebSocket e, se
 * contengono istruzioni specifiche per HTMX (come HX-Trigger), le esegue.
 */
import { ws } from './websocket.js'; // Importa l'istanza WebSocket dal modulo core

// Aggiunge un listener CORRETTO per l'evento 'message' del WebSocket.
// Questa è la correzione principale per l'errore 'addEventListener'.
ws.addEventListener('message', function(event) {
    // Log immediato del messaggio raw
    console.log("[HTMX-WS-RAW] Messaggio ricevuto:", event.data);
    
    try {
        const message = JSON.parse(event.data);
        console.log("[HTMX-WS] Messaggio parsato:", message);
        
        // Emetti evento custom per altri handler
        const customEvent = new CustomEvent('ws-message', { detail: message });
        document.dispatchEvent(customEvent);
        
        // Processa il messaggio per HTMX
        if (message.headers && message.headers['HX-Trigger']) {
            const triggers = message.headers['HX-Trigger'];
            console.log('[HTMX-WS] Trigger HTMX:', triggers);
            
            // HX-Trigger può essere una semplice stringa (nome dell'evento)
            // o un oggetto JSON per passare dati più complessi.
            if (typeof triggers === 'string') {
                htmx.trigger('body', triggers, message.detail || {});
            } else if (typeof triggers === 'object') {
                for (const eventName in triggers) {
                    htmx.trigger('body', eventName, triggers[eventName]);
                }
            }
        }
    } catch (e) {
        console.error('[HTMX-WS] Errore nel processare il messaggio:', e);
    }
});

function processMessage(event) {
    try {
        const message = JSON.parse(event.data);
        
        // Log specifico per ogni tipo di messaggio
        if (message.type === 'toast') {
            console.log("[HTMX-WS] Toast ricevuto:", message);
        } else if (message.type && message.type.startsWith('resource/')) {
            console.log("[HTMX-WS] Resource event ricevuto:", message);
        } else if (message.type === 'badge') {
            console.log("[HTMX-WS] Badge update ricevuto:", message);
        }
        
        // Controlla se il messaggio dal server contiene un header 'HX-Trigger'.
        // Questo è un pattern potente che permette al server di scatenare
        // eventi e comportamenti sul client in modo asincrono.
        if (message.headers && message.headers['HX-Trigger']) {
            const triggers = message.headers['HX-Trigger'];
            console.log('[HTMX-DEBUG] Trigger ricevuto:', {
                triggers,
                timestamp: new Date().toISOString(),
                source: 'WebSocket'
            });
            
            // HX-Trigger può essere una semplice stringa (nome dell'evento)
            // o un oggetto JSON per passare dati più complessi.
            if (typeof triggers === 'string') {
                htmx.trigger('body', triggers, message.detail || {});
            } else if (typeof triggers === 'object') {
                for (const eventName in triggers) {
                    htmx.trigger('body', eventName, triggers[eventName]);
                }
            }
        }
    } catch (e) {
        console.error('[HTMX-WS] Errore nel processare il messaggio:', e);
    }
}

console.log('[HTMX-WS] Bridge WebSocket -> HTMX inizializzato e in ascolto.');

// Intercetta OGNI messaggio HTMX
document.addEventListener('htmx:beforeRequest', function(event) {
    console.log('🟡 [DEBUG-LINK-FLOW] HTMX richiesta:', {
        timestamp: new Date().toISOString(),
        url: event.detail.pathInfo.requestPath,
        metodo: event.detail.verb,
        headers: event.detail.headers,
        trigger: event.detail.triggeringEvent,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
});

document.addEventListener('htmx:afterRequest', function(event) {
    console.log('🟢 [DEBUG-LINK-FLOW] HTMX risposta:', {
        timestamp: new Date().toISOString(),
        url: event.detail.pathInfo.requestPath,
        status: event.detail.xhr.status,
        risposta: event.detail.xhr.responseText,
        headers: event.detail.xhr.getAllResponseHeaders(),
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
});

// Aggiungo listener per ogni refresh della pagina
window.addEventListener('load', function() {
    console.log('🔄 [DEBUG-LINK-FLOW] Pagina caricata/ricaricata:', {
        timestamp: new Date().toISOString(),
        url: window.location.href,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
}); 