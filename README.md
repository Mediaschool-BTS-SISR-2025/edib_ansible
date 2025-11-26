# VM_Manager

VM_Manager est une interface web simple pour gérer des machines virtuelles (création via Vagrant/libvirt, gestion via libvirt/virsh et accès via noVNC).

## Technologies utilisées

- Backend: Python + Flask
  - `Flask` pour l'application web
  - `Flask-Login` pour la gestion de session
  - `flask-ldap3-login` (optionnel) pour authentification LDAP
  - `libvirt-python` pour interagir avec libvirt/virsh
  - `websockify` + `noVNC` pour la console web VNC
  - `python-dotenv` pour charger les variables d'environnement
- Frontend: HTML/CSS/Vanilla JavaScript
  - `frontend/index.html`, `frontend/static/styles.css`, `frontend/static/app.js`
- Formulaire de demande de ressources: Formspree (service tiers)

## Ports utilisés (par défaut)

- `5000` — Flask (VM Manager)
- `6080` — noVNC / websockify (par défaut recherche de ports libres depuis 6080)
- `5900+` — ports VNC internes configurés par libvirt (dépend de la VM)

> Remarque: le port public réel pour noVNC dépendra du port libre trouvé par `websockify`. Le serveur cherche un port libre entre `6080` et `6180`.

## Structure du dépôt

- `backend/` : code Flask
  - `main.py` : application principale
  - `config.py` : configuration (lit les variables d'environnement)
  - `requirements.txt` : dépendances Python (core)
- `frontend/` : fichiers statiques et template
  - `index.html`
  - `static/` : `app.js`, `styles.css`
- `student_vms/` : dossiers VM par utilisateur (créés automatiquement)

## Variables d'environnement importantes

Vous pouvez définir ces variables dans un fichier `.env` à la racine du projet ou les exporter dans l'environnement de l'OS.

- `SECRET_KEY` — clé secrète Flask (par défaut: `dev-secret-change-me`)
- `LDAP_HOST`, `LDAP_BASE_DN`, `LDAP_BIND_USER_DN`, `LDAP_BIND_USER_PASSWORD` — paramètres LDAP (optionnels)

## Installer les dépendances

Créez un environnement virtuel (recommandé) et installez les dépendances :

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
```

## Démarrage en développement

Depuis la racine du projet :

```bash
export FLASK_APP=backend/main.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=5000
```

L'interface sera accessible sur `http://localhost:5000`.

## Exécution en production (recommendé)

1. Installer et configurer `gunicorn` (déjà dans `requirements.txt`).
2. Mettre en place un reverse-proxy `nginx` devant l'application Flask.

Exemple minimal de commande `gunicorn` :

```bash
cd backend
. ../.venv/bin/activate
gunicorn --bind 0.0.0.0:5000 main:app
```

### Exemple `nginx` (reverse proxy + TLS)

- Le serveur Nginx sert `VM_Manager.a3n.fr` et reverse-proxy vers `http://127.0.0.1:5000`.
- Pour TLS, utilisez Let's Encrypt (certbot) et configurez automatiquement les certificats.

Extrait de configuration Nginx (à adapter) :

```
server {
    listen 80;
    server_name VM_Manager.a3n.fr;
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name VM_Manager.a3n.fr;

    ssl_certificate /etc/letsencrypt/live/VM_Manager.a3n.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/VM_Manager.a3n.fr/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Exemple: rediriger /vnc proxies si nécessaire
}
```

## Configuration DNS pour `VM_Manager.a3n.fr`

1. Dans le panneau DNS de votre fournisseur de domaine `a3n.fr`, créez un enregistrement `A` :
   - Nom/Host: `VM_Manager` (ou `VM_Manager.a3n.fr` selon l'UI)
   - Type: `A`
   - Valeur: l'adresse IP publique de votre serveur
2. Attendre la propagation DNS (quelques minutes à quelques heures).
3. Configurer Nginx et Let's Encrypt pour activer HTTPS.

## noVNC et websockify

Ce projet attend un dossier `noVNC/` (fichiers statiques de noVNC) à la racine du repo si vous voulez que la console web soit servie depuis le même serveur.

- Téléchargez noVNC depuis : https://github.com/novnc/noVNC
- Placez le dossier `noVNC` à la racine du dépôt (même niveau que `backend/` et `frontend/`).

Le serveur démarre `websockify` automatiquement pour chaque VM et cherche un port libre entre `6080` et `6180`.

Si `noVNC/` est absent, `websockify` démarrera quand même mais la page `vnc.html` ne sera pas servie depuis ce dépôt — vous devrez alors héberger noVNC ailleurs ou copier les fichiers nécessaires.

## Formspree (formulaire de demande de ressources)

La fonctionnalité de demande de ressources utilise Formspree (service tiers) pour envoyer des emails sans backend local.

- Allez sur https://formspree.io et créez un formulaire.
- Remplacez l'endpoint dans `frontend/index.html` :

```html
<form action="https://formspree.io/f/<VOTRE_FORM_ID>" method="POST" id="resourceForm">
```

- Confirmez votre adresse email via le lien envoyé par Formspree (première utilisation).

## Points d'attention et recommandations

- Le code interagit avec `libvirt` / `virsh` / `vagrant` et nécessite que ces outils soient installés et configurés correctement sur le serveur.
- L'application doit être exécutée avec un utilisateur ayant les droits d'accès à `libvirt` (souvent `root` ou membre du groupe `libvirt`).
- Sauvegardez les VMs et configurations avant tests importants.

## Dépannage rapide

- Si la console noVNC ne s'ouvre pas : vérifier que `noVNC/` existe, que `websockify` est installé et qu'un port libre est disponible.
- Si un import LDAP pose problème, vérifiez vos variables d'environnement LDAP dans `.env`.

---

Si vous voulez, je peux :

- Nettoyer davantage `requirements.txt` et créer un script d'installation automatique.
- Générer une configuration `systemd` pour lancer `gunicorn` au démarrage.
- Préparer un `nginx` config complet et commandes `certbot` pour automatiser le TLS.

Dites-moi quel(s) point(s) vous voulez que j'implémente ensuite (ex: `systemd` service, configuration nginx prête à coller, scripts d'installation).