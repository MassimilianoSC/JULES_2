import { eventBus } from '../../core/event-bus.js';
import { showToast } from '../notifications/toast.js';

// Gestione aggiornamenti lista link
document.addEventListener('DOMContentLoaded', function() {
    console.log("🔄 [DEBUG-LINK-FLOW] Inizializzazione modulo links");
    
    // Configura HTMX per l'aggiornamento automatico
    const linksList = document.getElementById('links-list');
    if (linksList) {
        console.log("📋 [DEBUG-LINK-SETUP] Configurazione lista links:", {
            element: linksList,
            userInfo: window.userInfo,
            pathname: window.location.pathname
        });
        linksList.setAttribute('hx-get', '/links/list');
        linksList.setAttribute('hx-trigger', 'resource.refresh from:body');
        linksList.setAttribute('hx-swap', 'outerHTML');

        // Aggiungi listener per il pre-refresh
        linksList.addEventListener('htmx:beforeRequest', function(e) {
            console.log("🔄 [DEBUG-LINK-REFRESH] Iniziando refresh lista:", {
                timestamp: new Date().toISOString(),
                trigger: e.detail.triggerSpec,
                currentContent: linksList.children.length + " elementi",
                userInfo: window.userInfo
            });
        });

        // Aggiungi listener per il post-refresh
        linksList.addEventListener('htmx:afterRequest', function(e) {
            console.log("✅ [DEBUG-LINK-REFRESH] Completato refresh lista:", {
                timestamp: new Date().toISOString(),
                success: !e.detail.failed,
                newContent: linksList.children.length + " elementi",
                userInfo: window.userInfo
            });
        });
    }
});

// Monitor updates to links list
document.addEventListener('ws-message', function(e) {
    const message = e.detail;
    console.log("🔗 [DEBUG-LINK-WS] Messaggio WebSocket ricevuto:", {
        timestamp: new Date().toISOString(),
        type: message?.type,
        data: message?.data,
        userInfo: window.userInfo,
        pathname: window.location.pathname
    });
    
    if (message?.type === 'refresh_home_highlights') {
        console.log("🏠 [DEBUG-LINK-HOME] Richiesto refresh highlights home:", {
            timestamp: new Date().toISOString(),
            data: message?.data,
            userInfo: window.userInfo
        });
    }
    
    // Gestisci sia i messaggi di tipo resource/ che le notifiche di nuovi link
    if ((message && message.type && message.type.startsWith('resource/')) || 
        (message && message.type === 'new_notification' && message.data && message.data.resource === 'link' && message.data.action === 'create')) {
        // Determina l'azione in base al tipo di messaggio
        const action = message.type.startsWith('resource/') ? message.type.split('/')[1] : message.data?.action;
        const isLink = message.type.startsWith('resource/') ? (message.item?.type === 'link') : (message.data?.resource === 'link');
        
        if (isLink) {
            const linkData = message.type.startsWith('resource/') ? message.item : { type: 'link' };
            console.log("🔗 [LINKS-RESOURCE] Aggiornamento link:", {
                timestamp: new Date().toISOString(),
                action,
                messageType: message.type,
                link: linkData,
                userBranch: window.userInfo?.branch,
                userEmploymentType: window.userInfo?.employment_type,
                linkBranch: linkData.branch,
                linkEmploymentType: linkData.employment_type,
                shouldUpdate: window.location.pathname === '/links'
            });

            // Trigger refresh when on links page
            if (window.location.pathname === '/links') {
                htmx.trigger('#links-list', 'resource.refresh');
                console.log('🔗 [LINKS-WS-REFRESH] Trigger refresh inviato:', {
                    timestamp: new Date().toISOString(),
                    location: '/links',
                    target: '#links-list'
                });
            }
            // Update highlights when on home page
            else if (window.location.pathname === '/') {
                eventBus.emit('highlights.refresh');
                console.log('🔗 [LINKS-WS-REFRESH] Trigger highlights refresh inviato:', {
                    timestamp: new Date().toISOString(),
                    location: '/'
                });
            }
        }
    }
});

eventBus.on('resource/add', function(data) {
    if (data.type === 'link') {
        console.log('🔗 [LINKS-ADD] Nuovo link:', {
            timestamp: new Date().toISOString(),
            data,
            userInfo: {
                branch: window.userInfo?.branch,
                employmentType: window.userInfo?.employment_type,
                role: window.userInfo?.role
            },
            location: window.location.pathname,
            shouldRefresh: window.location.pathname === '/links'
        });
        
        // Debug pre-refresh
        const linksList = document.getElementById('links-list');
        console.log('🔗 [LINKS-DOM-PRE] Stato lista pre-refresh:', {
            timestamp: new Date().toISOString(),
            exists: !!linksList,
            childCount: linksList?.children.length,
            html: linksList?.innerHTML.substring(0, 100)
        });

        // Trigger HTMX refresh
        if (window.location.pathname === '/links') {
            htmx.trigger('#links-list', 'resource.refresh');
            console.log('🔗 [LINKS-REFRESH] Trigger refresh inviato:', {
                timestamp: new Date().toISOString(),
                location: '/links',
                target: '#links-list'
            });
        }
        // Se siamo nella home, aggiorna gli highlights
        else if (window.location.pathname === '/') {
            eventBus.emit('highlights.refresh');
            console.log('🔗 [LINKS-REFRESH] Trigger highlights refresh inviato:', {
                timestamp: new Date().toISOString(),
                location: '/'
            });
        }
    }
});

// Gestione eventi resource/delete specifici per i link
eventBus.on('resource/delete', function(data) {
    if (data.type === 'link') {
        console.log('🔗 [LINKS-DELETE] Link eliminato:', {
            timestamp: new Date().toISOString(),
            data,
            location: window.location.pathname
        });

        // Trigger HTMX refresh
        if (window.location.pathname === '/links') {
            htmx.trigger('#links-list', 'resource.refresh');
        }
        // Se siamo nella home, aggiorna gli highlights
        else if (window.location.pathname === '/') {
            eventBus.emit('highlights.refresh');
        }
    }
});

// Ascolta eventi di notifica specifici per i link
eventBus.on('new_notification', function(data) {
    if (data.resource === 'link') {
        console.log('🔗 [LINKS-NOTIFY] Notifica link:', {
            timestamp: new Date().toISOString(),
            data,
            userInfo: {
                branch: window.userInfo?.branch,
                employmentType: window.userInfo?.employment_type,
                role: window.userInfo?.role
            },
            location: window.location.pathname
        });

        // Aggiorna il badge delle notifiche
        htmx.trigger('body', 'notifications.refresh');
    }
});

// Monitor updates to links list
document.addEventListener('htmx:beforeRequest', function(e) {
    if (e.detail.pathInfo.requestPath === '/links/list') {
        console.log("🔄 [DEBUG-LINK-REQUEST] Richiesta HTMX in partenza:", {
            timestamp: new Date().toISOString(),
            path: e.detail.pathInfo.requestPath,
            headers: e.detail.headers,
            userInfo: window.userInfo
        });
    }
});

document.addEventListener('htmx:afterRequest', function(e) {
    if (e.detail.pathInfo.requestPath === '/links/list') {
        console.log("✅ [DEBUG-LINK-RESPONSE] Risposta HTMX ricevuta:", {
            timestamp: new Date().toISOString(),
            path: e.detail.pathInfo.requestPath,
            status: e.detail.xhr.status,
            responseType: e.detail.xhr.responseType,
            responseText: e.detail.xhr.responseText.substring(0, 100) + "..." // primi 100 caratteri
        });
    }
});