/**
 * Gestore delle notifiche ricevute via WebSocket.
 * Ascolta l'event bus e chiama la funzione 'showToast'.
 */
import { eventBus } from "../../core/event-bus.js";
import { showToast } from "./toast.js";

console.log('[Notifications-WS] Inizializzazione sistema notifiche...');

function saveDebugLog(message) {
  const logs = JSON.parse(sessionStorage.getItem('debug_logs') || '[]');
  logs.push(message);
  sessionStorage.setItem('debug_logs', JSON.stringify(logs));
  console.log(message);
}

// Funzione helper per gestire gli eventi resource
function handleResourceEvent(event, message) {
  console.log('🔵 [WS-DEBUG] Ricevuto evento resource:', {
    event: event,
    message: message,
    timestamp: new Date().toISOString(),
    location: window.location.pathname,
    userInfo: window.userInfo
  });

  // Estrai i dati dal messaggio
  const eventData = message.item || message.data || {};
  console.log('🔵 [WS-DEBUG] Dati evento resource:', {
    ...eventData,
    timestamp: new Date().toISOString()
  });

  const { type: item_type, id: item_id, user_id: source_user_id, title: item_title, name: item_name } = eventData;
  
  const currentUserId = document.body.dataset.userId;
  const currentUserRole = document.body.dataset.userRole;

  // UI Refresh Logic
  let listElementId;
  let listRefreshUrl;

  if (item_type === 'ai_news') {
    listElementId = 'ai-news-list';
    listRefreshUrl = '/ai-news/list';
  } else if (item_type === 'link') {
    // Controlla se siamo nella home page o nella pagina dei link
    const isHomePage = window.location.pathname === '/';
    if (isHomePage) {
      // Emetti un evento per aggiornare gli highlights della home
      console.log('🔵 [WS-DEBUG] Siamo nella home, triggero evento highlights.refresh');
      eventBus.emit('highlights.refresh');
    } else {
      listElementId = 'links-list';
      listRefreshUrl = '/links/list';
    }
  }

  console.log('🔵 [WS-DEBUG] Tentativo refresh UI:', {
    timestamp: new Date().toISOString(),
    listElementId,
    listRefreshUrl,
    elementExists: document.getElementById(listElementId) ? 'SI' : 'NO',
    allElementIds: Array.from(document.querySelectorAll('[id]')).map(el => el.id)
  });

  if (listElementId && listRefreshUrl) {
    const listElement = document.getElementById(listElementId);
    if (listElement) {
      console.log('🔵 [WS-DEBUG] Eseguo refresh HTMX:', {
        timestamp: new Date().toISOString(),
        target: listElementId,
        url: listRefreshUrl
      });
      htmx.ajax('GET', listRefreshUrl, {
        target: `#${listElementId}`,
        swap: 'outerHTML'
      }).then(() => {
        console.log('🔵 [WS-DEBUG] Refresh HTMX completato con successo');
      }).catch(err => {
        console.error('🔴 [WS-DEBUG] Errore refresh HTMX:', err);
      });
    } else {
      console.log('🔵 [WS-DEBUG] Elemento non trovato per refresh');
    }
  }

  // Toast Logic per altri utenti
  if (source_user_id === currentUserId || currentUserRole === 'admin') {
    console.log('🔵 [WS-DEBUG] Toast ignorato:', {
      reason: source_user_id === currentUserId ? 'utente corrente è la fonte' : 'utente è admin',
      source_user_id,
      currentUserId,
      currentUserRole
    });
    return;
  }

  // Cerca il titolo in diversi campi possibili
  const itemTitle = item_title || item_name || eventData.title || eventData.name || 'Risorsa sconosciuta';
  console.log('[WS-DEBUG] Titolo estratto:', {
    item_title,
    item_name,
    eventData_title: eventData.title,
    eventData_name: eventData.name,
    finalTitle: itemTitle
  });

  const eventMessages = {
    add: {
      title: 'Nuova Risorsa Aggiunta',
      body: `Un nuovo elemento '${itemTitle}' (${item_type}) è stato aggiunto.`,
      type: 'success'
    },
    update: {
      title: 'Risorsa Aggiornata',
      body: `L'elemento '${itemTitle}' (${item_type}) è stato aggiornato.`,
      type: 'info'
    },
    delete: {
      title: 'Risorsa Eliminata',
      body: `L'elemento '${itemTitle}' (${item_type}) è stato eliminato.`,
      type: 'warning'
    }
  };

  const messageConfig = eventMessages[event];
  if (messageConfig) {
    console.log('[WS-DEBUG] Mostro toast per evento resource:', {
      event,
      item_type,
      itemTitle
    });
    showToast(messageConfig);

    // Non triggeriamo il badge refresh qui perché verrà fatto dalla notifica
    console.log('[WS-DEBUG] Badge refresh sarà gestito dalla notifica');
  }
}

function handleNotification(message) {
  console.log('[WS-DEBUG] Processando notifica:', {
    message: message,
    timestamp: new Date().toISOString()
  });

  const notificationData = message.data || message;
  const { title, body, level, action, resource, source_user_id } = notificationData;
  
  const currentUserId = document.body.dataset.userId;
  const currentUserRole = document.body.dataset.userRole;

  // Non mostrare il toast se l'utente corrente è quello che ha eseguito l'azione
  // o se l'utente è admin
  if (source_user_id === currentUserId || currentUserRole === 'admin') {
    console.log('[WS-DEBUG] Toast ignorato:', { 
      reason: source_user_id === currentUserId ? 'utente corrente è la fonte' : 'utente è admin',
      source_user_id,
      currentUserId,
      currentUserRole
    });
    return;
  }

  // Mostra il toast
  if (title && body) {
    console.log('[WS-DEBUG] Mostro toast per notifica:', {
      title,
      level
    });
    showToast({
      title: title,
      body: body,
      type: level || 'info'
    });
  }

  // Aggiorna i badge
  console.log('[WS-DEBUG] Triggering badge refresh da notifica:', {
    action,
    resource
  });
  htmx.trigger('body', 'notifications.refresh', {
    source: 'notification',
    action: action,
    resource: resource
  });
}

// Registra i listener per gli eventi
eventBus.on('new_notification', handleNotification);
eventBus.on('resource/add', (message) => handleResourceEvent('add', message));
eventBus.on('resource/update', (message) => handleResourceEvent('update', message));
eventBus.on('resource/delete', (message) => handleResourceEvent('delete', message));

// Inizializza il sistema di notifiche WebSocket
export function initNotificationsWebSocket() {
  console.log('[WS-DEBUG] Inizializzazione WebSocket notifiche');

  eventBus.on("ws:message", (message) => {
    console.log('[WS-DEBUG] Ricevuto messaggio WebSocket:', {
      type: message.type,
      data: message.data,
      timestamp: new Date().toISOString()
    });

    if (message.type === "new_notification" || message.type === "notification") {
      handleNotification(message);
    }
  });
} 