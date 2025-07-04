import { eventBus } from '../../core/event-bus.js';
import { showToast } from '../notifications/toast.js';

// Gestione aggiornamenti lista contatti
document.addEventListener('DOMContentLoaded', function() {
    console.log("🔄 [DEBUG-CONTACT-FLOW] Inizializzazione modulo contatti");

    // Configura HTMX per l'aggiornamento automatico
    const contactsList = document.getElementById('contacts-list'); // Sostituito #links-list con #contacts-list
    if (contactsList) {
        console.log("📋 [DEBUG-CONTACT-SETUP] Configurazione lista contatti:", {
            element: contactsList,
            userInfo: window.userInfo,
            pathname: window.location.pathname
        });
        contactsList.setAttribute('hx-get', '/contatti/list'); // Sostituito /links/list con /contatti/list
        contactsList.setAttribute('hx-trigger', 'resource.refresh from:body');
        contactsList.setAttribute('hx-swap', 'outerHTML');

        // Aggiungi listener per il pre-refresh
        contactsList.addEventListener('htmx:beforeRequest', function(e) {
            console.log("🔄 [DEBUG-CONTACT-REFRESH] Iniziando refresh lista contatti:", { // Modificato log
                timestamp: new Date().toISOString(),
                trigger: e.detail.triggerSpec,
                currentContent: contactsList.children.length + " elementi",
                userInfo: window.userInfo
            });
        });

        // Aggiungi listener per il post-refresh
        contactsList.addEventListener('htmx:afterRequest', function(e) {
            console.log("✅ [DEBUG-CONTACT-REFRESH] Completato refresh lista contatti:", { // Modificato log
                timestamp: new Date().toISOString(),
                success: !e.detail.failed,
                newContent: contactsList.children.length + " elementi",
                userInfo: window.userInfo
            });
        });
    }
});

// Monitor updates to contacts list
document.addEventListener('ws-message', function(e) {
    const message = e.detail;
    console.log("📞 [DEBUG-CONTACT-WS] Messaggio WebSocket ricevuto:", { // Modificato log e emoji
        timestamp: new Date().toISOString(),
        type: message?.type,
        data: message?.data,
        userInfo: window.userInfo,
        pathname: window.location.pathname
    });

    if (message?.type === 'refresh_home_highlights') {
        console.log("🏠 [DEBUG-CONTACT-HOME] Richiesto refresh highlights home:", { // Modificato log
            timestamp: new Date().toISOString(),
            data: message?.data,
            userInfo: window.userInfo
        });
    }

    // Gestisci sia i messaggi di tipo resource/ che le notifiche di nuovi contatti
    if ((message && message.type && message.type.startsWith('resource/')) ||
        (message && message.type === 'new_notification' && message.data && message.data.resource === 'contact' && message.data.action === 'create')) { // Sostituito 'link' con 'contact'
        // Determina l'azione in base al tipo di messaggio
        const action = message.type.startsWith('resource/') ? message.type.split('/')[1] : message.data?.action;
        const isContact = message.type.startsWith('resource/') ? (message.item?.type === 'contact') : (message.data?.resource === 'contact'); // Sostituito 'link' con 'contact'

        if (isContact) {
            const contactData = message.type.startsWith('resource/') ? message.item : { type: 'contact' }; // Sostituito 'link' con 'contact'
            console.log("📞 [CONTACTS-RESOURCE] Aggiornamento contatto:", { // Modificato log e emoji
                timestamp: new Date().toISOString(),
                action,
                messageType: message.type,
                contact: contactData, // Sostituito 'link' con 'contact'
                userBranch: window.userInfo?.branch,
                userEmploymentType: window.userInfo?.employment_type,
                contactBranch: contactData.branch, // Sostituito 'linkBranch' con 'contactBranch'
                contactEmploymentType: contactData.employment_type, // Sostituito 'linkEmploymentType' con 'contactEmploymentType'
                shouldUpdate: window.location.pathname === '/contatti' // Sostituito /links con /contatti
            });

            // Trigger refresh when on contacts page
            if (window.location.pathname === '/contatti') { // Sostituito /links con /contatti
                htmx.trigger('#contacts-list', 'resource.refresh'); // Sostituito #links-list con #contacts-list
                console.log('📞 [CONTACTS-WS-REFRESH] Trigger refresh inviato:', { // Modificato log
                    timestamp: new Date().toISOString(),
                    location: '/contatti', // Sostituito /links con /contatti
                    target: '#contacts-list' // Sostituito #links-list con #contacts-list
                });
            }
            // Update highlights when on home page
            else if (window.location.pathname === '/') {
                eventBus.emit('highlights.refresh');
                console.log('📞 [CONTACTS-WS-REFRESH] Trigger highlights refresh inviato:', { // Modificato log
                    timestamp: new Date().toISOString(),
                    location: '/'
                });
            }
        }
    }
});

eventBus.on('resource/add', function(data) {
    if (data.type === 'contact') { // Sostituito 'link' con 'contact'
        console.log('📞 [CONTACTS-ADD] Nuovo contatto:', { // Modificato log e emoji
            timestamp: new Date().toISOString(),
            data,
            userInfo: {
                branch: window.userInfo?.branch,
                employmentType: window.userInfo?.employment_type,
                role: window.userInfo?.role
            },
            location: window.location.pathname,
            shouldRefresh: window.location.pathname === '/contatti' // Sostituito /links con /contatti
        });

        // Debug pre-refresh
        const contactsList = document.getElementById('contacts-list'); // Sostituito #links-list con #contacts-list
        console.log('📞 [CONTACTS-DOM-PRE] Stato lista pre-refresh:', { // Modificato log
            timestamp: new Date().toISOString(),
            exists: !!contactsList,
            childCount: contactsList?.children.length,
            html: contactsList?.innerHTML.substring(0, 100)
        });

        // Trigger HTMX refresh
        if (window.location.pathname === '/contatti') { // Sostituito /links con /contatti
            htmx.trigger('#contacts-list', 'resource.refresh'); // Sostituito #links-list con #contacts-list
            console.log('📞 [CONTACTS-REFRESH] Trigger refresh inviato:', { // Modificato log
                timestamp: new Date().toISOString(),
                location: '/contatti', // Sostituito /links con /contatti
                target: '#contacts-list' // Sostituito #links-list con #contacts-list
            });
        }
        // Se siamo nella home, aggiorna gli highlights
        else if (window.location.pathname === '/') {
            eventBus.emit('highlights.refresh');
            console.log('📞 [CONTACTS-REFRESH] Trigger highlights refresh inviato:', { // Modificato log
                timestamp: new Date().toISOString(),
                location: '/'
            });
        }
    }
});

// Gestione eventi resource/delete specifici per i contatti
eventBus.on('resource/delete', function(data) {
    if (data.type === 'contact') { // Sostituito 'link' con 'contact'
        console.log('📞 [CONTACTS-DELETE] Contatto eliminato:', { // Modificato log e emoji
            timestamp: new Date().toISOString(),
            data,
            location: window.location.pathname
        });

        // Trigger HTMX refresh
        if (window.location.pathname === '/contatti') { // Sostituito /links con /contatti
            htmx.trigger('#contacts-list', 'resource.refresh'); // Sostituito #links-list con #contacts-list
        }
        // Se siamo nella home, aggiorna gli highlights
        else if (window.location.pathname === '/') {
            eventBus.emit('highlights.refresh');
        }
    }
});

// Ascolta eventi di notifica specifici per i contatti
eventBus.on('new_notification', function(data) {
    if (data.resource === 'contact') { // Sostituito 'link' con 'contact'
        console.log('📞 [CONTACTS-NOTIFY] Notifica contatto:', { // Modificato log e emoji
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

// Monitor updates to contacts list
document.addEventListener('htmx:beforeRequest', function(e) {
    if (e.detail.pathInfo.requestPath === '/contatti/list') { // Sostituito /links/list con /contatti/list
        console.log("🔄 [DEBUG-CONTACT-REQUEST] Richiesta HTMX in partenza:", { // Modificato log
            timestamp: new Date().toISOString(),
            path: e.detail.pathInfo.requestPath,
            headers: e.detail.headers,
            userInfo: window.userInfo
        });
    }
});

document.addEventListener('htmx:afterRequest', function(e) {
    if (e.detail.pathInfo.requestPath === '/contatti/list') { // Sostituito /links/list con /contatti/list
        console.log("✅ [DEBUG-CONTACT-RESPONSE] Risposta HTMX ricevuta:", { // Modificato log
            timestamp: new Date().toISOString(),
            path: e.detail.pathInfo.requestPath,
            status: e.detail.xhr.status,
            responseType: e.detail.xhr.responseType,
            responseText: e.detail.xhr.responseText.substring(0, 100) + "..." // primi 100 caratteri
        });
    }
});
