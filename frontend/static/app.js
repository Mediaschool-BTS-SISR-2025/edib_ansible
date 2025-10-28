// -------------------- Variables globales --------------------
let autoRefreshInterval = null;
let launchOptions = null;

document.addEventListener("DOMContentLoaded", () => {
    // -------------------- Sélecteurs principaux --------------------
    const loginForm = document.getElementById("loginForm");
    const dashboard = document.getElementById("dashboard");
    const createOptions = document.getElementById("createOptions");
    launchOptions = document.getElementById("launchOptions");
    const apiLog = document.getElementById("apiLog");
    const vmList = document.getElementById("vm-list");
    const noVmsDiv = document.getElementById("no-vms");
    
    // Boutons
    const createBtn = document.getElementById("createBtn");
    const launchBtn = document.getElementById("launchBtn");
    const backBtn = document.getElementById("backBtn");
    const logoutBtn = document.getElementById("logoutBtn");
    const confirmCreateBtn = document.getElementById("confirmCreateBtn");
    const vmNameInput = document.getElementById("vmNameInput");
    const vmUsernameInput = document.getElementById("vmUsernameInput");
    const vmPasswordInput = document.getElementById("vmPasswordInput");
    const vmPasswordConfirmInput = document.getElementById("vmPasswordConfirmInput");
    const vmRootPasswordInput = document.getElementById("vmRootPasswordInput");
    const rootPasswordHelp = document.getElementById("rootPasswordHelp");
    
    // Cartes de sélection
    const roleCards = document.querySelectorAll(".role-card");
    const osCards = document.querySelectorAll(".os-card");
    const createNote = document.getElementById("create-note");
    
    const VM_NAME_RE = /^[A-Za-z0-9._-]{1,64}$/;
    const VM_USERNAME_RE = /^[a-z][a-z0-9_-]{2,31}$/;

    let selectedRole = "serveur";
    let selectedOS = null;

    // -------------------- Fonction de log --------------------
    function logMessage(msg, type = "info") {
        if (!apiLog) return;
        const entry = document.createElement("div");
        entry.className = `log-entry ${type}`;
        entry.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        apiLog.appendChild(entry);
        apiLog.scrollTop = apiLog.scrollHeight;
    }

    // -------------------- Login --------------------
    loginForm?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = loginForm.username.value.trim();
        const password = loginForm.password.value;
        
        try {
            const res = await fetch("/api/login", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({username, password})
            });
            
            const data = await res.json();
            
            if(data.success) {
                loginForm.style.display = "none";
                dashboard.style.display = "block";
                displayVMs();
                logMessage(`Connecté en tant que ${username}`, "success");
            } else {
                alert(data.message || "Échec de la connexion");
            }
        } catch(err) {
            alert("Erreur de connexion");
            console.error(err);
        }
    });

    // -------------------- Déconnexion --------------------
    window.logout = async function() {
        try {
            const res = await fetch("/api/logout");
            const data = await res.json();
            if(data.success) {
                stopAutoRefresh();
                dashboard.style.display = "none";
                loginForm.style.display = "block";
                apiLog.innerHTML = "";
            }
        } catch(err) {
            console.error(err);
        }
    };

    // -------------------- Sélections Rôle/OS --------------------
    roleCards.forEach(card => card.addEventListener("click", () => {
        roleCards.forEach(c => { c.classList.remove("selected"); c.setAttribute("aria-pressed","false"); });
        card.classList.add("selected");
        card.setAttribute("aria-pressed","true");
        selectedRole = card.dataset.role;
        updateCreateNote();
    }));

    osCards.forEach(card => card.addEventListener("click", () => {
        osCards.forEach(c => c.classList.remove("selected"));
        card.classList.add("selected");
        selectedOS = card.dataset.os;
        updateCreateNote();
    }));

    function updateCreateNote() {
        if (!createNote) return;
        if (selectedRole && selectedOS) {
            let detail = "";
            if (selectedOS === "debian") {
                detail = selectedRole === "serveur" ? "Debian Serveur (sans GUI)" : "Debian Client (GUI)";
            } else {
                detail = selectedRole === "serveur" ? "Windows Server (GUI)" : "Windows 11 (GUI)";
            }
            createNote.textContent = `${detail} — Remplis les champs ci-dessous.`;
        } else {
            createNote.textContent = "Sélectionne d'abord Serveur/Client et un OS.";
        }
        validateForm();
    }

    // -------------------- Validation formulaire --------------------
    function validateForm() {
        const name = vmNameInput?.value.trim() || "";
        const username = vmUsernameInput?.value.trim() || "";
        const password = vmPasswordInput?.value || "";
        const passwordConfirm = vmPasswordConfirmInput?.value || "";
        const rootPwd = vmRootPasswordInput?.value || "";
        const rootValid = rootPwd.length >= 6;

        if (rootPasswordHelp) {
            if (!rootPwd) {
                rootPasswordHelp.textContent = "Mot de passe root/Administrator obligatoire";
                rootPasswordHelp.style.color = "var(--error)";
            } else if (!rootValid) {
                rootPasswordHelp.textContent = "Minimum 6 caractères";
                rootPasswordHelp.style.color = "var(--error)";
            } else {
                rootPasswordHelp.textContent = "✓ Mot de passe root/Administrator valide";
                rootPasswordHelp.style.color = "var(--success)";
            }
        }

        const nameValid = VM_NAME_RE.test(name);
        const usernameValid = VM_USERNAME_RE.test(username);
        const passwordValid = password.length >= 6;
        const passwordsMatch = password === passwordConfirm && password.length > 0;
        
        const help = document.getElementById("vmNameHelp");
        if (help) {
            if (!name) { 
                help.textContent="Nom obligatoire"; 
            } else if (!nameValid) { 
                help.textContent="Nom invalide"; 
            } else { 
                help.textContent="✓ Nom valide"; 
            }
        }
        
        const passwordHelp = document.getElementById("passwordHelp");
        if (passwordHelp) {
            if (!password) {
                passwordHelp.textContent = "Mot de passe obligatoire";
                passwordHelp.style.color = "var(--error)";
            } else if (!passwordValid) {
                passwordHelp.textContent = "Minimum 6 caractères";
                passwordHelp.style.color = "var(--error)";
            } else if (!passwordsMatch) {
                passwordHelp.textContent = "Les mots de passe ne correspondent pas";
                passwordHelp.style.color = "var(--error)";
            } else {
                passwordHelp.textContent = "✓ Mots de passe valides";
                passwordHelp.style.color = "var(--success)";
            }
        }
        
        const allValid = nameValid && usernameValid && passwordValid && passwordsMatch && rootValid && selectedRole && selectedOS;
        if (confirmCreateBtn) confirmCreateBtn.disabled = !allValid;
        return allValid;
    }

    vmNameInput?.addEventListener("input", validateForm);
    vmUsernameInput?.addEventListener("input", validateForm);
    vmPasswordInput?.addEventListener("input", validateForm);
    vmPasswordConfirmInput?.addEventListener("input", validateForm);
    vmRootPasswordInput?.addEventListener("input", validateForm);

    // -------------------- Créer VM --------------------
    // Bouton "Créer la VM"
    confirmCreateBtn?.addEventListener("click", async () => {
        if (!validateForm()) { logMessage("Formulaire invalide","error"); return; }

        const payload = { 
            vm_name: vmNameInput.value.trim(), 
            vm_type: selectedRole, 
            os: selectedOS,
            vm_username: vmUsernameInput.value.trim(),
            vm_password: vmPasswordInput.value,
            root_password: vmRootPasswordInput.value
        };

        logMessage(`Création VM ${payload.vm_name}...`, "info");
        confirmCreateBtn.disabled = true;
        showLoader("Création de la VM en cours... Cela peut prendre quelques minutes."); // ← AJOUT

        try {
            const res = await fetch("/api/create_vm", {
                method: "POST",
                headers: {"Content-Type":"application/json"},
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            logMessage(data.message, res.ok ? "success" : "error");
            if (res.ok) {
                vmNameInput.value = "";
                vmUsernameInput.value = "";
                vmPasswordInput.value = "";
                vmPasswordConfirmInput.value = "";
                vmRootPasswordInput.value = "";
                
                logMessage("Redirection vers Mes VMs...", "info");
                setTimeout(() => {
                    createOptions.style.display = "none";
                    launchOptions.style.display = "block";
                    displayVMs();
                    startAutoRefresh();
                }, 800);
            }
        } catch(err) {
            console.error(err);
            logMessage("Erreur création","error");
        } finally {
            hideLoader(); // ← AJOUT
            confirmCreateBtn.disabled = false;
            validateForm();
        }
    });

    // -------------------- Charger et afficher les VMs --------------------
    window.displayVMs = async function() {
        if (!vmList || !noVmsDiv) {
            console.error("Éléments VM list ou no-vms introuvables");
            return;
        }
        
        try {
            const res = await fetch("/api/list_vms");
            const data = await res.json();
            const vms = data.vms || [];

            if(vms.length === 0) {
                noVmsDiv.style.display = "block";
                vmList.innerHTML = "";
                return;
            } else {
                noVmsDiv.style.display = "none";
            }

            vmList.innerHTML = "";
            vms.forEach(vm => {
                const card = document.createElement("div");
                card.className = "vm-card";
                
                const isRunning = vm.state === 'running';
                const stateClass = isRunning ? 'running' : 'stopped';
                const stateText = isRunning ? 'En cours' : 'Arrêtée';
                const ownerBadge = data.is_admin ? `<span class="owner-badge">👤 ${vm.owner}</span>` : '';
                
                card.innerHTML = `
                    <div class="vm-header">
                        <h3>${vm.name}</h3>
                        ${ownerBadge}
                        <span class="vm-state ${stateClass}">${stateText}</span>
                    </div>
                    <div class="vm-actions">
                        <button class="launch-vm-btn" data-vm="${vm.name}" ${isRunning ? 'disabled' : ''}>
                            ${isRunning ? '✓ Lancée' : '▶ Lancer'}
                        </button>
                        <button class="halt-vm-btn" data-vm="${vm.name}" ${!isRunning ? 'disabled' : ''}>
                            ⏹ Arrêter
                        </button>
                        <button class="view-vm-btn" data-vm="${vm.name}" ${!isRunning ? 'disabled' : ''}>
                            🖥 GUI
                        </button>
                        <button class="delete-vm-btn" data-vm="${vm.name}" ${isRunning ? 'disabled' : ''}>
                            🗑 Supprimer
                        </button>
                    </div>
                `;
                vmList.appendChild(card);
            });
        } catch(err) {
            console.error("Erreur displayVMs:", err);
            logMessage("Erreur lors du chargement des VMs", "error");
        }
    };

    // -------------------- Actions VM --------------------
    vmList?.addEventListener("click", async (e) => {
        const btn = e.target;
        const vmName = btn.dataset?.vm;
        if(!vmName || btn.disabled) return;

        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = '⏳';

        if(btn.classList.contains("launch-vm-btn")) {
            logMessage(`Lancement de ${vmName}...`, "info");
            try {
                const res = await fetch("/api/launch_vm", {
                    method:"POST",
                    headers:{"Content-Type":"application/json"},
                    body:JSON.stringify({vm_name:vmName})
                });
                const data = await res.json();
                logMessage(data.message, "success");
                setTimeout(() => displayVMs(), 2000);
            } catch(err) {
                logMessage(`Erreur lancement ${vmName}`, "error");
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
        
        else if(btn.classList.contains("halt-vm-btn")) {
            logMessage(`Arrêt de ${vmName}...`, "info");
            try {
                const res = await fetch("/api/halt_vm", {
                    method:"POST",
                    headers:{"Content-Type":"application/json"},
                    body:JSON.stringify({vm_name:vmName})
                });
                const data = await res.json();
                logMessage(data.message, "success");
                setTimeout(() => displayVMs(), 1000);
            } catch(err) {
                logMessage(`Erreur arrêt ${vmName}`, "error");
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
        
        else if(btn.classList.contains("delete-vm-btn")) {
            if(!confirm(`⚠️ Supprimer ${vmName} ?\n\nCette action est irréversible.`)) {
                btn.disabled = false;
                btn.innerHTML = originalText;
                return;
            }
            
            logMessage(`Suppression de ${vmName}...`, "info");
            try {
                const res = await fetch("/api/delete_vm", {
                    method:"POST",
                    headers:{"Content-Type":"application/json"},
                    body:JSON.stringify({vm_name:vmName})
                });
                const data = await res.json();
                logMessage(data.message, "success");
                displayVMs();
            } catch(err) {
                logMessage(`Erreur suppression ${vmName}`, "error");
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
        
        else if(btn.classList.contains("view-vm-btn")) {
            btn.innerHTML = originalText;
            btn.disabled = false;
            viewVM(vmName);
        }
    });

    // -------------------- Navigation boutons principaux --------------------
    createBtn?.addEventListener("click", () => {
        launchOptions.style.display = "none";
        createOptions.style.display = "block"; // ← block au lieu de flex
        backBtn.style.display = "inline-block";
        stopAutoRefresh();
        logMessage("Affichage des options de création", "info");
    });

    launchBtn?.addEventListener("click", () => {
        createOptions.style.display = "none";
        launchOptions.style.display = "block"; // ← block au lieu de flex
        backBtn.style.display = "inline-block";
        displayVMs();
        startAutoRefresh();
        logMessage("Affichage des VMs", "info");
    });

    backBtn?.addEventListener("click", () => {
        createOptions.style.display = "none";
        launchOptions.style.display = "none";
        backBtn.style.display = "none";
        stopAutoRefresh();
        logMessage("Retour au menu principal", "info");
    });

    // -------------------- Fonction viewVM --------------------
    function viewVM(vmName) {
        fetch(`/api/get_vnc_url/${vmName}`)
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                window.open(data.url, '_blank', 'width=1280,height=720');
                logMessage(`Console web de ${vmName} ouverte`, "success");
            } else {
                logMessage(data.message || 'Erreur ouverture console', "error");
            }
        })
        .catch(err => {
            logMessage('Erreur: ' + err, "error");
        });
    }

    // -------------------- Initialisation --------------------
    updateCreateNote();
});

// -------------------- Auto-refresh (HORS DOMContentLoaded) --------------------
function startAutoRefresh() {
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
    
    autoRefreshInterval = setInterval(() => {
        if (launchOptions && launchOptions.style.display !== 'none') {
            window.displayVMs();
        }
    }, 5000);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// Utils loader (globaux)
function showLoader(message) {
    const overlay = document.getElementById("globalLoader");
    if (!overlay) return;
    const text = overlay.querySelector(".loader-text");
    if (text && message) text.textContent = message;
    overlay.style.display = "flex";
}
function hideLoader() {
    const overlay = document.getElementById("globalLoader");
    if (!overlay) return;
    overlay.style.display = "none";
}
