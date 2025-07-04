from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from app.deps import require_admin, get_current_user
from bson import ObjectId
from datetime import datetime
import json
import logging

logger = logging.getLogger("intranet")

from app.utils.notification_helpers import create_action_notification_payload, create_admin_confirmation_trigger
from app.ws_broadcast import broadcast_message, broadcast_resource_event

# Aggiunto il prefisso "/links" per allineare le rotte con il frontend
links_router = APIRouter(prefix="/links", tags=["links"])

@links_router.post("/new", dependencies=[Depends(require_admin)])
async def create_link(
    request: Request, 
    title: str = Form(...), 
    url: str = Form(...), 
    branch: str = Form("*"), 
    employment_type: str = Form("*"), 
    show_on_home: bool = Form(False), 
    current_user: dict = Depends(get_current_user)
):
    print(f"🔗 [DEBUG-LINK-CREATE] Creazione link:", {
        "title": title,
        "branch": branch,
        "employment_type": employment_type,
        "show_on_home": show_on_home,
        "creator": {
            "id": str(current_user["_id"]),
            "branch": current_user.get("branch"),
            "employment_type": current_user.get("employment_type")
        }
    })
    db = request.app.state.db
    
    # Converti employment_type in lista
    employment_type_list = [employment_type] if employment_type != "*" else ["*"]
    
    print(f"🔗 [DEBUG-LINK-CREATE] Employment type processato:", {
        "originale": employment_type,
        "convertito": employment_type_list
    })
    
    # Crea il link nel DB
    link_data = {
        "title": title.strip(),
        "url": url.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list,
        "show_on_home": show_on_home,
        "created_at": datetime.utcnow()
    }
    result = await db.links.insert_one(link_data)
    new_id = str(result.inserted_id)

    # 1. Salva la notifica nel database per il conteggio dei badge e la persistenza
    from app.notifiche import crea_notifica
    await crea_notifica(
        request=request,
        tipo="link",
        titolo=f"Nuovo link aggiunto: {title.strip()}",
        branch=branch.strip(),
        id_risorsa=new_id,
        employment_type=employment_type_list,
        source_user_id=str(current_user["_id"])
    )

    # 2. Notifica WebSocket ai client connessi
    payload_toast = create_action_notification_payload(
        'create',
        'link',
        title.strip(),
        str(current_user["_id"])
    )
    logger.debug(f"[LINKS] Invio notifica toast con payload: {payload_toast}")
    logger.debug(f"[LINKS] Parametri broadcast: branch={branch}, employment_type={employment_type_list}, exclude_user={str(current_user['_id'])}")
    await broadcast_message(
        payload_toast,
        branch=branch, 
        employment_type=employment_type_list,
        exclude_user_id=str(current_user["_id"])
    )

    # 3. Broadcast dell'evento generico per aggiornare UI (es. liste)
    logger.debug(f"[LINKS] Invio resource event per link: id={new_id}, title={title.strip()}")
    await broadcast_resource_event(
        event="add",
        item_type="link",
        item_id=new_id,
        user_id=str(current_user["_id"]),
        title=title.strip(),
        db=db
    )

    # 3. Aggiornamento highlights (se necessario)
    if show_on_home:
        print(f"🔗 [DEBUG-LINK-HIGHLIGHT] Aggiunta agli highlights:", {
            "link_id": new_id,
            "title": title,
            "branch": branch,
            "employment_type": employment_type_list
        })
        
        await db.home_highlights.insert_one({
            "type": "link",
            "object_id": new_id,
            "title": title.strip(),
            "url": url.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "created_at": datetime.utcnow()
        })
        
        # Aggiorna highlights home
        try:
            payload_highlight = {
                "type": "refresh_home_highlights",
                "data": {
                    "branch": branch,
                    "employment_type": employment_type_list
                }
            }
            print(f"🔗 [DEBUG-LINK-BROADCAST] Invio broadcast highlights:", payload_highlight)
            await broadcast_message(payload_highlight, branch=branch, employment_type=employment_type_list)
        except Exception as e:
            print(f"🔗 [DEBUG-LINK-ERROR] Errore broadcast highlights:", e)

    # 4. Risposta di conferma per l'admin con redirect ritardato
    print(f"[DEBUG] Preparazione risposta")
    resp = Response(status_code=200)
    # Prima mostra la conferma
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', title)
    # Poi chiudi la modale e fai il redirect
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirect-to-links": "/links"
    })
    print(f"[DEBUG] Headers risposta: {dict(resp.headers)}")
    return resp

@links_router.get("/", response_class=HTMLResponse)
async def list_links(request: Request, current_user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    branch = current_user.get("branch")
    print("\n🔍 [DEBUG-LIST-LINKS] ==================")
    print(f"👤 Utente che richiede i link:")
    print(f"   - Branch: {branch}")
    print(f"   - Employment Type: {employment_type}")
    print(f"   - Role: {current_user.get('role')}")
    
    if current_user["role"] == "admin":
        print("👑 Utente admin - mostra tutti i link")
        mongo_filter = {}
    else:
        if employment_type:
            employment_type_conditions = [
                {"employment_type": "*"},  # Link per tutti i tipi
                {"employment_type": employment_type}  # Tipo specifico
            ]
            print(f"📋 Condizioni employment_type: {employment_type_conditions}")
        else:
            employment_type_conditions = [
                {"employment_type": "*"},  # Link per tutti i tipi
                {"employment_type": {"$exists": True}}  # Qualsiasi valore se non definito
            ]
            print("⚠️ Utente senza employment_type!")
            print(f"📋 Condizioni employment_type default: {employment_type_conditions}")

        if branch:
            branch_conditions = [
                {"branch": "*"},  # Link per tutte le branch
                {"branch": branch}  # Branch specifica
            ]
            print(f"🏢 Condizioni branch: {branch_conditions}")
        else:
            branch_conditions = [
                {"branch": "*"},  # Link per tutte le branch
                {"branch": {"$exists": True}}  # Qualsiasi branch se non definita
            ]
            print("⚠️ Utente senza branch!")
            print(f"🏢 Condizioni branch default: {branch_conditions}")

        mongo_filter = {
            "$and": [
                {"$or": branch_conditions},
                {"$or": employment_type_conditions}
            ]
        }
    
    print(f"\n🔎 Filtro MongoDB finale:")
    print(f"{mongo_filter}")
    
    links = await db.links.find(mongo_filter).to_list(length=None)
    print(f"\n📊 Risultati trovati: {len(links)}")
    for link in links:
        print(f"\n🔗 Link: {link.get('title')}")
        print(f"   - Branch: {link.get('branch')}")
        print(f"   - Employment Type: {link.get('employment_type')}")
        print(f"   - Show on home: {link.get('show_on_home', False)}")
    print("==========================================\n")

    # --- Segna tutte le notifiche 'link' come lette per l'utente ---
    def get_emp_type_conditions(user_emp_type):
        if not user_emp_type:
            return [
                {"employment_type": {"$exists": False}},
                {"employment_type": []},
                {"employment_type": {"$exists": True}}  # Qualsiasi valore
            ]
        return [
            {"employment_type": {"$exists": False}},  # Legacy
            {"employment_type": []},  # Lista vuota = tutti
            {"employment_type": {"$in": ["*"]}},  # "*" = tutti
            {"employment_type": {"$in": [user_emp_type]}}  # Match specifico
        ]

    user_id_str = str(current_user["_id"])
    notifications_to_mark_read_filter = {
        "tipo": "link",
        "branch": {"$in": ["*", branch] if branch else ["*"]},
        "$or": get_emp_type_conditions(employment_type),
        "letta_da": {"$ne": user_id_str}
    }
    update_result = await db.notifiche.update_many(
        notifications_to_mark_read_filter,
        {"$addToSet": {"letta_da": user_id_str}}
    )
    print(f"[DEBUG] Segnate {update_result.modified_count} notifiche link come lette per {user_id_str} visitando /links")
    
    return request.app.state.templates.TemplateResponse(
        "links/links_index.html",
        {
            "request": request,
            "links": links,
            "current_user": current_user
        }
    )

@links_router.get(
    "/{link_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_link_form(
    request: Request,
    link_id: str,
    user = Depends(get_current_user)
):
    db = request.app.state.db
    link = await db.links.find_one({"_id": ObjectId(link_id)})
    if not link:
        raise HTTPException(404, "Link non trovato")
    branches = ["*", "HQE", "HQ ITALIA", "HQIA"]
    employment_types = ["*", "TD", "TI", "AP", "CO"]
    is_htmx = request.headers.get("hx-request") == "true"
    template = "links/links_edit_partial.html" if is_htmx else "links/links_edit.html"
    return request.app.state.templates.TemplateResponse(
        template,
        {
            "request": request,
            "l": link,
            "branches": branches,
            "employment_types": employment_types,
            "branch": link.get("branch", "*"),
            "employment_type": (link.get("employment_type", ["*"])[0] if isinstance(link.get("employment_type", ["*"]), list) else link.get("employment_type", ["*"])),
            "show_on_home": link.get("show_on_home", False),
            "current_user": user,
        }
    )

@links_router.delete("/{link_id}", dependencies=[Depends(require_admin)])
async def delete_link(request: Request, link_id: str, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    
    # Verifica che l'ID sia valido e che il link esista prima di procedere.
    try:
        object_id_to_delete = ObjectId(link_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID del link non valido.")
        
    link_to_delete = await db.links.find_one({"_id": object_id_to_delete})
    if not link_to_delete:
        # Se il link non viene trovato nel DB, si solleva un 404.
        # Questo è il comportamento corretto.
        raise HTTPException(status_code=404, detail="Link non trovato.")
    
    title = link_to_delete.get('title', 'Link sconosciuto')
    branch = link_to_delete.get('branch', '*')
    employment_type = link_to_delete.get('employment_type', ['*'])

    # Esegui l'eliminazione
    await db.links.delete_one({"_id": object_id_to_delete})

    # Elimina le notifiche associate a questo link
    # Questo aiuta a mantenere il conteggio dei badge accurato dopo l'eliminazione di un link.
    delete_notifiche_result = await db.notifiche.delete_many({"id_risorsa": link_id, "tipo": "link"})
    print(f"[DEBUG] Eliminate {delete_notifiche_result.deleted_count} notifiche associate al link {link_id}")
    
    # 1. Notifica WebSocket SOLO ai destinatari
    payload = create_action_notification_payload(
        'delete',
        'link',
        title,
        str(current_user["_id"])
    )
    await broadcast_message(
        payload, 
        branch=branch, 
        employment_type=employment_type,  # Passa la lista direttamente
        exclude_user_id=str(current_user["_id"])
    )

    # 2. Aggiornamento highlights
    was_on_home = link_to_delete.get("show_on_home", False)
    await db.home_highlights.delete_one({"type": "link", "object_id": link_id}) # Assicurati di specificare anche il type

    if was_on_home:
        try:
            # Invia refresh_home_highlights mirato a chi poteva vedere il link
            payload_highlight = {
                "type": "refresh_home_highlights",
                "data": {
                    "branch": branch, # branch del link eliminato
                    "employment_type": employment_type # employment_type del link eliminato
                }
            }
            await broadcast_message(payload_highlight, branch=branch, employment_type=employment_type)
            print(f"[DEBUG] Broadcast refresh_home_highlights per eliminazione link inviato a branch '{branch}', emp_type '{employment_type}'.")
        except Exception as e:
            print(f"[WebSocket] Errore broadcast refresh_home_highlights (delete link): {e}")

    # Invia comunque l'evento generico di eliminazione risorsa
    await broadcast_resource_event(
        event="delete",
        item_type="link",
        item_id=link_id,
        user_id=str(current_user["_id"])
    )

    # 3. Conferma immediata SOLO per l'admin
    resp = Response(status_code=200)
    admin_trigger = create_admin_confirmation_trigger('delete', title)
    print("[DEBUG-LINKS-DELETE] Payload conferma admin:", admin_trigger)
    resp.headers["HX-Trigger"] = admin_trigger
    return resp

@links_router.post("/{link_id}/edit", dependencies=[Depends(require_admin)])
async def edit_link_submit(
    request: Request, 
    link_id: str, 
    title: str = Form(...), 
    url: str = Form(...), 
    branch: str = Form(...), 
    employment_type: list[str] = Form(...), 
    show_on_home: bool = Form(False), 
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    await db.links.update_one(
        {"_id": ObjectId(link_id)}, 
        {"$set": {
            "title": title.strip(),
            "url": url.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type,
            "show_on_home": show_on_home
        }}
    )

    # 1. Notifica WebSocket SOLO ai destinatari
    payload = create_action_notification_payload(
        'update',
        'link',
        title.strip(),
        str(current_user["_id"])
    )
    await broadcast_message(
        payload, 
        branch=branch, 
        employment_type=employment_type,  # Passa la lista direttamente
        exclude_user_id=str(current_user["_id"])
    )

    # 2. Aggiornamento highlights
    updated_link_for_highlight = await db.links.find_one({"_id": ObjectId(link_id)})

    # Determina lo stato precedente di show_on_home e i criteri di filtro
    # Questo è un po' complicato perché non abbiamo lo stato 'prima' della modifica direttamente qui.
    # Per una logica precisa, bisognerebbe recuperare il link *prima* dell'update_one.
    # Semplificazione: se `show_on_home` è true ora, o se era true (ipotizzando che `delete_one` da highlights avvenga solo se non più in home),
    # allora inviamo un refresh.

    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "link", "object_id": link_id},
            {"$set": {
                "type": "link", "object_id": link_id, "title": title.strip(), "url": url.strip(),
                "branch": branch.strip(), "employment_type": employment_type,
                "created_at": updated_link_for_highlight.get("created_at", datetime.utcnow())
            }},
            upsert=True
        )
        # Invia broadcast mirato per refresh (aggiunta o modifica di un highlight esistente)
        try:
            payload_highlight = {
                "type": "refresh_home_highlights",
                "data": {"branch": branch.strip(), "employment_type": employment_type}
            }
            await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type)
        except Exception as e:
            print(f"[WebSocket] Errore broadcast refresh_home_highlights (update link add/mod): {e}")
    else:
        # Se show_on_home è false, il link non deve essere/rimanere negli highlights
        delete_result = await db.home_highlights.delete_one({"type": "link", "object_id": link_id})
        if delete_result.deleted_count > 0: # Era in home ed è stato rimosso
            # Invia broadcast mirato per refresh per notificare la rimozione
            # È importante usare i criteri del link *prima* della modifica se sono cambiati,
            # ma qui per semplicità usiamo quelli attuali (branch, employment_type).
            # Se i criteri sono cambiati E show_on_home è diventato false, alcuni utenti potrebbero non ricevere
            # il refresh per la rimozione. Una soluzione più robusta recupererebbe lo stato precedente.
            try:
                payload_highlight = {
                    "type": "refresh_home_highlights",
                    "data": {"branch": branch.strip(), "employment_type": employment_type}
                }
                await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type)
            except Exception as e:
                print(f"[WebSocket] Errore broadcast refresh_home_highlights (update link remove): {e}")

    await broadcast_resource_event(
        event="update",
        item_type="link",
        item_id=link_id,
        user_id=str(current_user["_id"])
    )

    # 3. Conferma immediata SOLO per l'admin
    updated_link = await db.links.find_one({"_id": ObjectId(link_id)})
    resp = request.app.state.templates.TemplateResponse(
        "links/links_row_partial.html",
        {"request": request, "link": updated_link, "current_user": current_user}
    )
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('update', title)
    return resp

@links_router.get("/new", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def new_link_form(request: Request):
    template = "links/links_new_partial.html" if request.headers.get("hx-request") == "true" else "links/links_new.html"
    return request.app.state.templates.TemplateResponse(template, {"request": request})

@links_router.get("/list", response_class=HTMLResponse)
async def list_links(request: Request, current_user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    branch = current_user.get("branch")
    
    print("\n🔍 [DEBUG-LIST-LINKS] ==================")
    print(f"👤 Utente che richiede i link:")
    print(f"   - Branch: {branch}")
    print(f"   - Employment Type: {employment_type}")
    print(f"   - Role: {current_user.get('role')}")
    
    if current_user["role"] == "admin":
        print("👑 Utente admin - mostra tutti i link")
        mongo_filter = {}
    else:
        employment_type_conditions = [
            {"employment_type": "*"},  # Link per tutti i tipi
            {"employment_type": employment_type}  # Tipo specifico
        ]
        
        branch_conditions = [
            {"branch": "*"},  # Link per tutte le branch
            {"branch": branch}  # Branch specifica
        ]
        
        mongo_filter = {
            "$and": [
                {"$or": branch_conditions},
                {"$or": employment_type_conditions}
            ]
        }
    
    print(f"\n🔍 Filtro MongoDB:")
    print(mongo_filter)
    
    links = await db.links.find(mongo_filter).sort("created_at", -1).to_list(None)
    
    print(f"\n📋 Link trovati ({len(links)}):")
    for link in links:
        print(f"\n- {link.get('title')}:")
        print(f"   Branch: {link.get('branch')}")
        print(f"   Employment Type: {link.get('employment_type')}")
        print(f"   Created At: {link.get('created_at')}")
    
    print("\n==========================================")

    # Renderizza SOLO il frammento della lista dei link
    return request.app.state.templates.TemplateResponse(
        "links/links_list_partial.html",
        {
            "request": request,
            "links": links,
            "current_user": current_user
        }
    )
