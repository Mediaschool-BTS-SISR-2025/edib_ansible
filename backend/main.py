from flask import Flask, render_template, jsonify, request
from flask_ldap3_login import LDAP3LoginManager
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from pathlib import Path
import datetime
import subprocess
import shutil
import re
import config
import xml.etree.ElementTree as ET
import socket
import signal
import sys
import os  # ← déjà présent

# Éviter l'avertissement du plugin vagrant-winrm (inutile)
os.environ.setdefault('VAGRANT_IGNORE_WINRM_PLUGIN', '1')

# -------------------- Chemins absolus pour templates et static --------------------
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / 'frontend'
STATIC_DIR = TEMPLATE_DIR / 'static'

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path='/static'
)

# -------------------- Configuration --------------------
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['LDAP_HOST'] = config.LDAP_HOST
app.config['LDAP_BASE_DN'] = config.LDAP_BASE_DN
app.config['LDAP_USER_DN'] = config.LDAP_USER_DN
app.config['LDAP_GROUP_DN'] = config.LDAP_GROUP_DN
app.config['LDAP_USER_RDN_ATTR'] = config.LDAP_USER_RDN_ATTR
app.config['LDAP_USER_LOGIN_ATTR'] = config.LDAP_USER_LOGIN_ATTR
app.config['LDAP_BIND_USER_DN'] = config.LDAP_BIND_USER_DN
app.config['LDAP_BIND_USER_PASSWORD'] = config.LDAP_BIND_USER_PASSWORD

# -------------------- Flask-Login --------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

# -------------------- LDAP Manager --------------------
ldap_manager = LDAP3LoginManager()
ldap_manager.init_app(app)

# -------------------- User Class --------------------
class User(UserMixin):
    def __init__(self, dn, username, data):
        self.dn = dn
        self.username = username
        self.data = data

    def __repr__(self):
        return self.dn

    def get_id(self):
        return self.dn

@login_manager.user_loader
def load_user(user_id):
    # user_id = DN, ex: "uid=alice,ou=users,dc=example,dc=com"
    username = user_id.split(',')[0].split('=')[1] if '=' in user_id else user_id
    return User(user_id, username, {})

@ldap_manager.save_user
def save_user(dn, username, data, memberships):
    return User(dn, username, data)

# -------------------- Fonctions helper pour isolation --------------------
def get_user_vm_dir(username):
    """
    Retourne le dossier des VMs pour un utilisateur donné.
    Exemple: student_vms/alice/
    """
    base = Path(__file__).parent.parent / 'student_vms' / username
    base.mkdir(parents=True, exist_ok=True)
    return base

def is_admin(username):
    """
    Vérifie si l'utilisateur est admin.
    Les admins peuvent voir et gérer toutes les VMs.
    """
    ADMIN_USERS = ['admin', 'root']  # À synchroniser avec LDAP plus tard
    return username in ADMIN_USERS

def check_vm_ownership(username, vm_name):
    """
    Vérifie si l'utilisateur a le droit d'accéder à cette VM.
    Retourne (True, vm_path) si autorisé, (False, None) sinon.
    """
    if is_admin(username):
        # Admin : chercher dans tous les sous-dossiers
        base = Path(__file__).parent.parent / 'student_vms'
        for user_dir in base.iterdir():
            if user_dir.is_dir():
                vm_path = user_dir / vm_name
                if vm_path.exists():
                    return True, vm_path
        return False, None
    else:
        # Utilisateur normal : uniquement son dossier
        vm_path = get_user_vm_dir(username) / vm_name
        if vm_path.exists():
            return True, vm_path
        return False, None

def get_vm_state(vm_name):
    """
    Retourne l'état d'une VM : 'running', 'shut off', 'paused', etc.
    Retourne 'unknown' si introuvable.
    """
    try:
        domain_name = f"{vm_name}_default"
        result = subprocess.run(
            ['virsh', '-c', 'qemu:///system', 'domstate', domain_name],
            capture_output=True,
            text=True,
            check=True
        )
        state = result.stdout.strip().lower()
        
        # Normaliser l'état (français → anglais)
        if 'exécution' in state or 'execution' in state:
            return 'running'
        elif 'arrêt' in state or 'shut' in state:
            return 'shut off'
        elif 'pause' in state or 'paused' in state:
            return 'paused'
        else:
            return state
    except subprocess.CalledProcessError:
        return 'unknown'

def ensure_box_installed(box_name, provider="libvirt"):
    """
    Vérifie si une box Vagrant est installée.
    Retourne True si présente, False sinon.
    """
    try:
        result = subprocess.run(
            ['vagrant', 'box', 'list'],
            capture_output=True,
            text=True,
            check=True
        )
        # Chercher la box avec le provider spécifié
        # Format: "generic/debian12                           (libvirt, 4.3.12, (amd64))"
        # On vérifie ligne par ligne pour gérer les espaces multiples
        for line in result.stdout.splitlines():
            if line.startswith(box_name) and f"({provider}," in line:
                return True
        return False
    except subprocess.CalledProcessError:
        return False

# -------------------- Page principale --------------------
@app.route('/')
def index():
    return render_template('index.html')

# -------------------- API Login --------------------
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Identifiants manquants'}), 400

    # Auth temporaire (remplace LDAP le temps des tests)
    try:
        from test_auth import authenticate_test_user
        if authenticate_test_user(username, password):
            user_dn = f"uid={username},ou=users,dc=test,dc=local"
            user = User(user_dn, username, {})
            login_user(user)
            return jsonify({'success': True, 'message': f'Bienvenue {username}'})
        else:
            return jsonify({'success': False, 'message': 'Identifiants incorrects'}), 401
    except Exception as e:
        print(f"Erreur auth test: {e}")
        return jsonify({'success': False, 'message': 'Erreur d\'authentification'}), 500

# -------------------- API Logout --------------------
@app.route('/api/logout')
@login_required
def api_logout():
    logout_user()
    return jsonify({'success': True, 'message': 'Déconnexion réussie'})

# -------------------- Easter Egg Cowsay --------------------
@app.route('/api/cowsay')
def api_cowsay():
    """Easter egg: exécute cowsay avec le message."""
    try:
        # Vérifier si cowsay est installé
        result = subprocess.run(
            ['which', 'cowsay'],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # cowsay n'est pas installé, renvoyer une version ASCII art simple
            output = """
 _____________________
< Réalisé par Edib >
 ---------------------
        \\   ^__^
         \\  (oo)\\_______
            (__)\\       )\\/\\
                ||----w |
                ||     ||
"""
        else:
            # cowsay est installé, l'exécuter
            result = subprocess.run(
                ['cowsay', 'Réalisé par Edib'],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout
        
        return jsonify({'output': output})
    except Exception as e:
        # En cas d'erreur, renvoyer la version simple
        output = """
 _____________________
< Réalisé par Edib >
 ---------------------
        \\   ^__^
         \\  (oo)\\_______
            (__)\\       )\\/\\
                ||----w |
                ||     ||
"""
        return jsonify({'output': output})

# -------------------- Liste des VMs --------------------
@app.route('/api/list_vms')
@login_required
def list_vms():
    username = current_user.username
    vms = []
    
    if is_admin(username):
        # Admin voit TOUTES les VMs de tous les utilisateurs
        base = Path(__file__).parent.parent / 'student_vms'
        if base.exists():
            for user_dir in sorted(base.iterdir()):
                if user_dir.is_dir():
                    for vm_dir in sorted(user_dir.iterdir()):
                        if vm_dir.is_dir():
                            vm_info = {
                                'name': vm_dir.name,
                                'owner': user_dir.name,
                                'path': str(vm_dir),
                                'state': get_vm_state(vm_dir.name)
                            }
                            vms.append(vm_info)
    else:
        # Utilisateur normal voit uniquement SES VMs
        user_dir = get_user_vm_dir(username)
        if user_dir.exists():
            for vm_dir in sorted(user_dir.iterdir()):
                if vm_dir.is_dir():
                    vm_info = {
                        'name': vm_dir.name,
                        'owner': username,
                        'path': str(vm_dir),
                        'state': get_vm_state(vm_dir.name)
                    }
                    vms.append(vm_info)
    
    return jsonify({'vms': vms, 'user': username, 'is_admin': is_admin(username)})

# -------------------- Créer une VM --------------------
@app.route('/api/create_vm', methods=['POST'])
@login_required
def create_vm():
    data = request.get_json() or {}
    vm_name = data.get('vm_name')
    vm_type = data.get('vm_type')
    os_name = data.get('os')
    vm_username = data.get('vm_username')
    vm_password = data.get('vm_password')
    root_password = (data.get('root_password') or "").strip()

    # Validation root_password : OBLIGATOIRE pour Debian, OPTIONNEL pour Windows
    if os_name != "windows":
        if not root_password:
            return jsonify({'message': 'Mot de passe root requis pour Debian'}), 400
        if len(root_password) < 6:
            return jsonify({'message': 'Le mot de passe root doit contenir au moins 6 caractères'}), 400

    # Snippet pour définir le mot de passe root (Debian uniquement)
    root_pass_snippet = ""
    if os_name != "windows" and root_password:
        root_pass_snippet = f'''echo "root:{root_password}" | chpasswd
usermod -U root || true
'''

    # Validation basique
    if not vm_username or not vm_password:
        return jsonify({'message': 'Nom d\'utilisateur et mot de passe requis'}), 400
    
    # Validation spécifique Windows (complexité du mot de passe utilisateur uniquement)
    if os_name == "windows":
        if len(vm_password) < 8:
            return jsonify({'message': 'Windows: mot de passe minimum 8 caractères'}), 400
        if not re.search(r'[A-Z]', vm_password):
            return jsonify({'message': 'Windows: mot de passe doit contenir au moins 1 majuscule'}), 400
        if not re.search(r'[a-z]', vm_password):
            return jsonify({'message': 'Windows: mot de passe doit contenir au moins 1 minuscule'}), 400
        if not re.search(r'[0-9]', vm_password):
            return jsonify({'message': 'Windows: mot de passe doit contenir au moins 1 chiffre'}), 400
    else:
        # Linux: validation simple
        if len(vm_password) < 6:
            return jsonify({'message': 'Le mot de passe doit contenir au moins 6 caractères'}), 400

    # Nom de VM normalisé
    vm_name = re.sub(r'[^A-Za-z0-9._-]', '-', vm_name)[:64] if vm_name else f"vm-{int(datetime.datetime.utcnow().timestamp())}"

    base = Path(__file__).parent.parent / 'student_vms'
    base.mkdir(parents=True, exist_ok=True)
    vmdir = base / vm_name

    # Créer dans le dossier de l'utilisateur
    base = get_user_vm_dir(current_user.username)
    vmdir = base / vm_name

    if vmdir.exists():
        return jsonify({'message': f'Nom de VM déjà utilisé : {vm_name}'}), 400

    try:
        vmdir.mkdir()

        # Choix de la box et ressources
        if os_name == "debian":
            box_name = "generic/debian12"
            if vm_type == "client":
                memory, cpus, serial_console = 4096, 2, False
                # Provisioning script pour Debian (client)
                provision_script = f"""
export DEBIAN_FRONTEND=noninteractive
apt-get update

# Préselectionner LightDM comme display manager (évite l'invite non-interactive)
echo "lightdm shared/default-x-display-manager select lightdm" | debconf-set-selections

# Paquets clavier/locale
apt-get install -y kbd console-setup keyboard-configuration locales

# Locale FR
sed -i 's/# fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=fr_FR.UTF-8

# Clavier FR (console + X11)
cat > /etc/default/keyboard << 'EOF'
XKBMODEL="pc105"
XKBLAYOUT="fr"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
EOF
dpkg-reconfigure -f noninteractive keyboard-configuration || true
setupcon --force --save || true
loadkeys fr 2>/dev/null || true
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf << 'EOF'
Section "InputClass"
    Identifier "system-keyboard"
    MatchIsKeyboard "on"
    Option "XkbModel" "pc105"
    Option "XkbLayout" "fr"
    Option "XkbVariant" ""
    Option "XkbOptions" ""
EndSection
EOF

# Bureau XFCE + LightDM + Xorg (+ greeter) + drivers utiles
apt-get install -y xorg dbus-x11 policykit-1 \
    lightdm lightdm-gtk-greeter lightdm-gtk-greeter-settings \
    xfce4 xfce4-goodies \
    xserver-xorg-input-libinput xserver-xorg-video-qxl \
    network-manager-gnome fonts-dejavu

# S'assurer que LightDM est le display manager par défaut
echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager

# Démarrage graphique par défaut et démarrage immédiat
systemctl set-default graphical.target
systemctl enable lightdm
systemctl restart lightdm || systemctl start display-manager || true

# Utilisateur
useradd -m -s /bin/bash {vm_username} || true
echo "{vm_username}:{vm_password}" | chpasswd
usermod -aG sudo {vm_username}
mkdir -p /home/{vm_username}
echo "startxfce4" > /home/{vm_username}/.xsession
chown -R {vm_username}:{vm_username} /home/{vm_username}

# Autologin LightDM (optionnel)
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-autologin.conf << 'EOF'
[Seat:*]
autologin-user={vm_username}
autologin-user-timeout=0
EOF

# Mot de passe root obligatoire (déjà validé côté backend)
{root_pass_snippet}

echo "✅ XFCE + LightDM installés et démarrés (mode graphique)."
                """.strip()
            else:
                memory, cpus, serial_console = 2048, 2, True
                # Provisioning script pour Debian (serveur)
                provision_script = f"""
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y kbd console-setup keyboard-configuration locales

# Locale FR
sed -i 's/# fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=fr_FR.UTF-8

# Clavier FR (console)
cat > /etc/default/keyboard << 'EOF'
XKBMODEL="pc105"
XKBLAYOUT="fr"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
EOF

debconf-set-selections << 'DEB'
keyboard-configuration keyboard-configuration/layoutcode string fr
keyboard-configuration keyboard-configuration/modelcode string pc105
DEB
dpkg-reconfigure -f noninteractive keyboard-configuration
setupcon --force --save || true
loadkeys fr 2>/dev/null || true
udevadm trigger --subsystem-match=input --action=change || true

# Exemple d’injection dans le provisioning Debian (client/serveur)
{root_pass_snippet}# mot de passe root défini
# utilisateur
useradd -m -s /bin/bash {vm_username} || true
echo "{vm_username}:{vm_password}" | chpasswd
usermod -aG sudo {vm_username}

# Console série
systemctl enable serial-getty@ttyS0.service
systemctl start serial-getty@ttyS0.service
echo "ttyS0" >> /etc/securetty

echo "✅ Clavier FR activé (console)"
                """.strip()

        elif os_name == "windows":
            # Boxes libvirt disponibles: Windows 10 (client) et Server 2022 (serveur)
            if vm_type == "serveur":
                box_name = "peru/windows-server-2022-standard-x64-eval"
            else:
                # Windows 11 (libvirt) n’est pas publié → utiliser Windows 10 Enterprise eval
                box_name = "peru/windows-10-enterprise-x64-eval"

            memory, cpus, serial_console = 6144, 2, False
            provision_script = f"""
# Configuration Windows - Clavier AZERTY uniquement
# Interface reste en anglais pour eviter redemarrage

Write-Host "=== Configuration Windows ==="

# 1. Desactiver la complexite des mots de passe
Write-Host "Desactivation complexite mots de passe..."
secedit /export /cfg C:\\secpol.cfg | Out-Null
(Get-Content C:\\secpol.cfg).replace("PasswordComplexity = 1", "PasswordComplexity = 0") | Out-File C:\\secpol.cfg
secedit /configure /db C:\\windows\\security\\local.sdb /cfg C:\\secpol.cfg /areas SECURITYPOLICY | Out-Null
Remove-Item -Force C:\\secpol.cfg -ErrorAction SilentlyContinue

# 2. Configuration clavier AZERTY SYSTEME (pour toute la VM)
Write-Host "Configuration clavier AZERTY systeme..."

# METHODE PRINCIPALE: Forcer le clavier par defaut au niveau systeme
# Cette commande force AZERTY pour TOUS les utilisateurs (y compris ecran de connexion)
Set-WinDefaultInputMethodOverride -InputTip "040c:0000040c"

# Configuration culture/region
Set-Culture fr-FR -ErrorAction SilentlyContinue
Set-WinHomeLocation -GeoId 84 -ErrorAction SilentlyContinue
Set-TimeZone -Id "Romance Standard Time" -ErrorAction SilentlyContinue

# Monter le registre HKU
$null = New-PSDrive -Name HKU -PSProvider Registry -Root HKEY_USERS -ErrorAction SilentlyContinue

# Configuration registre .DEFAULT (ecran de connexion et nouveaux comptes)
New-Item -Path "HKU:\\.DEFAULT\\Keyboard Layout\\Preload" -Force -ErrorAction SilentlyContinue | Out-Null
Set-ItemProperty -Path "HKU:\\.DEFAULT\\Keyboard Layout\\Preload" -Name "1" -Value "0000040c" -Force

# Substitutes pour forcer AZERTY
New-Item -Path "HKU:\\.DEFAULT\\Keyboard Layout\\Substitutes" -Force -ErrorAction SilentlyContinue | Out-Null
Set-ItemProperty -Path "HKU:\\.DEFAULT\\Keyboard Layout\\Substitutes" -Name "00000409" -Value "0000040c" -Force

# Configuration machine globale
New-Item -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Keyboard Layout\\DosKeybCodes" -Force -ErrorAction SilentlyContinue | Out-Null
Set-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Keyboard Layout\\DosKeybCodes" -Name "0000040c" -Value "fr" -Force

# Definir AZERTY comme clavier par defaut dans le profil par defaut
New-Item -Path "HKU:\\.DEFAULT\\Control Panel\\International" -Force -ErrorAction SilentlyContinue | Out-Null
Set-ItemProperty -Path "HKU:\\.DEFAULT\\Control Panel\\International" -Name "LocaleName" -Value "fr-FR" -Force

# Configuration du clavier au niveau systeme (Apply to all users)
$LangList = New-WinUserLanguageList fr-FR
Set-WinUserLanguageList $LangList -Force

Write-Host "Clavier AZERTY configure au niveau SYSTEME (ecran de connexion inclus)"

# 3. Creation du compte utilisateur
Write-Host "Creation utilisateur {vm_username}..."
$username = "{vm_username}"
$password = ConvertTo-SecureString "{vm_password}" -AsPlainText -Force

$userExists = Get-LocalUser -Name $username -ErrorAction SilentlyContinue
if (-not $userExists) {{
    New-LocalUser -Name $username -Password $password -FullName "{vm_username}" -PasswordNeverExpires:$true -ErrorAction Stop
    Write-Host "Utilisateur $username cree"
}} else {{
    Set-LocalUser -Name $username -Password $password -PasswordNeverExpires:$true
    Write-Host "Utilisateur $username mis a jour"
}}

Add-LocalGroupMember -Group "Administrators" -Member $username -ErrorAction SilentlyContinue
Write-Host "Utilisateur $username ajoute aux administrateurs"

# 4. Mise a jour mot de passe vagrant (meme mot de passe)
Set-LocalUser -Name "vagrant" -Password $password -PasswordNeverExpires:$true -ErrorAction SilentlyContinue

# 5. Configuration visibilite des comptes
Write-Host "Configuration visibilite des comptes..."
$RegPath = "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\SpecialAccounts\\UserList"
New-Item -Path $RegPath -Force -ErrorAction SilentlyContinue | Out-Null

# Masquer vagrant et Administrator (valeur 0 = masque)
Set-ItemProperty -Path $RegPath -Name "vagrant" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $RegPath -Name "Administrator" -Value 0 -Type DWord -Force

# Afficher explicitement votre compte (valeur 1 = visible)
Set-ItemProperty -Path $RegPath -Name $username -Value 1 -Type DWord -Force

Write-Host "Compte $username visible, vagrant et Administrator masques"

# 6. Activer RDP
Write-Host "Activation RDP..."
Set-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" -Name "fDenyTSConnections" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
Set-Service -Name TermService -StartupType Automatic
Start-Service TermService -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Configuration terminee ==="
Write-Host "Clavier: AZERTY (global)"
Write-Host "Utilisateur visible: {vm_username}"
Write-Host "Comptes masques: vagrant, Administrator"
Write-Host ""

# Programmer un redemarrage via tache planifiee (apres que Vagrant ait fini)
Write-Host "Programmation redemarrage automatique dans 2 minutes..."
Write-Host "(Pour appliquer clavier AZERTY et visibilite des comptes)"

$Action = New-ScheduledTaskAction -Execute "shutdown.exe" -Argument "/r /f /t 0"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "ApplyAZERTY" -Action $Action -Trigger $Trigger -Settings $Settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null

Write-Host "Redemarrage programme dans 2 minutes (tache planifiee)"
Write-Host ""
            """.strip()

        else:
            box_name, memory, cpus, serial_console, provision_script = "generic/debian12", 2048, 2, False, ""

        # Génération du Vagrantfile
        vagrantfile_content = f"""# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "{box_name}"
  config.vm.hostname = "{vm_name}"
"""

        # Windows: communicator WinRM
        if os_name == "windows":
            vagrantfile_content += """
  config.vm.guest = :windows
  config.vm.communicator = "winrm"
  config.winrm.username = "vagrant"
  config.winrm.password = "vagrant"
  config.vm.boot_timeout = 1800
  config.vm.graceful_halt_timeout = 900
"""

        vagrantfile_content += f"""
  config.vm.provider :libvirt do |lv|
    lv.memory = {memory}
    lv.cpus = {cpus}
    lv.graphics_type = "vnc"
    lv.graphics_websocket = -1
    lv.graphics_ip = "127.0.0.1"
    lv.video_type = "qxl"
    lv.keymap = "fr"   # ← clavier VNC côté hyperviseur en FR
    lv.channel :type => 'unix', :target_name => 'org.qemu.guest_agent.0', :target_type => 'virtio'
"""
        if serial_console:
            vagrantfile_content += """    lv.serial :type => "pty", :target_port => "0"
"""
        vagrantfile_content += """  end

  config.vm.synced_folder ".", "/vagrant", type: "rsync", rsync__auto: true, disabled: true
  config.vm.network "private_network", type: "dhcp"
"""

        # Provisioning
        if provision_script:
            if os_name == "windows":
                script_file = vmdir / "provision.ps1"
                with open(script_file, "w", encoding="utf-8") as f:
                    f.write(provision_script)
                vagrantfile_content += """
  config.vm.provision "shell", privileged: true, path: "provision.ps1"
"""
            else:
                vagrantfile_content += f"""
  config.vm.provision "shell", inline: <<-SHELL
{provision_script}
  SHELL
"""

        vagrantfile_content += "end\n"

        # Écriture des fichiers
        with open(vmdir / "Vagrantfile", "w") as f:
            f.write(vagrantfile_content)

        with open(vmdir / "vm_info.txt", "w") as f:
            f.write(f"VM Name: {vm_name}\n")
            f.write(f"Username: {vm_username}\n")
            f.write(f"OS: {os_name}\n")
            f.write(f"Type: {vm_type}\n")
            f.write(f"Created: {datetime.datetime.now()}\n")

        # S’assurer que la box est installée (message clair si échec)
        if not ensure_box_installed(box_name, provider="libvirt"):
            return jsonify({'message': f"Box introuvable: {box_name}. Installez-la d'abord:\n  vagrant box add {box_name} --provider libvirt"}), 400

        # Lancement
        subprocess.run(['vagrant', 'up', '--provider', 'libvirt'], cwd=vmdir, check=True)

        vm_description = ""
        if os_name == "debian" and vm_type == "client":
            vm_description = f" avec interface graphique XFCE (utilisateur: {vm_username})"
        elif os_name == "debian" and vm_type == "serveur":
            vm_description = f" (utilisateur: {vm_username}, console texte)"

        return jsonify({'message': f'VM {vm_name} créée{vm_description}.', 'vm_name': vm_name})

    except subprocess.CalledProcessError as e:
        if vmdir.exists():
            try:
                subprocess.run(['vagrant', 'destroy', '-f'], cwd=vmdir, check=False)
                shutil.rmtree(vmdir)
            except:
                pass
        return jsonify({'message': f'Erreur Vagrant : {e}'}), 500
    except Exception as e:
        if vmdir.exists():
            try:
                shutil.rmtree(vmdir)
            except:
                pass
        return jsonify({'message': f'Erreur création VM : {e}'}), 500

# -------------------- Lancer une VM --------------------
@app.route('/api/launch_vm', methods=['POST'])
@login_required
def launch_vm():
    data = request.get_json() or {}
    vm_name = data.get('vm_name')
    
    if not vm_name:
        return jsonify({'message': 'Nom de VM requis.'}), 400
    
    # Vérifier la propriété
    allowed, vm_path = check_vm_ownership(current_user.username, vm_name)
    if not allowed:
        return jsonify({'message': 'VM introuvable ou accès refusé.'}), 403
    
    try:
        subprocess.run(['vagrant', 'up', '--provider', 'libvirt'], cwd=vm_path, check=True)
        return jsonify({'message': f'VM {vm_name} lancée.'})
    except subprocess.CalledProcessError as e:
        return jsonify({'message': f'Erreur lancement VM : {e}'}), 500

# -------------------- Arrêter une VM --------------------
@app.route('/api/halt_vm', methods=['POST'])
@login_required
def halt_vm():
    data = request.get_json() or {}
    vm_name = data.get('vm_name')
    
    if not vm_name:
        return jsonify({'message': 'Nom de VM requis.'}), 400
    
    # Vérifier la propriété
    allowed, vm_path = check_vm_ownership(current_user.username, vm_name)
    if not allowed:
        return jsonify({'message': 'VM introuvable ou accès refusé.'}), 403
    
    try:
        # Arrêter websockify si actif
        stop_websockify(vm_name)
        
        # Tentative d'arrêt propre d'abord
        result = subprocess.run(
            ['vagrant', 'halt'],
            cwd=vm_path,
            capture_output=True,
            text=True,
            timeout=30  # Timeout réduit
        )
        
        # Si l'arrêt propre échoue (Windows résiste souvent), forcer avec virsh
        if result.returncode != 0:
            print(f"Arrêt propre échoué, tentative d'arrêt forcé...")
            domain_name = f"{vm_name}_default"
            
            # Forcer l'arrêt avec virsh destroy (équivalent à débrancher)
            force_result = subprocess.run(
                ['virsh', '-c', 'qemu:///system', 'destroy', domain_name],
                capture_output=True,
                text=True
            )
            
            if force_result.returncode == 0:
                return jsonify({'message': f'VM {vm_name} arrêtée (forcé).'}), 200
            else:
                print(f"Erreur virsh destroy: {force_result.stderr}")
                return jsonify({'message': f'Erreur lors de l\'arrêt forcé : {force_result.stderr}'}), 500
        
        return jsonify({'message': f'VM {vm_name} arrêtée.'})
    except subprocess.TimeoutExpired:
        # Timeout atteint, forcer l'arrêt immédiatement
        print(f"Timeout vagrant halt, arrêt forcé de {vm_name}...")
        domain_name = f"{vm_name}_default"
        subprocess.run(['virsh', '-c', 'qemu:///system', 'destroy', domain_name], check=False)
        return jsonify({'message': f'VM {vm_name} arrêtée (forcé après timeout).'}), 200
    except Exception as e:
        print(f"Erreur halt_vm: {e}")
        return jsonify({'message': f'Erreur : {str(e)}'}), 500

# -------------------- Supprimer une VM --------------------
@app.route('/api/delete_vm', methods=['POST'])
@login_required
def delete_vm():
    data = request.get_json() or {}
    vm_name = data.get('vm_name')
    
    if not vm_name:
        return jsonify({'message': 'Nom de VM requis.'}), 400
    
    # Vérifier la propriété
    allowed, vm_path = check_vm_ownership(current_user.username, vm_name)
    if not allowed:
        return jsonify({'message': 'VM introuvable ou accès refusé.'}), 403
    
    domain_name = f"{vm_name}_default"
    
    try:
        # 1. Arrêter la websockify si elle tourne
        try:
            stop_websockify(current_user.username, vm_name)
        except Exception as ws_err:
            print(f"Avertissement: erreur arrêt websockify: {ws_err}")
        
        # 2. Tenter vagrant destroy (peut échouer si VM corrompue)
        result = subprocess.run(
            ['vagrant', 'destroy', '-f'], 
            cwd=vm_path, 
            capture_output=True, 
            text=True,
            timeout=60
        )
        
        # Si vagrant destroy échoue, forcer la destruction avec virsh
        if result.returncode != 0:
            print(f"Vagrant destroy a échoué pour {vm_name}, nettoyage forcé...")
            
            # Forcer l'arrêt de la VM avec virsh
            subprocess.run(
                ['virsh', '-c', 'qemu:///system', 'destroy', domain_name],
                check=False,
                capture_output=True
            )
            
            # Supprimer le domaine libvirt
            subprocess.run(
                ['virsh', '-c', 'qemu:///system', 'undefine', domain_name, '--remove-all-storage'],
                check=False,
                capture_output=True
            )
        
        # 3. Supprimer le dossier de la VM dans tous les cas
        if vm_path.exists():
            shutil.rmtree(vm_path)
            print(f"Dossier {vm_path} supprimé")
        
        return jsonify({'message': f'VM {vm_name} supprimée.'})
        
    except subprocess.TimeoutExpired:
        # En cas de timeout, forcer quand même
        print(f"Timeout lors de la suppression de {vm_name}, nettoyage forcé...")
        subprocess.run(['virsh', '-c', 'qemu:///system', 'destroy', domain_name], check=False, capture_output=True)
        subprocess.run(['virsh', '-c', 'qemu:///system', 'undefine', domain_name, '--remove-all-storage'], check=False, capture_output=True)
        if vm_path.exists():
            shutil.rmtree(vm_path)
        return jsonify({'message': f'VM {vm_name} supprimée (forcé après timeout).'})
        
    except Exception as e:
        print(f"Erreur delete_vm: {e}")
        # Même en cas d'erreur, essayer de nettoyer
        try:
            if vm_path.exists():
                shutil.rmtree(vm_path)
        except Exception as cleanup_err:
            print(f"Erreur nettoyage final: {cleanup_err}")
        return jsonify({'message': f'VM supprimée avec avertissements : {str(e)}'}), 200

# -------------------- Lancer GUI (actuel: virt-viewer local) --------------------
@app.route('/api/view_vm', methods=['POST'])
@login_required
def view_vm():
    data = request.get_json() or {}
    vm_name = data.get('vm_name')
    
    if not vm_name:
        return jsonify({'message': 'Nom de VM requis.'}), 400
    
    # Vérifier la propriété
    allowed, vm_path = check_vm_ownership(current_user.username, vm_name)
    if not allowed:
        return jsonify({'message': 'VM introuvable ou accès refusé.'}), 403
    
    vagrantfile_path = vm_path / "Vagrantfile"
    is_gui_vm = False
    if vagrantfile_path.exists():
        content = vagrantfile_path.read_text()
        is_gui_vm = 'xfce' in content.lower() or 'windows' in content.lower()

    domain_name = f"{vm_name}_default"
    try:
        subprocess.Popen(['virt-viewer', '--connect', 'qemu:///system', domain_name])
        return jsonify({'message': f'Console de {vm_name} ouverte.' if not is_gui_vm else f'Interface graphique de {vm_name} ouverte.'})
    except FileNotFoundError:
        return jsonify({'message': 'virt-viewer non installé.'}), 500
    except Exception as e:
        return jsonify({'message': f'Erreur lancement console : {e}'}), 500

# -------------------- Fonctions helper pour noVNC --------------------
def get_vm_vnc_port(vm_name):
    """
    Récupère le port VNC d'une VM via virsh dumpxml.
    Retourne le port ou None si introuvable.
    """
    try:
        domain_name = f"{vm_name}_default"
        result = subprocess.run(
            ['virsh', '-c', 'qemu:///system', 'dumpxml', domain_name],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parser le XML
        root = ET.fromstring(result.stdout)
        graphics = root.find(".//graphics[@type='vnc']")
        
        if graphics is not None:
            port = graphics.get('port')
            if port and port != '-1':
                return int(port)
        
        return None
    except Exception as e:
        print(f"Erreur récupération port VNC: {e}")
        return None

def find_free_port(start=6080, end=6180):
    """
    Trouve un port libre pour websockify.
    """
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return None

# Dictionnaire global pour tracker les processus websockify
websockify_processes = {}

def start_websockify(vm_name, vnc_port):
    """
    Démarre websockify pour une VM.
    Retourne (ws_port, process) ou (None, None) en cas d'erreur.
    """
    ws_port = find_free_port()
    if not ws_port:
        return None, None
    
    try:
        # Chemin vers noVNC dans le projet
        novnc_path = Path(__file__).parent.parent / 'noVNC'

        # Chemin vers websockify dans un éventuel venv
        venv_websockify = Path(__file__).parent.parent / '.venv' / 'bin' / 'websockify'
        websockify_cmd = str(venv_websockify) if venv_websockify.exists() else 'websockify'

        # Préparer la commande en fonction de la présence de noVNC
        cmd = [websockify_cmd, f'{ws_port}', f'127.0.0.1:{vnc_port}']
        if novnc_path.exists():
            cmd.insert(1, '--web')
            cmd.insert(2, str(novnc_path))
        else:
            # Si noVNC absent, afficher un message clair et continuer :
            # websockify démarrera mais la page noVNC ne sera pas servie par ce process.
            print(f"Avis: dossier noVNC introuvable ({novnc_path}). Télécharger noVNC si vous voulez la console web intégrée.")

        # Lancer websockify
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp  # Créer un nouveau groupe de processus
        )
        
        # Sauvegarder le processus
        websockify_processes[vm_name] = {
            'process': process,
            'ws_port': ws_port,
            'vnc_port': vnc_port
        }
        
        return ws_port, process
    except Exception as e:
        print(f"Erreur démarrage websockify: {e}")
        return None, None

def stop_websockify(vm_name):
    """
    Arrête websockify pour une VM.
    """
    if vm_name in websockify_processes:
        try:
            proc_info = websockify_processes[vm_name]
            process = proc_info['process']
            
            # Vérifier si le processus existe encore
            if process.poll() is None:  # None = processus actif
                # Tuer le processus et son groupe
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.wait(timeout=5)
                except ProcessLookupError:
                    pass  # Processus déjà terminé
                except Exception as e:
                    print(f"Erreur kill websockify: {e}")
        except Exception as e:
            print(f"Erreur arrêt websockify: {e}")
        finally:
            # Toujours supprimer l'entrée du dictionnaire
            del websockify_processes[vm_name]

# -------------------- Obtenir l'URL noVNC --------------------
@app.route('/api/get_vnc_url/<vm_name>')
@login_required
def get_vnc_url(vm_name):
    """
    Retourne l'URL noVNC pour accéder à la console de la VM.
    Démarre websockify si nécessaire.
    """
    if not vm_name:
        return jsonify({'success': False, 'message': 'Nom de VM requis'}), 400
    
    # Vérifier la propriété
    allowed, vm_path = check_vm_ownership(current_user.username, vm_name)
    if not allowed:
        return jsonify({'success': False, 'message': 'VM introuvable ou accès refusé'}), 403
    
    # Vérifier que la VM est démarrée
    try:
        domain_name = f"{vm_name}_default"
        result = subprocess.run(
            ['virsh', '-c', 'qemu:///system', 'domstate', domain_name],
            capture_output=True,
            text=True,
            check=True
        )
        
        state = result.stdout.strip().lower()
        # Vérifier si la VM est running (en français ou anglais)
        if 'running' not in state and 'exécution' not in state and 'execution' not in state:
            return jsonify({
                'success': False, 
                'message': f'La VM doit être démarrée (état actuel: {state})'
            }), 400
    except subprocess.CalledProcessError:
        return jsonify({'success': False, 'message': 'VM introuvable dans libvirt'}), 404
    
    # Récupérer le port VNC
    vnc_port = get_vm_vnc_port(vm_name)
    if not vnc_port:
        return jsonify({
            'success': False,
            'message': 'Port VNC introuvable. La VM est-elle configurée en VNC ?'
        }), 500
    
    # Démarrer websockify (ou réutiliser existant)
    if vm_name in websockify_processes:
        ws_port = websockify_processes[vm_name]['ws_port']
    else:
        ws_port, process = start_websockify(vm_name, vnc_port)
        if not ws_port:
            return jsonify({
                'success': False,
                'message': 'Impossible de démarrer le proxy WebSocket'
            }), 500
    
    # Construire l'URL noVNC avec clavier AZERTY (français)
    vnc_url = f"http://localhost:{ws_port}/vnc.html?autoconnect=true&resize=scale&keyboard=fr"
    
    return jsonify({
        'success': True,
        'url': vnc_url,
        'ws_port': ws_port,
        'vnc_port': vnc_port
    })

# -------------------- Lancement Flask --------------------
if __name__ == '__main__':
    # Dev server
    app.run(debug=True, host='0.0.0.0', port=5000)
