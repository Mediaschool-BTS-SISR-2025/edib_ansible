Guide de déploiement Ansible

Prérequis sur la machine de contrôle (où tu lances ansible):
- Ansible installé (`pip install ansible`) ou via apt/yum.

Prérequis côté cible:
- SSH access + privilèges `sudo` pour l'utilisateur défini dans l inventory.

Utilisation rapide (test local):

```bash
# depuis la racine du dépôt
cd ansible
ansible-playbook -i inventory.ini deploy.yml
```

Notes:
- Le playbook installe git, python3-venv, docker.io, clone le repo sur la cible, exécute `deploy.sh` (qui crée le venv et active le service systemd) puis build & run le conteneur frontend sur le port `8080`.
- Si tu veux utiliser hosts distants, modifie `inventory.ini` avec l'adresse et méthode de connexion.

Ansible Vault (gestion des secrets)
----------------------------------

Ce dépôt fournit un exemple de variables sensibles à placer dans `ansible/group_vars/all/vault.yml`. **Ne commite jamais** de secrets en clair.

1) Créer le fichier d'exemple (fourni) :

```
ansible/group_vars/all/vault.yml.example
```

2) Copier et chiffrer en utilisant Ansible Vault :

```bash
# depuis la racine du dépôt
cp ansible/group_vars/all/vault.yml.example ansible/group_vars/all/vault.yml
ansible-vault encrypt ansible/group_vars/all/vault.yml
```

3) Options pour exécuter le playbook avec Vault :

- Demander le mot de passe au runtime :
	```bash
	ansible-playbook -i inventory.ini deploy.yml --ask-vault-pass
	```
- Utiliser un fichier contenant le mot de passe (moins interactif) :
	```bash
	ansible-playbook -i inventory.ini deploy.yml --vault-password-file ~/.vault_pass.txt
	```

4) Bonnes pratiques :
- Utiliser `ansible-vault edit` pour modifier les valeurs chiffrées.
- Stocker le mot de passe Vault en sécurité (ex: gestionnaire de secrets de l'école), ou utiliser un fichier protégé par des permissions strictes si nécessaire.
- Ne pas committer `vault.yml` chiffré sans informer le professeur (selon la politique de l'école), mais le commit chiffré est acceptable si le mot de passe n'est pas partagé.

Intégration avec le playbook
---------------------------

Le playbook lit automatiquement les variables dans `group_vars/all/`. Si `ansible-vault` est utilisé pour chiffrer ce fichier, il faut fournir `--ask-vault-pass` ou `--vault-password-file` lors de l'exécution du playbook.


Changements récents
-------------------

Ce dépôt a été mis à jour pour faciliter le déploiement et la revue :

- Le playbook `ansible/deploy.yml` utilise désormais la collection `community.docker` pour construire l'image et gérer le conteneur frontend de façon idempotente. Installez-la avec :

```bash
ansible-galaxy collection install community.docker
```

- L'inventaire d'exemple (`ansible/inventory.ini`) inclut maintenant une entrée commentée pour un hôte distant (ex : `37.64.159.66`) et montre comment configurer la clé privée, le port SSH et l'utilisateur.

- Un document de revue en français `DEPLOYMENT_REVIEW.md` a été ajouté à la racine du dépôt. Il contient un récapitulatif destiné au professeur (architecture, checklist, instructions Vault, vérifications post-déploiement).

- Le playbook conserve l'appel à `deploy.sh` (script local) pour la création du virtualenv et l'installation des dépendances. Si tu préfères, on peut convertir toute la logique de `deploy.sh` en tâches Ansible idempotentes — dis‑moi et je m'en occupe.

Remarque : Avant d'exécuter le playbook, installez la collection `community.docker` et chiffrez `ansible/group_vars/all/vault.yml` si vous utilisez des secrets.

