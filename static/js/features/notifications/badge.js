import { eventBus } from "../../core/event-bus.js";

/**
 * Trova tutti i badge che contano le notifiche e registra il refresh.
 * Badge HTML atteso:
 *   <span id="nav-news-badge"
 *         hx-get="/notifiche/count/news"
 *         hx-trigger="notifications.refresh from:body"
 *         hx-swap="innerHTML"
 *         hx-target="this">0</span>
 */
export function initBadges() {
  console.log('[BADGE-DEBUG] Inizializzazione badge');
  
  // 1) Primo caricamento: scatena un refresh di tutti i badge HTMX
  console.log('[BADGE-DEBUG] Trigger refresh iniziale dei badge');
  htmx.trigger("body", "notifications.refresh");

  // Aggiungiamo un listener per tracciare quando viene triggerato il refresh
  document.body.addEventListener('notifications.refresh', function(event) {
    console.log('[BADGE-DEBUG] Evento notifications.refresh triggerato', {
      timestamp: new Date().toISOString(),
      source: event.detail || 'unknown'
    });
  });

  // Aggiungiamo un listener per le richieste HTMX dei badge
  htmx.on('htmx:beforeRequest', function(evt) {
    if (evt.detail.path && evt.detail.path.includes('/notifiche/count/')) {
      console.log('[BADGE-DEBUG] Richiesta aggiornamento badge:', {
        path: evt.detail.path,
        timestamp: new Date().toISOString()
      });
    }
  });

  htmx.on('htmx:afterRequest', function(evt) {
    if (evt.detail.path && evt.detail.path.includes('/notifiche/count/')) {
      console.log('[BADGE-DEBUG] Risposta aggiornamento badge:', {
        path: evt.detail.path,
        status: evt.detail.xhr.status,
        response: evt.detail.xhr.responseText,
        timestamp: new Date().toISOString()
      });
    }
  });

  // 2) Il refresh dei badge in risposta a nuove notifiche WebSocket
  // è gestito da `static/js/features/notifications/websocket.js`.
  // Quel file ascolta `new_notification` dall'event bus (emesso da `core/websocket.js`)
  // e poi esegue `htmx.trigger('body', 'notifications.refresh');`.
  // Quindi, un listener separato qui per un evento `notifications/new` è ridondante
  // e potenzialmente confuso se l'evento non viene emesso come previsto.
  // eventBus.on("notifications/new", () => {
  //   log.debug('Evento notifications/new ricevuto, aggiorno i badge.');
  //   htmx.trigger("body", "notifications.refresh");
  // });
}

function handleBadgeUpdate(message) {
    console.log("[BADGE] Ricevuto aggiornamento badge:", {
        message,
        timestamp: new Date().toISOString()
    });
    
    if (message && message.type === 'badge') {
        const { badge_type, count } = message;
        console.log("[BADGE] Aggiornamento specifico:", {
            badge_type,
            count,
            timestamp: new Date().toISOString()
        });
        updateBadge(badge_type, count);
    }
}

document.addEventListener('ws-message', function(e) {
    const message = e.detail;
    console.log("[BADGE] Messaggio WebSocket ricevuto:", message);
    
    if (message && message.type === 'badge') {
        console.log("[BADGE] Aggiornamento badge:", {
            badge_type: message.badge_type,
            count: message.count
        });
        updateBadge(message.badge_type, message.count);
    }
});

// Debug per OGNI aggiornamento badge
function refreshBadge(tipo) {
    console.log('🔴 [DEBUG-BADGE-AGGIORNAMENTO]', {
        timestamp: new Date().toISOString(),
        tipo: tipo,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
}

// Debug per OGNI evento badge
eventBus.on('notifications.refresh', function(data) {
    console.log('🔴 [DEBUG-BADGE-EVENTO]', {
        timestamp: new Date().toISOString(),
        datiCompleti: data,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
});

function updateBadge(count) {
    console.log('🏷️ [DEBUG-LINK-FLOW] Badge aggiornato:', {
        timestamp: new Date().toISOString(),
        count,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
    // ... existing code ...
}

// auto-bootstrap
initBadges();