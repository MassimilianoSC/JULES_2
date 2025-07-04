from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from app.deps import require_admin, get_current_user
from app.utils.save_with_notifica import save_and_notify
from app.models.contacts_model import ContactIn, ContactOut
from bson import ObjectId
from datetime import datetime
from app.constants import DEFAULT_BRANCHES, DEFAULT_HIRE_TYPES
from typing import Annotated
from app.notifiche import crea_notifica
from app.ws_broadcast import broadcast_message, broadcast_resource_event
from app.utils.notification_helpers import create_action_notification_payload, create_admin_confirmation_trigger
import json

contatti_router = APIRouter(tags=["contatti"])

@contatti_router.post(
    "/contatti/new",
    response_class=Response,
    dependencies=[Depends(require_admin)]
)
async def create_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    bu: str = Form(None),
    team: str = Form(None),
    branch: str = Form(...),
    employment_type: str = Form(...),
    work_branch: str = Form(...),
    show_on_home: Annotated[bool, Form()] = False,
    current_user: dict = Depends(require_admin)
):
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    db = request.app.state.db
    # Assicura che employment_type sia una lista, come in links.py
    # Se arriva una stringa singola, la mettiamo in una lista.
    # Se è già una lista (es. da un form con multiple select), usiamo quella.
    # Se è None o vuota, la trattiamo come una lista vuota per coerenza.
    if isinstance(employment_type, str):
        employment_type_list = [employment_type] if employment_type else []
    elif isinstance(employment_type, list):
        employment_type_list = employment_type
    else:
        employment_type_list = [] # Default a lista vuota se non fornito o tipo inatteso

    # 1. Operazione DB
    contact_data = {
        "name": name.strip(),
        "email": email.strip(),
        "phone": (phone or "").strip(),
        "bu": (bu or "").strip() or None,
        "team": (team or "").strip() or None,
        "branch": branch,
        "employment_type": employment_type_list,
        "work_branch": work_branch,
        "show_on_home": bool(show_on_home),
        "created_at": datetime.utcnow()
    }
    result = await db.contatti.insert_one(contact_data)
    new_id = str(result.inserted_id)

    # 2. Notifica nel DB per badge
    await crea_notifica(
        request=request,
        tipo="contatto",
        titolo=f"Nuovo contatto aggiunto: {name.strip()}", # Titolo più descrittivo come in links
        branch=branch,
        id_risorsa=new_id,
        employment_type=employment_type_list,
        source_user_id=str(current_user["_id"]) # Aggiunto source_user_id come in links
    )

    # 3. Toast notification
    payload_toast = create_action_notification_payload(
        'create',
        'contatto',
        name.strip(),
        str(current_user["_id"])
    )
    await broadcast_message(
        payload_toast,
        branch=branch,
        employment_type=employment_type_list, # Usare la lista
        exclude_user_id=str(current_user["_id"])
    )

    # 4. Broadcast evento risorsa
    await broadcast_resource_event(
        event="add",
        item_type="contact",
        item_id=new_id,
        user_id=str(current_user["_id"]),
        title=name.strip(), # Aggiunto title come in links (anche se non specificato se db è necessario qui)
        db=db # Aggiunto db come in links
    )

    # 5. Aggiornamento highlights (se necessario)
    if show_on_home:
        highlight_data = {
            "type": "contact",
            "object_id": new_id,
            "title": name.strip(),
            "created_at": contact_data["created_at"], # Usa la stessa datetime di creazione
            "branch": branch,
            "employment_type": employment_type_list,
            "email": email.strip(),
            "phone": (phone or "").strip(),
            "bu": (bu or "").strip() or None,
            "team": (team or "").strip() or None,
            "work_branch": work_branch
        }
        await db.home_highlights.update_one( # Usare update_one con upsert=True o insert_one
            {"type": "contact", "object_id": new_id}, # Criterio per l'upsert
            {"$set": highlight_data}, # Dati da inserire/aggiornare
            upsert=True
        )
        payload_highlight = {
            "type": "refresh_home_highlights",
            "data": {
                "branch": branch,
                "employment_type": employment_type_list
            }
        }
        await broadcast_message(payload_highlight, branch=branch, employment_type=employment_type_list)

    # 6. Risposta con conferma admin
    resp = Response(status_code=200)
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', name.strip())
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirectToContatti": "/contatti" # Allineato con la richiesta originale per i contatti
    })
    return resp

@contatti_router.get("/contatti", response_class=HTMLResponse)
async def list_contacts(
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    branch = current_user.get("branch")
    if current_user["role"] == "admin" or not employment_type:
        mongo_filter = {}
    else:
        mongo_filter = {
            "$and": [
                {
                    "$or": [
                        {"branch": "*"},
                        {"branch": branch}
                    ]
                },
                {
                    "$or": [
                        {"employment_type": {"$elemMatch": {"$in": [employment_type, "*"]}}},
                        {"employment_type": {"$exists": False}},
                        {"employment_type": []}
                    ]
                }
            ]
        }
    contacts = await db.contatti.find(mongo_filter).sort("created_at", -1).to_list(None)
    if request.headers.get("HX-Request") == "true":
        return request.app.state.templates.TemplateResponse(
            "contatti/contatti_list_partial.html",
            {"request": request, "contacts": contacts, "current_user": current_user}
        )
    else:
        return request.app.state.templates.TemplateResponse(
            "contatti/contatti_index.html",
            {"request": request, "contacts": contacts, "current_user": current_user}
        )

@contatti_router.get(
    "/contatti/{contact_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_contact_form(
    request: Request,
    contact_id: str,
    user = Depends(get_current_user)
):
    print("[DEBUG MODALE] Richiesta edit contatto ricevuta")
    print("[DEBUG MODALE] Contact ID:", contact_id)
    
    db = request.app.state.db
    contact = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    print("[DEBUG MODALE] Contatto trovato:", contact)
    
    if not contact:
        print("[DEBUG MODALE] Contatto non trovato!")
        raise HTTPException(404, "Contatto non trovato")
    
    branches = await db.branches.distinct("name")
    if not branches:
        print("[DEBUG MODALE] Usando branches di default")
        branches = DEFAULT_BRANCHES
    print("[DEBUG MODALE] Branches:", branches)
    
    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        print("[DEBUG MODALE] Usando hire_types di default")
        hire_types = DEFAULT_HIRE_TYPES
    print("[DEBUG MODALE] Hire types:", hire_types)
    
    # Controllo se il contatto è in evidenza
    highlight = await db.home_highlights.find_one({"type": "contact", "object_id": str(contact_id)})
    show_on_home = bool(highlight)
    print("[DEBUG MODALE] Show on home:", show_on_home)
    
    print("[DEBUG MODALE] Rendering template edit_partial.html")
    return request.app.state.templates.TemplateResponse(
        "contatti/contatti_edit_partial.html",
        {
            "request": request,
            "c": contact,
            "user": user,
            "branches": branches,
            "hire_types": hire_types,
            "show_on_home": show_on_home
        }
    )

@contatti_router.post("/contatti/{contact_id}/edit", dependencies=[Depends(require_admin)])
async def edit_contact_submit(
    request: Request,
    contact_id: str,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    bu: str = Form(None),
    team: str = Form(None),
    branch: str = Form(...),
    employment_type: list[str] = Form(...), # Aspetta una lista di stringhe
    work_branch: str = Form(None),
    show_on_home: bool = Form(False),
    current_user: dict = Depends(get_current_user) # Rinominato user a current_user per coerenza
):
    db = request.app.state.db

    # employment_type arriva già come list[str] da Form(...)
    # Non serve la conversione vista in create_contact se il form invia correttamente
    # Assicuriamoci che sia sempre una lista per coerenza con il modello dati
    employment_type_list = employment_type if isinstance(employment_type, list) else [employment_type]


    # 1. Operazione DB: Aggiorna il contatto
    update_data = {
        "name": name.strip(),
        "email": email.strip(),
        "phone": (phone or "").strip(),
        "bu": (bu or "").strip() or None,
        "team": (team or "").strip() or None,
        "branch": branch,
        "employment_type": employment_type_list,
        "work_branch": (work_branch or "").strip() or None,
        "show_on_home": bool(show_on_home),
        "updated_at": datetime.utcnow()
    }
    await db.contatti.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": update_data}
    )

    # 2. Toast notification (come in links.py)
    payload_toast = create_action_notification_payload(
        'update',
        'contatto',
        name.strip(),
        str(current_user["_id"])
    )
    await broadcast_message(
        payload_toast,
        branch=branch,
        employment_type=employment_type_list,
        exclude_user_id=str(current_user["_id"])
    )

    # 3. Aggiornamento highlights (se necessario)
    # Recupera il contatto aggiornato per avere i dati corretti per home_highlights
    updated_contact_for_highlight = await db.contatti.find_one({"_id": ObjectId(contact_id)})

    if show_on_home:
        highlight_data = {
            "type": "contact",
            "object_id": contact_id, # E' gia' una stringa
            "title": updated_contact_for_highlight["name"],
            "created_at": updated_contact_for_highlight.get("created_at", datetime.utcnow()), # Mantieni created_at originale se esiste
            "branch": updated_contact_for_highlight["branch"],
            "employment_type": updated_contact_for_highlight["employment_type"],
            "email": updated_contact_for_highlight["email"],
            "phone": updated_contact_for_highlight["phone"],
            "bu": updated_contact_for_highlight["bu"],
            "team": updated_contact_for_highlight["team"],
            "work_branch": updated_contact_for_highlight["work_branch"]
        }
        await db.home_highlights.update_one(
            {"type": "contact", "object_id": contact_id},
            {"$set": highlight_data},
            upsert=True
        )
        payload_highlight_refresh = {
            "type": "refresh_home_highlights",
            "data": {"branch": branch, "employment_type": employment_type_list}
        }
        await broadcast_message(payload_highlight_refresh, branch=branch, employment_type=employment_type_list)
    else:
        # Se show_on_home è False, rimuovi da home_highlights
        delete_result = await db.home_highlights.delete_one({"type": "contact", "object_id": contact_id})
        if delete_result.deleted_count > 0: # Era in home ed è stato rimosso
            # Invia broadcast per refresh se effettivamente rimosso
            payload_highlight_refresh = {
                "type": "refresh_home_highlights",
                # Qui dovremmo idealmente usare i branch/emp_type *prima* della modifica
                # se sono cambiati, per notificare correttamente chi lo vedeva prima.
                # Per semplicità, usiamo quelli attuali come in links.py.
                "data": {"branch": branch, "employment_type": employment_type_list}
            }
            await broadcast_message(payload_highlight_refresh, branch=branch, employment_type=employment_type_list)

    # 4. Broadcast evento risorsa
    await broadcast_resource_event(
        event="update",
        item_type="contact",
        item_id=contact_id,
        user_id=str(current_user["_id"]),
        # title=name.strip(), # Opzionale, ma per coerenza con create e links.py
        # db=db # Opzionale, ma per coerenza con create e links.py
    )

    # 5. Risposta con la riga aggiornata e conferma admin
    # Recupera il contatto finale per il template (potrebbe essere ridondante se updated_contact_for_highlight è sufficiente)
    final_updated_contact = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    resp = request.app.state.templates.TemplateResponse(
        "contatti/contatti_row_partial.html", # Assumendo che questo template esista e funzioni come links_row_partial.html
        {"request": request, "contact": final_updated_contact, "current_user": current_user}
    )
    # HX-Trigger per la conferma admin (include closeModal: true)
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('update', name.strip())
    # Non serve HX-Trigger-After-Settle se closeModal è gestito nel payload di create_admin_confirmation_trigger

    return resp

@contatti_router.get("/contatti/new", response_class=HTMLResponse)
async def new_contact(request: Request, current_user: dict = Depends(require_admin)):
    db = request.app.state.db
    branches = await db.branches.distinct("name")
    if not branches:
        branches = DEFAULT_BRANCHES

    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        hire_types = DEFAULT_HIRE_TYPES

    print("branches:", branches)        # debug: lista filiali
    print("hire_types:", hire_types)    # debug: lista tipologie assunzione
    
    return request.app.state.templates.TemplateResponse(
        "contatti/contatti_new.html",
        {
            "request": request,
            "branches": branches,
            "hire_types": hire_types
        }
    )

@contatti_router.get("/contatti/new/partial", response_class=HTMLResponse)
async def new_contact_partial(request: Request, current_user: dict = Depends(require_admin)):
    db = request.app.state.db
    branches = await db.branches.distinct("name")
    if not branches:
        branches = DEFAULT_BRANCHES

    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        hire_types = DEFAULT_HIRE_TYPES

    print("branches (partial):", branches)        # debug: lista filiali
    print("hire_types (partial):", hire_types)    # debug: lista tipologie assunzione
    
    return request.app.state.templates.TemplateResponse(
        "contatti/contatto_new_partial.html",
        {
            "request": request,
            "branches": branches,
            "hire_types": hire_types
        }
    )

@contatti_router.put("/contatti/{contact_id}", status_code=200)
async def update_contact(
    request: Request,
    contact_id: str,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    bu: str = Form(None),
    team: str = Form(None),
    branch: str = Form(...),
    employment_type: str = Form(...), # Questo dovrebbe probabilmente essere una lista come in create_contact se il form lo permette
    work_branch: str = Form(None), # Aggiunto work_branch
    show_on_home: Annotated[bool, Form()] = False,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db

    # Prepara i dati da aggiornare
    update_data = {
        "name": name.strip(),
        "email": email.strip(),
        "phone": (phone or "").strip(),
        "bu": (bu or "").strip() or None,
        "team": team.strip() if team else None,
        "branch": branch, # branch di destinazione
        # employment_type dovrebbe essere gestito come lista se il form invia multipli valori o per coerenza
        "employment_type": [employment_type] if isinstance(employment_type, str) else (employment_type or []),
        "show_on_home": bool(show_on_home),
        "updated_at": datetime.utcnow(),
    }
    if work_branch: # Aggiungi work_branch solo se fornito
        update_data["work_branch"] = work_branch.strip()

    await db.contatti.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": update_data}
    )
    c = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    html = request.app.state.templates.TemplateResponse(
        "contatti/contatti_row_partial.html",
        {"request": request, "contact": c, "current_user": current_user},
        status_code=200
    )
    html.headers["HX-Trigger"] = "closeModal,refreshContattiList"
    return html

@contatti_router.delete("/contatti/{contact_id}")
async def delete_contact(
    request: Request,
    contact_id: str,
    current_user: dict = Depends(require_admin)
):
    db = request.app.state.db
    
    # 1. Recupera il contatto prima di eliminarlo
    contact = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    if not contact:
        raise HTTPException(404, "Contatto non trovato")

    # 2. Elimina il contatto
    await db.contatti.delete_one({"_id": ObjectId(contact_id)})

    # 3. Elimina le notifiche associate a questo contatto (come in links.py)
    # Questo aiuta a mantenere il conteggio dei badge accurato.
    await db.notifiche.delete_many({"id_risorsa": contact_id, "tipo": "contatto"})
    
    # Recupera i dettagli necessari prima che 'contact' non sia più disponibile
    contact_name = contact.get('name', 'Contatto sconosciuto')
    contact_branch = contact.get('branch', '*') # Default a '*' se non specificato
    contact_employment_type = contact.get('employment_type', ['*']) # Default a ['*']
    was_on_home = contact.get("show_on_home", False)

    # 4. Toast notification
    payload_toast = create_action_notification_payload(
        'delete', 
        'contatto', 
        contact_name,
        str(current_user["_id"])
    )
    await broadcast_message(
        payload_toast,
        branch=contact_branch,
        employment_type=contact_employment_type,
        exclude_user_id=str(current_user["_id"])
    )

    # 5. Elimina da home_highlights se presente
    await db.home_highlights.delete_one({
        "type": "contact", # Assicurati che type sia corretto
        "object_id": contact_id # contact_id è già una stringa
    })

    # 6. Broadcast refresh_home_highlights (se era in home)
    if was_on_home:
        payload_highlight_refresh = {
            "type": "refresh_home_highlights",
            "data": { # Dati per il broadcast mirato
                "branch": contact_branch,
                "employment_type": contact_employment_type
            }
        }
        await broadcast_message(
            payload_highlight_refresh,
            branch=contact_branch, # Filtra il broadcast per chi poteva vedere il contatto
            employment_type=contact_employment_type
        )

    # 7. Broadcast evento risorsa
    await broadcast_resource_event(
        event="delete",
        item_type="contact",
        item_id=contact_id, # E' già una stringa
        user_id=str(current_user["_id"])
        # title e db non sono strettamente necessari qui per delete come in links.py
    )

    # 8. Conferma per l'admin
    response = Response(status_code=200)
    admin_trigger = create_admin_confirmation_trigger(
        'delete',
        contact["name"]
    )
    print("[DEBUG-CONTATTI-DELETE] Payload conferma admin:", admin_trigger)
    response.headers["HX-Trigger"] = admin_trigger
    return response
