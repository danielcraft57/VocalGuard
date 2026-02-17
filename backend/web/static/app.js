const API_BASE = '/api/v1';

// Gestion des onglets
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.dataset.tab;
        
        // Désactiver tous les onglets
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        // Activer l'onglet sélectionné
        btn.classList.add('active');
        document.getElementById(`${tabName}-tab`).classList.add('active');
        
        // Charger les données de l'onglet
        loadTabData(tabName);
    });
});

// Charger les données selon l'onglet
function loadTabData(tabName) {
    switch(tabName) {
        case 'calls':
            loadCalls();
            break;
        case 'callers':
            loadCallers();
            break;
        case 'voicemails':
            loadVoicemails();
            break;
        case 'voice-test':
            // Pas besoin de charger des données pour le test vocal
            break;
    }
}

// Fonctions API
async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`Erreur HTTP: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('Erreur API:', error);
        showNotification('Erreur: ' + error.message, 'error');
        throw error;
    }
}

// Charger les appels
async function loadCalls() {
    const container = document.getElementById('calls-list');
    container.innerHTML = '<div class="loading">Chargement...</div>';
    
    try {
        const data = await apiCall('/calls?limit=50');
        const calls = data.calls || [];
        
        if (calls.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📞</div><p>Aucun appel enregistré</p></div>';
            return;
        }
        
        container.innerHTML = calls.map(call => `
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span class="status-indicator ${call.status}"></span>
                            ${call.phone_number || 'Numéro inconnu'}
                        </div>
                        <div class="card-meta">
                            ${call.caller_name || ''} • ${formatDate(call.call_time)}
                            ${call.duration ? ` • ${call.duration}s` : ''}
                        </div>
                    </div>
                    <span class="badge badge-${getStatusBadge(call.status)}">${call.status}</span>
                </div>
                ${call.transcription ? `<p style="margin-top: 10px; color: var(--text-light);">${call.transcription}</p>` : ''}
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><p>Erreur lors du chargement des appels</p></div>';
    }
}

// Charger les appelants
async function loadCallers() {
    const container = document.getElementById('callers-list');
    container.innerHTML = '<div class="loading">Chargement...</div>';
    
    try {
        const callers = await apiCall('/callers?limit=100');
        
        if (callers.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">👤</div><p>Aucun appelant enregistré</p></div>';
            return;
        }
        
        container.innerHTML = callers.map(caller => `
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">${caller.phone_number}</div>
                        <div class="card-meta">
                            ${caller.name || 'Sans nom'} • Ajouté le ${formatDate(caller.created_at)}
                        </div>
                    </div>
                    <div>
                        ${caller.is_whitelisted ? '<span class="badge badge-success">Liste blanche</span>' : ''}
                        ${caller.is_blocked ? '<span class="badge badge-danger">Bloqué</span>' : ''}
                    </div>
                </div>
                ${caller.notes ? `<p style="margin-top: 10px; color: var(--text-light);">${caller.notes}</p>` : ''}
                <div class="card-actions">
                    <button class="btn btn-sm btn-secondary" onclick="editCaller(${caller.id})">Modifier</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteCaller(${caller.id})">Supprimer</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><p>Erreur lors du chargement des appelants</p></div>';
    }
}

// Charger les messages vocaux
async function loadVoicemails() {
    const container = document.getElementById('voicemails-list');
    container.innerHTML = '<div class="loading">Chargement...</div>';
    
    try {
        const voicemails = await apiCall('/voicemails?limit=50');
        
        if (voicemails.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📧</div><p>Aucun message vocal</p></div>';
            return;
        }
        
        container.innerHTML = voicemails.map(vm => `
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">${vm.phone_number || 'Numéro inconnu'}</div>
                        <div class="card-meta">
                            ${vm.caller_name || ''} • ${formatDate(vm.created_at)}
                            ${vm.duration ? ` • ${vm.duration}s` : ''}
                        </div>
                    </div>
                    ${vm.is_read ? '' : '<span class="badge badge-info">Non lu</span>'}
                </div>
                ${vm.transcription ? `<p style="margin-top: 10px; color: var(--text-light);">${vm.transcription}</p>` : ''}
                ${vm.audio_file ? `<audio controls style="margin-top: 15px; width: 100%;"><source src="/api/v1/voicemails/${vm.id}/audio" type="audio/wav"></audio>` : ''}
                <div class="card-actions">
                    <button class="btn btn-sm btn-secondary" onclick="deleteVoicemail(${vm.id})">Supprimer</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><p>Erreur lors du chargement des messages vocaux</p></div>';
    }
}

// Ajouter un appelant
async function addCaller(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    const data = {
        phone_number: formData.get('phone_number'),
        name: formData.get('name') || null,
        is_whitelisted: formData.has('is_whitelisted'),
        is_blocked: formData.has('is_blocked')
    };
    
    try {
        await apiCall('/callers', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        showNotification('Appelant ajouté avec succès', 'success');
        hideAddCallerForm();
        loadCallers();
        event.target.reset();
    } catch (error) {
        // Erreur déjà gérée dans apiCall
    }
}

// Supprimer un appelant
async function deleteCaller(id) {
    if (!confirm('Êtes-vous sûr de vouloir supprimer cet appelant ?')) {
        return;
    }
    
    try {
        await apiCall(`/callers/${id}`, { method: 'DELETE' });
        showNotification('Appelant supprimé', 'success');
        loadCallers();
    } catch (error) {
        // Erreur déjà gérée dans apiCall
    }
}

// Supprimer un message vocal
async function deleteVoicemail(id) {
    if (!confirm('Êtes-vous sûr de vouloir supprimer ce message vocal ?')) {
        return;
    }
    
    try {
        await apiCall(`/voicemails/${id}`, { method: 'DELETE' });
        showNotification('Message vocal supprimé', 'success');
        loadVoicemails();
    } catch (error) {
        // Erreur déjà gérée dans apiCall
    }
}

// Recherche OSINT
async function searchOSINT(event) {
    event.preventDefault();
    const phone = document.getElementById('osint-phone').value.trim();
    const callerName = document.getElementById('osint-caller-name').value.trim();
    const container = document.getElementById('osint-results');
    
    if (!phone) {
        container.innerHTML = '<div class="empty-state"><p>Veuillez entrer un numéro de téléphone</p></div>';
        return;
    }
    
    container.innerHTML = '<div class="loading">Recherche en cours... Cela peut prendre quelques secondes...</div>';
    
    try {
        // Construire l'URL avec le nom de l'appelant si fourni
        let url = `/osint/phone/${encodeURIComponent(phone)}`;
        if (callerName) {
            url += `?caller_name=${encodeURIComponent(callerName)}`;
        }
        
        const data = await apiCall(url);
        
        if (!data || Object.keys(data).length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Aucune information trouvée</p></div>';
            return;
        }
        
        // Construire l'affichage détaillé
        let html = `
            <div class="card" style="margin-bottom: 20px;">
                <div class="card-header">
                    <div class="card-title">Résultats OSINT pour ${phone}</div>
                </div>
                <div style="margin-top: 15px;">
        `;
        
        // Section: Informations générales
        html += `<div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color);">`;
        html += `<h3 style="margin-bottom: 10px; color: var(--primary);">Informations générales</h3>`;
        
        if (data.phone_number) {
            html += `<p><strong>Numéro analysé:</strong> ${data.phone_number}</p>`;
        }
        if (data.full_name || data.name) {
            const name = data.full_name || data.name;
            html += `<p><strong>Nom complet:</strong> ${name}</p>`;
            if (data.first_name) {
                html += `<p><strong>Prénom:</strong> ${data.first_name}</p>`;
            }
            if (data.last_name) {
                html += `<p><strong>Nom:</strong> ${data.last_name}</p>`;
            }
        } else if (data.name) {
            html += `<p><strong>Nom:</strong> ${data.name}</p>`;
        }
        if (data.address || data.company_address) {
            const address = data.address || data.company_address;
            html += `<p><strong>Adresse:</strong> ${address}</p>`;
        }
        if (data.postal_code) {
            html += `<p><strong>Code postal:</strong> ${data.postal_code}</p>`;
        }
        if (data.department) {
            html += `<p><strong>Département:</strong> ${data.department}</p>`;
        }
        if (data.country) {
            html += `<p><strong>Pays:</strong> ${data.country}</p>`;
        }
        if (data.operator || data.carrier) {
            const operator = data.operator || data.carrier;
            const operatorDesc = data.operator_description ? ` <span style="color: var(--text-light); font-size: 0.9em;">(${data.operator_description})</span>` : '';
            html += `<p><strong>Opérateur:</strong> ${operator}${operatorDesc}</p>`;
        }
        if (data.region) {
            html += `<p><strong>Région:</strong> ${data.region}</p>`;
        }
        if (data.city) {
            html += `<p><strong>Ville:</strong> ${data.city}</p>`;
        }
        if (data.line_type) {
            const lineTypeFr = data.line_type === 'mobile' ? 'Mobile' : data.line_type === 'landline' ? 'Fixe' : data.line_type === 'special' ? 'Spécial' : data.line_type;
            html += `<p><strong>Type de ligne:</strong> ${lineTypeFr}</p>`;
        }
        if (data.location) {
            html += `<p><strong>Localisation:</strong> ${data.location}</p>`;
        }
        
        // Informations entreprise
        if (data.is_company || data.company_name) {
            html += `<div style="margin-top: 15px; padding: 10px; background: #f0f9ff; border-left: 4px solid var(--primary); border-radius: 4px;">`;
            html += `<p style="margin: 0; font-weight: bold; color: var(--primary);">🏢 ENTREPRISE DÉTECTÉE</p>`;
            if (data.company_name) {
                html += `<p style="margin-top: 5px;"><strong>Nom de l'entreprise:</strong> ${data.company_name}</p>`;
            }
            if (data.company_siret) {
                html += `<p><strong>SIRET:</strong> ${data.company_siret}</p>`;
            }
            if (data.company_siren) {
                html += `<p><strong>SIREN:</strong> ${data.company_siren}</p>`;
            }
            if (data.company_address) {
                html += `<p><strong>Adresse entreprise:</strong> ${data.company_address}</p>`;
            }
            if (data.company_activity) {
                html += `<p><strong>Activité:</strong> ${data.company_activity}</p>`;
            }
            html += `</div>`;
        }
        
        html += `</div>`;
        
        // Section: Détection commerciale
        if (data.is_commercial !== undefined || data.is_telemarketer !== undefined) {
            html += `<div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color);">`;
            html += `<h3 style="margin-bottom: 10px; color: var(--primary);">Détection commerciale</h3>`;
            
            if (data.is_commercial !== undefined) {
                html += `<p><strong>Numéro commercial:</strong> ${data.is_commercial ? '<span class="badge badge-warning">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>`;
            }
            if (data.is_telemarketer !== undefined) {
                html += `<p><strong>Télémarketeur:</strong> ${data.is_telemarketer ? '<span class="badge badge-danger">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>`;
            }
            html += `</div>`;
        }
        
        // Section: Réputation et sécurité
        html += `<div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color);">`;
        html += `<h3 style="margin-bottom: 10px; color: var(--primary);">Réputation et sécurité</h3>`;
        
        if (data.reputation) {
            const repClass = data.reputation === 'high' ? 'success' : data.reputation === 'low' ? 'danger' : 'warning';
            const repText = data.reputation === 'high' ? 'Élevée' : data.reputation === 'low' ? 'Faible' : 'Moyenne';
            html += `<p><strong>Réputation:</strong> <span class="badge badge-${repClass}">${repText}</span></p>`;
        }
        if (data.is_spam !== undefined) {
            html += `<p><strong>Spam:</strong> ${data.is_spam ? '<span class="badge badge-danger">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>`;
        }
        if (data.is_scam !== undefined) {
            html += `<p><strong>Scam:</strong> ${data.is_scam ? '<span class="badge badge-danger">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>`;
        }
        if (data.valid !== undefined) {
            html += `<p><strong>Numéro valide:</strong> ${data.valid ? '<span class="badge badge-success">Oui</span>' : '<span class="badge badge-danger">Non</span>'}</p>`;
        }
        html += `</div>`;
        
        // Section: Sources et confiance
        html += `<div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color);">`;
        html += `<h3 style="margin-bottom: 10px; color: var(--primary);">Sources et confiance</h3>`;
        
        if (data.sources && data.sources.length > 0) {
            const sourceBadges = data.sources.map(s => `<span class="badge badge-info">${s}</span>`).join(' ');
            html += `<p><strong>Sources utilisées:</strong> ${sourceBadges}</p>`;
        }
        if (data.confidence !== undefined) {
            const confidencePercent = (data.confidence * 100).toFixed(0);
            const confClass = data.confidence > 0.7 ? 'success' : data.confidence > 0.4 ? 'warning' : 'danger';
            html += `<p><strong>Niveau de confiance:</strong> <span class="badge badge-${confClass}">${confidencePercent}%</span></p>`;
        }
        html += `</div>`;
        
        // Section: Médias sociaux (si disponible)
        if (data.social_media && Object.keys(data.social_media).length > 0) {
            html += `<div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color);">`;
            html += `<h3 style="margin-bottom: 10px; color: var(--primary);">Médias sociaux</h3>`;
            for (const [platform, url] of Object.entries(data.social_media)) {
                html += `<p><strong>${platform}:</strong> <a href="${url}" target="_blank">${url}</a></p>`;
            }
            html += `</div>`;
        }
        
        // Section: Recommandation
        if (data.recommendation) {
            html += `<div style="margin-top: 20px; padding: 15px; background: var(--bg-secondary); border-radius: 5px;">`;
            html += `<h3 style="margin-bottom: 10px; color: var(--primary);">Recommandation</h3>`;
            const recClass = data.recommendation === 'block' ? 'danger' : data.recommendation === 'allow' ? 'success' : 'warning';
            const recText = data.recommendation === 'block' ? 'Bloquer' : data.recommendation === 'allow' ? 'Autoriser' : 'À examiner';
            html += `<p><strong>Action recommandée:</strong> <span class="badge badge-${recClass}" style="font-size: 14px; padding: 8px 12px;">${recText}</span></p>`;
            html += `</div>`;
        }
        
        html += `
                </div>
            </div>
        `;
        
        // Ajouter un bouton pour vérifier la réputation séparément
        html += `
            <div class="card" style="margin-top: 20px;">
                <div class="card-header">
                    <div class="card-title">Actions supplémentaires</div>
                </div>
                <div style="margin-top: 15px;">
                    <button class="btn btn-secondary" onclick="checkReputation('${phone}', '${callerName || ''}')">Vérifier la réputation détaillée</button>
                    <button class="btn btn-secondary" onclick="checkCommercial('${phone}', '${callerName || ''}')">Détection commerciale uniquement</button>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    } catch (error) {
        console.error('Erreur OSINT:', error);
        container.innerHTML = `<div class="empty-state"><p>Erreur lors de la recherche OSINT: ${error.message || 'Erreur inconnue'}</p></div>`;
    }
}

// Vérifier la réputation détaillée
async function checkReputation(phone, callerName = '') {
    const container = document.getElementById('osint-results');
    container.innerHTML = '<div class="loading">Vérification de la réputation...</div>';
    
    try {
        let url = `/osint/reputation/${encodeURIComponent(phone)}`;
        if (callerName) {
            url += `?caller_name=${encodeURIComponent(callerName)}`;
        }
        
        const data = await apiCall(url);
        
        let html = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Réputation détaillée pour ${phone}</div>
                </div>
                <div style="margin-top: 15px;">
                    <p><strong>Réputation:</strong> <span class="badge badge-${data.reputation === 'high' ? 'success' : data.reputation === 'low' ? 'danger' : 'warning'}">${data.reputation}</span></p>
                    <p><strong>Spam:</strong> ${data.is_spam ? '<span class="badge badge-danger">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>
                    <p><strong>Scam:</strong> ${data.is_scam ? '<span class="badge badge-danger">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>
                    ${data.is_commercial !== undefined ? `<p><strong>Commercial:</strong> ${data.is_commercial ? '<span class="badge badge-warning">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>` : ''}
                    ${data.is_telemarketer !== undefined ? `<p><strong>Télémarketeur:</strong> ${data.is_telemarketer ? '<span class="badge badge-danger">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>` : ''}
                    <p><strong>Confiance:</strong> ${(data.confidence * 100).toFixed(0)}%</p>
                    <p><strong>Sources:</strong> ${data.sources ? data.sources.join(', ') : 'Aucune'}</p>
                    <p><strong>Recommandation:</strong> <span class="badge badge-${data.recommendation === 'block' ? 'danger' : data.recommendation === 'allow' ? 'success' : 'warning'}">${data.recommendation === 'block' ? 'Bloquer' : data.recommendation === 'allow' ? 'Autoriser' : 'À examiner'}</span></p>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Erreur: ${error.message || 'Erreur inconnue'}</p></div>`;
    }
}

// Vérifier uniquement la détection commerciale
async function checkCommercial(phone, callerName = '') {
    const container = document.getElementById('osint-results');
    container.innerHTML = '<div class="loading">Détection commerciale...</div>';
    
    try {
        let url = `/osint/commercial/${encodeURIComponent(phone)}`;
        if (callerName) {
            url += `?caller_name=${encodeURIComponent(callerName)}`;
        }
        
        const data = await apiCall(url);
        
        let html = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Détection commerciale pour ${phone}</div>
                </div>
                <div style="margin-top: 15px;">
                    <p><strong>Numéro commercial:</strong> ${data.is_commercial ? '<span class="badge badge-warning">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>
                    <p><strong>Télémarketeur:</strong> ${data.is_telemarketer ? '<span class="badge badge-danger">Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>
                    ${data.detection_type ? `<p><strong>Type de détection:</strong> ${data.detection_type}</p>` : ''}
                    ${data.pattern_matched ? `<p><strong>Pattern détecté:</strong> <code>${data.pattern_matched}</code></p>` : ''}
                    ${data.description ? `<p><strong>Description:</strong> ${data.description}</p>` : ''}
                    <p><strong>Confiance:</strong> ${(data.confidence * 100).toFixed(0)}%</p>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Erreur: ${error.message || 'Erreur inconnue'}</p></div>`;
    }
}

// Fonctions utilitaires
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('fr-FR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function getStatusBadge(status) {
    const badges = {
        'ringing': 'warning',
        'answered': 'info',
        'blocked': 'danger',
        'completed': 'success',
        'missed': 'secondary'
    };
    return badges[status] || 'info';
}

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type} show`;
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

function showAddCallerForm() {
    document.getElementById('add-caller-form').style.display = 'block';
}

function hideAddCallerForm() {
    document.getElementById('add-caller-form').style.display = 'none';
}

function refreshCalls() {
    loadCalls();
}

function refreshVoicemails() {
    loadVoicemails();
}

function editCaller(id) {
    showNotification('Fonctionnalité à venir', 'info');
}

// Test de synthèse vocale
async function testSynthesis(event) {
    event.preventDefault();
    const text = document.getElementById('synthesis-text').value;
    const container = document.getElementById('synthesis-result');
    
    container.innerHTML = '<div class="loading">Génération de l\'audio...</div>';
    
    try {
        const formData = new FormData();
        formData.append('text', text);
        
        const response = await fetch(`${API_BASE}/voice/test/synthesis`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`Erreur HTTP: ${response.status}`);
        }
        
        // Récupérer le blob audio
        const blob = await response.blob();
        const audioUrl = URL.createObjectURL(blob);
        
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Audio généré</div>
                </div>
                <audio controls style="width: 100%; margin-top: 15px;">
                    <source src="${audioUrl}" type="${response.headers.get('content-type')}">
                    Votre navigateur ne supporte pas la lecture audio.
                </audio>
                <p style="margin-top: 10px; color: var(--text-light);">
                    Texte: "${text}"
                </p>
            </div>
        `;
        
        showNotification('Audio généré avec succès', 'success');
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Erreur: ${error.message}</p></div>`;
        showNotification('Erreur lors de la génération de l\'audio', 'error');
    }
}

// Test de reconnaissance vocale
async function testRecognition(event) {
    event.preventDefault();
    const fileInput = document.getElementById('recognition-file');
    const file = fileInput.files[0];
    const container = document.getElementById('recognition-result');
    
    if (!file) {
        showNotification('Veuillez sélectionner un fichier audio', 'error');
        return;
    }
    
    container.innerHTML = '<div class="loading">Transcription en cours... (cela peut prendre quelques secondes)</div>';
    
    try {
        const formData = new FormData();
        formData.append('audio_file', file);
        
        const response = await fetch(`${API_BASE}/voice/test/recognition`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `Erreur HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Transcription</div>
                </div>
                <div style="margin-top: 15px;">
                    <p><strong>Texte transcrit:</strong></p>
                    <p style="padding: 15px; background: var(--bg-color); border-radius: 6px; margin-top: 10px;">
                        ${data.transcription || '<em>Aucune transcription disponible</em>'}
                    </p>
                    <p style="margin-top: 15px; color: var(--text-light); font-size: 0.9rem;">
                        Fichier: ${data.original_filename} (${(data.audio_size / 1024).toFixed(2)} KB)
                    </p>
                </div>
            </div>
        `;
        
        showNotification('Transcription terminée', 'success');
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Erreur: ${error.message}</p></div>`;
        showNotification('Erreur lors de la transcription', 'error');
    }
}

// Test de conversation
async function testConversation(event) {
    event.preventDefault();
    const fileInput = document.getElementById('conversation-file');
    const file = fileInput.files[0];
    const container = document.getElementById('conversation-result');
    
    if (!file) {
        showNotification('Veuillez sélectionner un fichier audio', 'error');
        return;
    }
    
    container.innerHTML = '<div class="loading">Traitement en cours... Transcription, génération de réponse et synthèse...</div>';
    
    try {
        const formData = new FormData();
        formData.append('audio_file', file);
        
        const response = await fetch(`${API_BASE}/voice/test/conversation`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `Erreur HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        
        let audioHtml = '';
        if (data.response_audio_url) {
            const audioPath = data.response_audio_url.startsWith('/') 
                ? data.response_audio_url 
                : `${API_BASE}/voice/test/conversation/audio/${data.response_audio_url.split('/').pop()}`;
            audioHtml = `
                <audio controls style="width: 100%; margin-top: 15px;">
                    <source src="${audioPath}" type="audio/wav">
                    Votre navigateur ne supporte pas la lecture audio.
                </audio>
            `;
        }
        
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Résultat de la conversation</div>
                </div>
                <div style="margin-top: 15px;">
                    <p><strong>Vous avez dit:</strong></p>
                    <p style="padding: 10px; background: var(--bg-color); border-radius: 6px; margin-top: 5px;">
                        ${data.user_text || '<em>Aucune transcription</em>'}
                    </p>
                    <p style="margin-top: 15px;"><strong>Réponse de VocalGuard:</strong></p>
                    <p style="padding: 10px; background: var(--bg-color); border-radius: 6px; margin-top: 5px;">
                        ${data.response_text || '<em>Aucune réponse</em>'}
                    </p>
                    ${audioHtml}
                </div>
            </div>
        `;
        
        showNotification('Conversation traitée avec succès', 'success');
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Erreur: ${error.message}</p></div>`;
        showNotification('Erreur lors du traitement de la conversation', 'error');
    }
}

// Charger les données au démarrage
document.addEventListener('DOMContentLoaded', () => {
    loadTabData('calls');
});

