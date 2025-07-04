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

    # Gestione employment_type: assicurarsi che sia una lista.
    # La richiesta originale specificava che il form inviava una stringa singola per employment_type.
    # links.py ha una logica specifica per '*', qui gestiamo la conversione a lista in modo più generale.
    if isinstance(employment_type, str):
        # Se è una stringa vuota o solo spazi, considerala come nessun tipo specificato -> lista vuota
        employment_type_list = [etype.strip() for etype in employment_type.split(',') if etype.strip()] if employment_type and employment_type.strip() else []
    elif isinstance(employment_type, list):
        employment_type_list = [str(et).strip() for et in employment_type if str(et).strip()] # Pulisce la lista esistente
    else:
        employment_type_list = []

    # 1. Operazione DB
    contact_data = {
        "name": name.strip(),
        "email": email.strip(),
        "phone": (phone or "").strip(),
        "bu": (bu or "").strip() or None,
        "team": (team or "").strip() or None,
        "branch": branch, # branch è un campo obbligatorio, già stringa
        "employment_type": employment_type_list,
        "work_branch": (work_branch or "").strip(), # work_branch è opzionale
        "show_on_home": bool(show_on_home),
        "created_at": datetime.utcnow()
    }
    result = await db.contatti.insert_one(contact_data)
    new_id = str(result.inserted_id)

    # 2. Notifica nel DB per badge (come in links.py)
    # L'import di crea_notifica è già a livello di modulo in contatti.py
    await crea_notifica(
        request=request,
        tipo="contatto", # tipo corretto per contatti
        titolo=f"Nuovo contatto aggiunto: {name.strip()}", # Titolo specifico come in links
        branch=branch, # branch è già strip()pato o defaultato
        id_risorsa=new_id,
        employment_type=employment_type_list, # Lista processata
        source_user_id=str(current_user["_id"]) # Aggiunto source_user_id
    )

    # 3. Toast notification (come in links.py)
    payload_toast = create_action_notification_payload(
        action_type='create', # 'create'
        resource_type='contatto', # 'contatto'
        resource_name=name.strip(),
        user_id=str(current_user["_id"])
    )
    await broadcast_message(
        payload_toast,
        branch=branch,
        employment_type=employment_type_list,
        exclude_user_id=str(current_user["_id"]) # Esclude l'utente che ha creato
    )

    # 4. Broadcast evento risorsa (come in links.py)
    await broadcast_resource_event(
        event="add",
        item_type="contact", # 'contact' per coerenza con JS e altri eventi
        item_id=new_id,
        user_id=str(current_user["_id"]),
        title=name.strip(), # title del contatto
        db=db # Passa l'istanza db
    )

    # 5. Aggiornamento highlights (se necessario, come in links.py)
    if show_on_home:
        highlight_data = {
            "type": "contact", # tipo corretto
            "object_id": new_id,
            "title": name.strip(),
            "url": None, # I contatti non hanno URL come i link, ma il modello highlight potrebbe aspettarselo
            "branch": branch,
            "employment_type": employment_type_list,
            "created_at": contact_data["created_at"], # Usa la stessa datetime di creazione
            # Campi specifici del contatto per l'highlight
            "email": contact_data["email"],
            "phone": contact_data["phone"],
            "bu": contact_data["bu"],
            "team": contact_data["team"],
            "work_branch": contact_data["work_branch"]
        }
        # links.py usa insert_one, che è più sicuro se l'oggetto non dovrebbe esistere.
        # Se un upsert è preferito (come era prima), assicurarsi che sia intenzionale.
        # Per allineamento stretto, usiamo insert_one.
        await db.home_highlights.insert_one(highlight_data)

        payload_highlight_refresh = { # Nome variabile cambiato per chiarezza
            "type": "refresh_home_highlights",
            "data": { # Dati per il broadcast mirato
                "branch": branch,
                "employment_type": employment_type_list
            }
        }
        await broadcast_message(
            payload_highlight_refresh,
            branch=branch, # Filtra il broadcast per chi potrebbe vedere questo highlight
            employment_type=employment_type_list
        )

    # 6. Risposta con conferma admin (come in links.py)
    resp = Response(status_code=200)
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger(
        action_type='create',
        resource_name=name.strip()
    )
    # HX-Trigger-After-Settle per closeModal e redirect
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirectToContatti": "/contatti" # Redirect specifico per contatti
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

    # Gestione employment_type: il Form lo riceve come list[str] se il form invia campi multipli con lo stesso nome
    # o se il campo è type-hinted come list[str]. Se arriva come stringa singola (es. da un input text),
    # necessita di essere splittato e pulito. Dato che il Form è `employment_type: list[str] = Form(...)`,
    # FastAPI dovrebbe già gestirlo come lista di stringhe. Applichiamo comunque una pulizia.
    if isinstance(employment_type, list):
        employment_type_list = [str(et).strip() for et in employment_type if str(et).strip()]
    elif isinstance(employment_type, str): # Fallback se per qualche motivo arriva come stringa
        employment_type_list = [etype.strip() for etype in employment_type.split(',') if etype.strip()] if employment_type and employment_type.strip() else []
    else:
        employment_type_list = []


    # 1. Operazione DB: Aggiorna il contatto
    update_data = {
        "name": name.strip(),
        "email": email.strip(),
        "phone": (phone or "").strip(),
        "bu": (bu or "").strip() or None,
        "team": (team or "").strip() or None,
        "branch": branch, # Già stringa
        "employment_type": employment_type_list, # Lista processata
        "work_branch": (work_branch or "").strip() or None,
        "show_on_home": bool(show_on_home),
        "updated_at": datetime.utcnow() # Aggiungi updated_at
    }
    await db.contatti.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": update_data}
    )

    # 2. Toast notification (come in links.py)
    payload_toast = create_action_notification_payload(
        action_type='update', # 'update'
        resource_type='contatto', # 'contatto'
        resource_name=name.strip(),
        user_id=str(current_user["_id"])
    )
    await broadcast_message(
        payload_toast,
        branch=branch,
        employment_type=employment_type_list, # Usa la lista processata
        exclude_user_id=str(current_user["_id"])
    )

    # 3. Aggiornamento highlights (se necessario, come in links.py)
    # Recupera il contatto aggiornato per avere i dati corretti per home_highlights
    # E' importante farlo *dopo* l'update_one per avere i dati più recenti.
    updated_contact_for_highlight = await db.contatti.find_one({"_id": ObjectId(contact_id)})

    if show_on_home:
        highlight_data_for_upsert = { # Nome variabile più specifico
            "type": "contact",
            "object_id": contact_id,
            "title": updated_contact_for_highlight["name"],
            "url": None, # Coerenza con create_contact
            "branch": updated_contact_for_highlight["branch"],
            "employment_type": updated_contact_for_highlight["employment_type"],
            "created_at": updated_contact_for_highlight.get("created_at", datetime.utcnow()), # Mantieni created_at originale
            # Campi specifici del contatto
            "email": updated_contact_for_highlight["email"],
            "phone": updated_contact_for_highlight["phone"],
            "bu": updated_contact_for_highlight["bu"],
            "team": updated_contact_for_highlight["team"],
            "work_branch": updated_contact_for_highlight["work_branch"]
        }
        await db.home_highlights.update_one(
            {"type": "contact", "object_id": contact_id},
            {"$set": highlight_data_for_upsert},
            upsert=True # Come in links.py per l'update
        )
        payload_highlight_refresh = {
            "type": "refresh_home_highlights",
            "data": {"branch": branch, "employment_type": employment_type_list} # Usa i valori attuali
        }
        await broadcast_message(payload_highlight_refresh, branch=branch, employment_type=employment_type_list)
    else:
        # Se show_on_home è False, rimuovi da home_highlights
        delete_result = await db.home_highlights.delete_one({"type": "contact", "object_id": contact_id})
        if delete_result.deleted_count > 0: # Era in home ed è stato rimosso
            payload_highlight_refresh = {
                "type": "refresh_home_highlights",
                "data": {"branch": branch, "employment_type": employment_type_list} # Usa i valori attuali
            }
            await broadcast_message(payload_highlight_refresh, branch=branch, employment_type=employment_type_list)

    # 4. Broadcast evento risorsa (come in links.py, senza title e db per l'update)
    await broadcast_resource_event(
        event="update",
        item_type="contact", # 'contact'
        item_id=contact_id,
        user_id=str(current_user["_id"])
    )

    # 5. Risposta con la riga aggiornata e conferma admin (come in links.py)
    # updated_contact_for_highlight contiene già il contatto aggiornato.
    resp = request.app.state.templates.TemplateResponse(
        "contatti/contatti_row_partial.html",
        {"request": request, "contact": updated_contact_for_highlight, "current_user": current_user}
    )
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger(
        action_type='update', # 'update'
        resource_name=name.strip() # Nome della risorsa per il messaggio di conferma
    )
    # create_admin_confirmation_trigger dovrebbe già includere closeModal:true nel suo payload JSON.
    # Non è necessario HX-Trigger-After-Settle se la chiusura è gestita globalmente dal JS che ascolta l'evento di conferma.
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

    db = request.app.state.db

    # 1. Recupera il contatto prima di eliminarlo per ottenere i dettagli per i broadcast
    contact_to_delete = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    if not contact_to_delete:
        raise HTTPException(404, "Contatto non trovato")

    # Estrai i dettagli necessari PRIMA dell'eliminazione
    contact_name = contact_to_delete.get('name', 'Contatto sconosciuto')
    # Assicurati che branch e employment_type abbiano valori di fallback sensati se mancanti
    contact_branch = contact_to_delete.get('branch', '*')
    # employment_type dovrebbe essere una lista; se non lo è o manca, usa ['*'] come fallback per il broadcast
    raw_employment_type = contact_to_delete.get('employment_type', ['*'])
    if isinstance(raw_employment_type, list):
        contact_employment_type_list = raw_employment_type
    elif isinstance(raw_employment_type, str): # Fallback nel caso sia stringa nel DB per errore
        contact_employment_type_list = [et.strip() for et in raw_employment_type.split(',') if et.strip()] if raw_employment_type.strip() else ['*']
    else:
        contact_employment_type_list = ['*'] # Default se tipo inatteso

    was_on_home = contact_to_delete.get("show_on_home", False)

    # 2. Elimina il contatto dal DB principale
    await db.contatti.delete_one({"_id": ObjectId(contact_id)})

    # 3. Elimina le notifiche associate (come in links.py)
    await db.notifiche.delete_many({"id_risorsa": contact_id, "tipo": "contatto"})

    # 4. Toast notification (come in links.py)
    payload_toast = create_action_notification_payload(
        action_type='delete',
        resource_type='contatto',
        resource_name=contact_name,
        user_id=str(current_user["_id"])
    )
    await broadcast_message(
        payload_toast,
        branch=contact_branch, # Usa i dettagli del contatto recuperato
        employment_type=contact_employment_type_list, # Usa la lista processata
        exclude_user_id=str(current_user["_id"])
    )

    # 5. Elimina da home_highlights (come in links.py)
    # L'operazione delete_one non fallisce se il documento non esiste, quindi è sicuro.
    await db.home_highlights.delete_one({
        "type": "contact",
        "object_id": contact_id
    })

    # 6. Broadcast refresh_home_highlights (se era in home, come in links.py)
    if was_on_home:
        payload_highlight_refresh = {
            "type": "refresh_home_highlights",
            "data": { # Dati per il broadcast mirato
                "branch": contact_branch, # Usa i dettagli del contatto recuperato
                "employment_type": contact_employment_type_list # Usa la lista processata
            }
        }
        await broadcast_message(
            payload_highlight_refresh,
            branch=contact_branch,
            employment_type=contact_employment_type_list
        )

    # 7. Broadcast evento risorsa (come in links.py)
    await broadcast_resource_event(
        event="delete",
        item_type="contact", # 'contact'
        item_id=contact_id,
        user_id=str(current_user["_id"])
    )

    # 8. Conferma per l'admin (come in links.py)
    response = Response(status_code=200)
    admin_trigger = create_admin_confirmation_trigger(
        'delete',
        contact["name"]
    )
    print("[DEBUG-CONTATTI-DELETE] Payload conferma admin:", admin_trigger)
    response.headers["HX-Trigger"] = admin_trigger
    return response
