import { initToasts } from "./toast.js";
import "./badge.js";        // importa per side-effect
import "./websocket.js";    // importa per side-effect
import "./confirmations.js";

/**
 * Entry-point notifiche.
 * Al momento inizializza solo i toast per essere ri-usati da altri moduli
 * (WS handler, AI-News, ecc.).
 */
export function initNotifications() {
  initToasts();
}

// esegui subito: il layout importerà solo questo file
initNotifications();

console.log("[Notifications] Modulo principale inizializzato.");

document.addEventListener('ws-message', function(e) {
    const message = e.detail;
    console.log("[NOTIFICATIONS] Messaggio WebSocket ricevuto:", message);
    
    if (message && message.type === 'notification') {
        console.log("[NOTIFICATIONS] Nuova notifica:", {
            type: message.notification_type,
            content: message.content,
            timestamp: new Date().toISOString()
        });
    }
});

// Debug per OGNI notifica
eventBus.on('new_notification', function(data) {
    console.log('🔔 [DEBUG-NOTIFICA]', {
        timestamp: new Date().toISOString(),
        tipo: data.tipo,
        datiCompleti: data,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
});

// Debug per OGNI evento risorsa
eventBus.on('resource/add', function(data) {
    console.log('📦 [DEBUG-RISORSA-AGGIUNTA]', {
        timestamp: new Date().toISOString(),
        tipo: data.type,
        datiCompleti: data,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
});

// Debug per OGNI aggiornamento home
eventBus.on('refresh_home_highlights', function(data) {
    console.log('🏠 [DEBUG-HOME-AGGIORNAMENTO]', {
        timestamp: new Date().toISOString(),
        datiCompleti: data,
        utente: {
            branch: window.userInfo?.branch,
            employmentType: window.userInfo?.employment_type,
            role: window.userInfo?.role
        }
    });
}); 