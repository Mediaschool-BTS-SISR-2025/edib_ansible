# VM_Manager

VM_Manager est une interface web pour gérer des machines virtuelles étudiantes (création via Vagrant/libvirt, gestion via libvirt/virsh et accès via noVNC).

## 🚀 Déploiement sur le serveur iris.a3n.fr

Le projet est déployé sur `vm-manager.iris.a3n.fr` via **Docker Compose** et **Traefik**.

### Accès
- **Application** : http://vm-manager.iris.a3n.fr

### Architecture de déploiement

```
┌─────────────────────────────────────┐
│   Traefik (reverse proxy)           │
│         admin_proxy network         │
└────────────┬────────────────────────┘
             │ HTTP
             ▼
       ┌─────────────┐
       │  Frontend   │
       │   (nginx)   │  /api/* ──────┐
       │   Port 80   │               │
       └─────────────┘               │ proxy_pass
                                     ▼
                            ┌─────────────────┐
                            │     Backend     │
                            │ (Flask/Gunicorn)│
                            │    Port 5000    │
                            └─────────────────┘
```

**Communication** :
- Traefik route `vm-manager.iris.a3n.fr` vers le conteneur nginx (frontend)
- nginx sert les fichiers statiques (HTML/CSS/JS)
- nginx proxifie `/api/*` vers le backend Flask (communication interne Docker)
- Le backend n'est pas exposé publiquement

## 📁 Structure du projet

```
├── backend/              # Backend Flask
│   ├── main.py          # Application principale
│   ├── config.py        # Configuration
│   ├── requirements.txt # Dépendances Python
│   └── Dockerfile       # Image Docker backend
├── frontend/            # Frontend statique
│   ├── index.html       # Page principale
│   ├── static/          # CSS & JS
│   └── Dockerfile       # Image Docker frontend
├── ansible/             # Playbooks Ansible (documentation)
│   ├── deploy.yml       # Playbook de déploiement
│   ├── inventory.ini    # Inventaire des serveurs
│   └── templates/       # Templates systemd
├── noVNC/              # Client noVNC pour consoles VNC
├── student_vms/        # VMs étudiantes (créées automatiquement)
├── docker-compose.traefik.yml  # Configuration Docker Compose
├── .env                # Variables d'environnement
└── README.md           # Ce fichier
```

## 🐳 Déploiement Docker Compose (Production)

### Sur le serveur

Le projet est déployé dans `/home/iris/sisr/vm_manager/`.

#### Démarrer les conteneurs

```bash
cd /home/iris/sisr/vm_manager
docker-compose -f docker-compose.traefik.yml up -d --build
```

#### Arrêter les conteneurs

```bash
docker-compose -f docker-compose.traefik.yml down
```

#### Voir les logs

```bash
docker-compose -f docker-compose.traefik.yml logs -f
# ou pour un service spécifique
docker logs vm_manager_backend -f
docker logs vm_manager_frontend -f
```

#### Redéployer après modification

```bash
cd /home/iris/sisr/vm_manager
git pull
docker-compose -f docker-compose.traefik.yml up -d --build
```

#### Vérifier l'état des conteneurs

```bash
docker ps --filter name=vm_manager
```

### Configuration Traefik

Les labels Traefik dans `docker-compose.traefik.yml` configurent automatiquement le routage :

- **Application web** : HTTP sur `vm-manager.iris.a3n.fr`
- Traefik route vers le conteneur nginx (frontend)
- nginx proxifie les appels API (`/api/*`) vers Flask en interne
- Le backend n'est pas exposé publiquement (sécurité)

Les deux services sont connectés au réseau Docker `admin_proxy`.

## 🔧 Technologies utilisées

### Backend
- **Python 3.11** + **Flask** : Framework web
- **Gunicorn** : Serveur WSGI
- **Flask-Login** : Gestion de session
- **flask-ldap3-login** : Authentification LDAP (optionnel)
- **libvirt-python** : Interaction avec libvirt/virsh
- **websockify** : Proxy WebSocket pour noVNC

### Frontend
- **HTML/CSS/JavaScript Vanilla**
- **nginx** : Serveur web (conteneur Docker)
- **Formspree** : Formulaire de demande de ressources (service tiers)

### Infrastructure
- **Docker** : Containerisation
- **Docker Compose** : Orchestration
- **Traefik** : Reverse proxy + TLS automatique
- **Ansible** : Automatisation du déploiement (alternative documentée)

## 📋 Variables d'environnement

Le fichier `.env` à la racine contient :

```bash
DOMAIN_NAME=iris.a3n.fr
```

Variables optionnelles pour le backend (dans le conteneur) :
- `SECRET_KEY` : Clé secrète Flask
- `LDAP_HOST`, `LDAP_BASE_DN`, etc. : Configuration LDAP

## 🎓 Déploiement Ansible (Alternative documentée)

Le projet inclut une configuration Ansible complète pour un déploiement alternatif sans Docker.

### Commande de déploiement

```bash
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml -e non_root_deploy=true
```

### Ce que fait Ansible

1. Crée un environnement virtuel Python sur le serveur
2. Installe les dépendances backend
3. Génère des scripts de démarrage (`start_backend.sh`, `start_websockify.sh`)
4. Démarre les services en arrière-plan avec `nohup`

**Mode non-root** : Utilisé car les droits sudo sont limités (uniquement `apt`/`apt-get`).

### Fichiers Ansible

- `ansible/deploy.yml` : Playbook principal avec logique conditionnelle (root/non-root)
- `ansible/inventory.ini` : Configuration serveur cible
- `ansible/templates/` : Templates systemd pour le mode privilégié

## 🖥️ noVNC et websockify

Le dossier `noVNC/` contient les fichiers statiques de noVNC pour l'accès aux consoles VNC des VMs.

- Télécharger noVNC : https://github.com/novnc/noVNC
- Le backend démarre automatiquement `websockify` sur un port libre (6080-6180)

## 🎯 Ports utilisés

- **5000** : Backend Flask (dans le conteneur)
- **80** : Frontend nginx (dans le conteneur)
- **6080+** : websockify/noVNC (cherche port libre automatiquement)
- **5900+** : Ports VNC internes des VMs

## 🔐 Windows VMs (notes)

### Comptes créés
- `Administrator` (mot de passe root)
- Compte utilisateur personnalisé (défini à la création)
- `vagrant` (pour compatibilité)

### Exigences mot de passe
Minimum 8 caractères : 1 majuscule, 1 minuscule, 1 chiffre (ex: `Azerty123`)

### Configuration
- Clavier : AZERTY (français)
- Temps de provisioning : 5-10 minutes (premier boot)
- Arrêt : tentative graceful (`vagrant halt`) puis forcé (`virsh destroy`) si timeout

## 🛠️ Développement local

### Prérequis
- Python 3.11+
- Docker (pour tester les conteneurs)

### Installation des dépendances

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Lancer en mode développement

```bash
export FLASK_APP=backend/main.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=5000
```

### Construire les images Docker localement

```bash
docker build -t vm_manager_backend:local ./backend
docker build -t vm_manager_frontend:local ./frontend
```

## 📊 Monitoring et logs

### Logs des conteneurs

```bash
# Tous les services
docker-compose -f docker-compose.traefik.yml logs -f

# Backend uniquement
docker logs vm_manager_backend -f

# Frontend uniquement
docker logs vm_manager_frontend -f
```

### État des conteneurs

```bash
docker ps --filter name=vm_manager
docker stats vm_manager_backend vm_manager_frontend
```

## 🐛 Dépannage

### Les conteneurs ne démarrent pas

```bash
# Vérifier les logs
docker-compose -f docker-compose.traefik.yml logs

# Vérifier la configuration
docker-compose -f docker-compose.traefik.yml config

# Reconstruire les images
docker-compose -f docker-compose.traefik.yml build --no-cache
docker-compose -f docker-compose.traefik.yml up -d
```

### Le site n'est pas accessible

1. Vérifier que les conteneurs tournent :
   ```bash
   docker ps --filter name=vm_manager
   ```

2. Vérifier le réseau Traefik :
   ```bash
   docker network inspect admin_proxy
   ```

3. Vérifier les logs Traefik (si accès) :
   ```bash
   docker logs traefik
   ```

### noVNC ne fonctionne pas

1. Vérifier que `noVNC/` existe dans le projet
2. Vérifier que `websockify` est installé dans le backend
3. Vérifier les logs backend pour les erreurs de démarrage websockify

## 🔒 Sécurité

### Recommandations production

- ✅ Traefik gère automatiquement le TLS avec Let's Encrypt
- ✅ Backend exposé uniquement via reverse proxy
- ✅ Conteneurs isolés dans un réseau Docker dédié
- ⚠️ Protéger l'accès noVNC avec authentification
- ⚠️ Configurer les limites de ressources dans docker-compose
- ⚠️ Sauvegarder régulièrement les VMs et données

### Variables sensibles

- Ne jamais commit `.env` avec des secrets réels
- Utiliser Ansible Vault pour les secrets en production
- Rotate les clés API et tokens régulièrement

## 📚 Documentation supplémentaire

- **DEPLOYMENT_REVIEW.md** : Guide détaillé pour le professeur
- **ansible/deploy.yml** : Playbook commenté avec explications

## 🤝 Contribution

Projet réalisé dans le cadre du BTS SISR à Mediaschool.

### Auteur
- **edib** - Étudiant BTS SISR 2025

### Serveur
- Hébergé sur iris.a3n.fr
- Gestion : Mediaschool-BTS-SISR-2025

---

Pour toute question ou problème, consulter les logs ou contacter l'administrateur système.
