// Modulo per gestire le risorse (link, documenti, contatti, news, etc.)
export class ResourceHandler {
  constructor(config) {
    this.type = config.type; // 'link', 'document', 'contact', etc.
    this.listId = config.listId;
    this.listUrl = config.listUrl;
    this.badgeContainerId = config.badgeContainerId;
    this.setupEventListeners();
  }

  setupEventListeners() {
    // Gestione WebSocket
    document.addEventListener('ws:resource/add', (e) => {
      if (e.detail.type === this.type) {
        this.refreshList();
        this.refreshBadge();
      }
    });

    document.addEventListener('ws:resource/delete', (e) => {
      if (e.detail.type === this.type) {
        this.refreshList();
        this.refreshBadge();
      }
    });

    document.addEventListener('ws:resource/update', (e) => {
      if (e.detail.type === this.type) {
        this.refreshList();
      }
    });

    // Gestione notifiche
    document.addEventListener('notifications.refresh', () => {
      this.refreshBadge();
    });
  }

  refreshList() {
    const listElement = document.getElementById(this.listId);
    if (listElement) {
      htmx.ajax('GET', this.listUrl, {target: `#${this.listId}`, swap: 'innerHTML'});
    }
  }

  refreshBadge() {
    const badgeContainer = document.getElementById(this.badgeContainerId);
    if (badgeContainer) {
      htmx.ajax('GET', `/notifiche/count/${this.type}`, {target: `#${this.badgeContainerId}`, swap: 'innerHTML'});
    }
  }

  // Metodo per gestire l'eliminazione
  handleDelete(itemId) {
    return Swal.fire({
      title: 'Sei sicuro?',
      text: 'Questa azione non può essere annullata',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Sì, elimina',
      cancelButtonText: 'Annulla',
      reverseButtons: true
    }).then((result) => {
      if (result.isConfirmed) {
        return true;
      }
      return false;
    });
  }
} 