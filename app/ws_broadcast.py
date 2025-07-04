from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Optional
import json
import logging
import base64
from datetime import datetime
from bson import ObjectId
from itsdangerous import URLSafeSerializer, TimestampSigner, BadSignature
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("intranet")

# Lista globale delle connessioni attive
active_ws_connections: List[WebSocket] = []

# --- Gestione Serializer per Cookie di Sessione ---

class JSONSerializer:
    """ Serializzatore JSON compatto, come quello di Starlette. """
    def dumps(self, obj):
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    def loads(self, data):
        return json.loads(data)

def make_starlette_serializer(secret: str) -> URLSafeSerializer:
    """
    Replica il serializer di Starlette per garantire la compatibilità
    nella lettura dei cookie di sessione.
    """
    import hashlib
    return URLSafeSerializer(
        secret,
        salt="starlette.sessions",
        serializer=JSONSerializer(),
        signer=TimestampSigner,
        signer_kwargs={
            "key_derivation": "django-concat",
            "digest_method": hashlib.sha1,
        },
    )

# --- Autenticazione e Gestione Utente ---

async def get_ws_user(websocket: WebSocket) -> Optional[Dict]:
    """
    Recupera l'utente autenticato dal cookie di sessione, con fallback.
    """
    raw_cookie = websocket.cookies.get("session")
    if not raw_cookie:
        logger.error("[WS AUTH] Nessun cookie 'session' trovato.")
        return None

    secret_key = websocket.app.state.secret_key
    serializer = make_starlette_serializer(secret_key)

    try:
        # Tentativo standard con verifica della firma
        data = serializer.loads(raw_cookie)
    except BadSignature:
        logger.warning("[WS AUTH] Firma del cookie non valida! Eseguo fallback...")
        try:
            # Estrae il payload senza verifica della firma
            payload_b64, *_ = raw_cookie.split(".", 1)
            payload_b64 += "=" * (-len(payload_b64) % 4) # Aggiungi padding
            data_json = base64.urlsafe_b64decode(payload_b64).decode()
            data = json.loads(data_json)
            logger.warning("[WS AUTH] Fallback riuscito: uso payload non verificato.")
        except Exception as e:
            logger.error(f"[WS AUTH] Fallback fallito: impossibile estrarre payload. Errore: {e}")
            return None

    user_id = data.get("user_id")
    if not user_id:
        logger.warning("[WS AUTH] 'user_id' non trovato nei dati di sessione.")
        return None

    db = websocket.app.state.db
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        logger.error(f"[WS AUTH] Utente con id '{user_id}' non trovato nel database.")
    return user


# --- Funzioni di Broadcast ---

async def broadcast_message(
    payload: Dict,
    branch: Optional[str] = None,
    employment_type: Optional[List[str]] = None,
    exclude_user_id: Optional[str] = None,
    target_user_id: Optional[str] = None
):
    logger.info("="*50)
    logger.info("[DEBUG-WS] INIZIO BROADCAST MESSAGE")
    logger.info(f"[DEBUG-WS] Payload ricevuto (raw): {payload}")
    logger.info(f"[DEBUG-WS] Tipo payload: {type(payload)}")
    logger.info(f"[DEBUG-WS] Lunghezza payload: {len(payload) if payload else 0}")
    
    if not active_ws_connections:
        logger.error("[DEBUG-WS] ❌ Nessuna connessione attiva")
        return

    if not payload:
        logger.error("[DEBUG-WS] ❌ Payload vuoto!")
        logger.error(f"[DEBUG-WS] Stack trace completo:", exc_info=True)
        return

    try:
        message_to_send = json.dumps(payload, ensure_ascii=False)
        logger.info(f"[DEBUG-WS] Messaggio serializzato: {message_to_send}")
        logger.info(f"[DEBUG-WS] Lunghezza messaggio serializzato: {len(message_to_send)}")
    except Exception as e:
        logger.error(f"[DEBUG-WS] ❌ Errore serializzazione JSON: {e}")
        logger.error(f"[DEBUG-WS] Payload problematico: {payload}")
        logger.error("[DEBUG-WS] Stack trace completo:", exc_info=True)
        return

    if not message_to_send or message_to_send == "{}":
        logger.error(f"[DEBUG-WS] ❌ Messaggio vuoto dopo serializzazione!")
        logger.error(f"[DEBUG-WS] Payload originale: {payload}")
        logger.error("[DEBUG-WS] Stack trace completo:", exc_info=True)
        return

    recipients = []
    
    logger.debug(f"[WS-BROADCAST] INIZIO broadcast_message:")
    logger.debug(f"[WS-BROADCAST] - Tipo messaggio: {payload.get('type')}")
    logger.debug(f"[WS-BROADCAST] - Target User ID: {target_user_id}")
    logger.debug(f"[WS-BROADCAST] - Branch filtro: {branch}")
    logger.debug(f"[WS-BROADCAST] - Employment type filtro: {employment_type}")
    logger.debug(f"[WS-BROADCAST] - User ID da escludere: {exclude_user_id}")
    logger.debug(f"[WS-BROADCAST] - Payload completo: {json.dumps(payload, indent=2)}")
    logger.debug(f"[WS-BROADCAST] - Connessioni attive: {len(active_ws_connections)}")

    # Itera su una copia per rimuovere in sicurezza le connessioni morte
    for connection in active_ws_connections[:]:
        if connection.client_state.name != "CONNECTED":
            continue

        try:
            user_info = connection.state.user
            user_id = str(user_info.get("_id"))
            user_role = user_info.get("role")
            user_branch = user_info.get("branch")
            user_emp_type = user_info.get("employment_type")
            
            print(f"📡 [DEBUG-BROADCAST-USER] Valutazione utente:", {
                "user_id": user_id,
                "user_branch": user_branch,
                "user_emp_type": user_emp_type,
                "matches_branch": branch == "*" or user_branch == branch,
                "matches_emp_type": not employment_type or "*" in employment_type or user_emp_type in employment_type
            })

            # Se è specificato un target_user_id, invia solo a quell'utente
            if target_user_id:
                if user_id == target_user_id:
                    logger.debug(f"[WS-BROADCAST] - INCLUSO: corrisponde a target_user_id")
                    recipients.append(connection)
                else:
                    logger.debug(f"[WS-BROADCAST] - ESCLUSO: non corrisponde a target_user_id")
                continue # Passa alla prossima connessione
            
            # Applica i filtri
            if exclude_user_id and user_id == exclude_user_id:
                print(f"📡 [DEBUG-BROADCAST-SKIP] Utente escluso: {user_id}")
                continue

            if branch and branch != "*" and user_branch != branch:
                print(f"📡 [DEBUG-BROADCAST-SKIP] Branch non corrispondente: {user_branch} != {branch}")
                continue

            if employment_type and "*" not in employment_type and user_emp_type not in employment_type:
                print(f"📡 [DEBUG-BROADCAST-SKIP] Employment type non corrispondente: {user_emp_type} not in {employment_type}")
                continue
            
            logger.debug(f"[WS-BROADCAST] - INCLUSO: tutti i filtri passati")
            recipients.append(connection)

        except Exception as e:
            print(f"📡 [DEBUG-BROADCAST-ERROR] Errore:", str(e))
            if connection in active_ws_connections:
                active_ws_connections.remove(connection)
    
    # Invia il messaggio a tutti i destinatari validi
    logger.debug(f"[WS-BROADCAST] Invio a {len(recipients)} destinatari:")
    for recipient in recipients:
        try:
            user_info = recipient.state.user
            logger.debug(f"[WS-BROADCAST] - Invio a {user_info.get('email')} (ruolo: {user_info.get('role')})")
            print(f"📡 [DEBUG-BROADCAST-SEND] Invio messaggio a utente:", {
                "user_id": user_info.get("_id"),
                "message_type": payload.get("type")
            })
            await recipient.send_text(message_to_send)
        except Exception as e:
            logger.error(f"[WS-BROADCAST] Errore durante l'invio: {e}")
            if recipient in active_ws_connections:
                active_ws_connections.remove(recipient)

    logger.debug(f"[WS-BROADCAST] Broadcast completato: {len(recipients)} destinatari")


async def broadcast_resource_event(event: str, *, item_type: str, item_id: str, user_id: str, title: Optional[str] = None, db: Optional[AsyncIOMotorClient] = None):
    """ Helper per inviare eventi di aggiornamento risorse (es. highlights) a tutti. """
    logger.debug(f"[WS-RESOURCE] INIZIO broadcast_resource_event: type={item_type}, event={event}, id={item_id}")
    
    if db is not None:
        # Recupera branch e employment_type dalla risorsa
        collection_map = {
            "link": "links",
            "contact": "contacts",
            "document": "documents",
            "news": "news",
            "ai_news": "ai_news"
        }
        
        collection = collection_map.get(item_type)
        if not collection:
            logger.warning(f"[WS-RESOURCE] Tipo risorsa non riconosciuto: {item_type}")
            return
            
        try:
            logger.debug(f"[WS-RESOURCE] Cerco risorsa in collezione {collection}")
            item = await db[collection].find_one({"_id": ObjectId(item_id)})
            if not item:
                logger.warning(f"[WS-RESOURCE] Risorsa non trovata: {item_type} {item_id}")
                return
                
            branch = item.get("branch", "*")
            employment_type = item.get("employment_type", "*")
            
            # Converti employment_type in lista
            if isinstance(employment_type, str):
                employment_type = [employment_type]
            
            logger.debug(f"[WS-RESOURCE] Risorsa trovata:")
            logger.debug(f"[WS-RESOURCE] - Branch: {branch}")
            logger.debug(f"[WS-RESOURCE] - Employment Type: {employment_type}")
            logger.debug(f"[WS-RESOURCE] - Item completo: {item}")
            
            item_data = {
                "type": item_type,
                "id": item_id
            }
            if title:
                item_data["title"] = title

            logger.debug(f"[WS-RESOURCE] Invio resource event con payload: {item_data}")
            logger.debug(f"[WS-RESOURCE] Filtri applicati: branch={branch}, employment_type={employment_type}")
            
            await broadcast_message({
                "type": f"resource/{event}",
                "item": item_data,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }, branch=branch, employment_type=employment_type)
            
            logger.debug("[WS-RESOURCE] Broadcast completato con successo usando i filtri")
            return
            
        except Exception as e:
            logger.error(f"[WS-RESOURCE] Errore durante il broadcast resource event: {e}")
            logger.error(f"[WS-RESOURCE] Traceback completo:", exc_info=True)
            # Continua con il fallback
    else:
        logger.warning("[WS-RESOURCE] Database non fornito, uso fallback senza filtri")
    
    # Fallback al broadcast senza filtri
    item_data = {
        "type": item_type,
        "id": item_id
    }
    if title:
        item_data["title"] = title

    logger.debug(f"[WS-RESOURCE] FALLBACK: invio resource event senza filtri: {item_data}")
    await broadcast_message({
        "type": f"resource/{event}",
        "item": item_data,
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    })
    logger.debug("[WS-RESOURCE] Broadcast fallback completato")


# --- Endpoint WebSocket Principale ---

async def websocket_main(websocket: WebSocket):
    """
    Punto di ingresso e gestore del ciclo di vita per ogni connessione WebSocket.
    """
    try:
        await websocket.accept()

        user = await get_ws_user(websocket)
        if not user:
            await websocket.close(code=1008, reason="Authentication failed")
            return

        # Memorizza i dati dell'utente nello stato della connessione per un accesso rapido
        websocket.state.user = {
            "_id": user["_id"],
            "email": user.get("email"),
            "branch": user.get("branch"),
            "employment_type": user.get("employment_type"),
            "role": user.get("role")
        }
        
        active_ws_connections.append(websocket)
        logger.info(f"[WS] Connessione stabilita per: {user.get('email')}. Totale connessioni: {len(active_ws_connections)}")

        # Loop principale per mantenere la connessione e gestire i messaggi
        while True:
            try:
                # Verifica se la connessione è ancora attiva
                if websocket.client_state.name != "CONNECTED":
                    logger.info(f"[WS] Client non più connesso per {user.get('email')}")
                    break

                message = await websocket.receive_json()
                logger.debug(f"[WS] Messaggio ricevuto da {user.get('email')}: {message}")
                
                if not message:
                    logger.warning(f"[WS] Messaggio vuoto ricevuto da {user.get('email')}")
                    continue
                
                # Rispondi all'heartbeat del client per mantenere la connessione viva
                if message.get("type") == "heartbeat":
                    try:
                        response = {"type": "heartbeat", "status": "acknowledged"}
                        logger.debug(f"[WS] Invio risposta heartbeat a {user.get('email')}: {response}")
                        await websocket.send_json(response)
                    except Exception as e:
                        logger.error(f"[WS] Errore durante l'invio della risposta heartbeat a {user.get('email')}: {e}")
                        break  # Esci dal loop se non riusciamo a inviare la risposta
                else:
                    # Gestisci altri tipi di messaggi inviando un ACK
                    try:
                        response = {"type": "ack", "status": "received", "original_type": message.get("type")}
                        logger.debug(f"[WS] Invio ACK a {user.get('email')}: {response}")
                        await websocket.send_json(response)
                    except Exception as e:
                        logger.error(f"[WS] Errore durante l'invio dell'ACK a {user.get('email')}: {e}")
                        break  # Esci dal loop se non riusciamo a inviare la risposta

            except WebSocketDisconnect:
                logger.info(f"[WS] Client disconnesso per {user.get('email')}")
                break
            except json.JSONDecodeError as e:
                logger.error(f"[WS] Errore di decodifica JSON per {user.get('email')}: {e}")
                continue
            except Exception as e:
                logger.error(f"[WS] Errore durante la gestione del messaggio per {user.get('email')}: {e}")
                break  # Esci dal loop per qualsiasi altro errore

    except Exception as e:
        logger.error(f"[WS] Errore inatteso per {user.get('email') if user else 'utente sconosciuto'}: {e}")
    finally:
        # Pulisci la connessione
        if websocket in active_ws_connections:
            active_ws_connections.remove(websocket)
            logger.info(f"[WS] Connessione rimossa. Totale connessioni: {len(active_ws_connections)}")
        
        # Chiudi la connessione se non è già stata chiusa
        try:
            await websocket.close()
        except Exception as e:
            logger.debug(f"[WS] Errore durante la chiusura del websocket: {e}")  # Debug perché è un errore non critico