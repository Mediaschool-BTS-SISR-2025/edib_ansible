from flask import Flask, render_template, jsonify, request
from flask_ldap3_login import LDAP3LoginManager
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from pathlib import Path
import datetime
import subprocess
import shutil
import os
import re
import signal
import socket
import sys
import xml.etree.ElementTree as ET
import config
import csv
import smtplib
import ssl
from email.message import EmailMessage

# Éviter l’avertissement du plugin vagrant-winrm (inutile)
os.environ.setdefault('VAGRANT_IGNORE_WINRM_PLUGIN', '1')
os.environ.setdefault('VAGRANT_DEFAULT_PROVIDER', 'libvirt')  # ← forcer libvirt par défaut

# Utiliser la partition si présente
if not os.environ.get('VAGRANT_HOME') and os.path.isdir('/mnt/partition2/vagrant.d'):
    os.environ['VAGRANT_HOME'] = '/mnt/partition2/vagrant.d'
if not os.environ.get('TMPDIR') and os.path.isdir('/mnt/partition2/tmp'):
    os.environ['TMPDIR'] = '/mnt/partition2/tmp'
# Fallback vers /data (nouvel emplacement)
if not os.environ.get('VAGRANT_HOME') and os.path.isdir('/data/vagrant.d'):
    os.environ['VAGRANT_HOME'] = '/data/vagrant.d'
if not os.environ.get('TMPDIR') and os.path.isdir('/data/tmp'):
    os.environ['TMPDIR'] = '/data/tmp'

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

    # OBLIGATOIRE: root_password
    if not root_password:
        return jsonify({'message': 'Mot de passe root/Administrator requis'}), 400
    if len(root_password) < 6:
        return jsonify({'message': 'Le mot de passe root/Administrator doit contenir au moins 6 caractères'}), 400

    # AJOUT: snippet utilisé dans le provisioning Debian
    # - définit le mot de passe root
    # - déverrouille le compte si verrouillé
    root_pass_snippet = f'''echo "root:{root_password}" | chpasswd
usermod -U root || true
'''

    # Validation basique
    if not vm_username or not vm_password:
        return jsonify({'message': 'Nom d\'utilisateur et mot de passe requis'}), 400
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

    # Vérifs provider + réseau avant toute création
    if not ensure_libvirt_provider():
        return jsonify({'message': "Plugin vagrant-libvirt manquant. Installez-le:\n  env VAGRANT_HOME=/data/vagrant.d vagrant plugin install vagrant-libvirt"}), 500
    ensure_libvirt_network()

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
            # TEMP: forcer Server 2022 pour client/serveur (Win10/11 trop lourdes / indisponibles)
            box_name = "peru/windows-server-2022-standard-x64-eval"
            memory, cpus, serial_console = 6144, 2, False
            provision_script = f"""
# Langue/Clavier FR
$LangList = New-WinUserLanguageList fr-FR
Set-WinUserLanguageList $LangList -Force
Set-Culture fr-FR
Set-WinSystemLocale fr-FR
Set-WinUILanguageOverride fr-FR
Set-TimeZone -Id "Romance Standard Time"

New-Item -Path "HKU:\\.DEFAULT\\Keyboard Layout\\Preload" -Force | Out-Null
Set-ItemProperty -Path "HKU:\\.DEFAULT\\Keyboard Layout\\Preload" -Name "1" -Value "0000040C"

$adminPass = ConvertTo-SecureString "{root_password}" -AsPlainText -Force
Set-LocalUser -Name "Administrator" -Password $adminPass

$username = "{vm_username}"
$password = ConvertTo-SecureString "{vm_password}" -AsPlainText -Force
$userExists = Get-LocalUser -Name $username -ErrorAction SilentlyContinue
if (-not $userExists) {{
  New-LocalUser -Name $username -Password $password -FullName "{vm_username}" -PasswordNeverExpires
  Add-LocalGroupMember -Group "Administrators" -Member $username
}}

# Activer RDP
Set-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" -Name "fDenyTSConnections" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
Set-Service -Name TermService -StartupType Automatic
Start-Service TermService

Write-Host "✅ Windows Server configuré (FR + Admin + RDP)."
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
    lv.keymap = "fr"
    lv.storage_pool_name = "default"
    lv.channel :type => 'unix', :target_name => 'org.qemu.guest_agent.0', :target_type => 'virtio'
"""
        if serial_console:
            vagrantfile_content += """    lv.serial :type => "pty", :target_port => "0"
"""
        vagrantfile_content += """  end

  config.vm.synced_folder ".", "/vagrant", type: "rsync", rsync__auto: true, disabled: true
  config.vm.network "private_network", type: "dhcp", libvirt__network_name: "default"
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
        if not ensure_libvirt_provider():
            return jsonify({'message': 'Plugin libvirt manquant'}), 500
        ensure_libvirt_network()
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
        
        # Arrêter la VM
        result = subprocess.run(
            ['vagrant', 'halt', '--provider', 'libvirt'],
            cwd=vm_path,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"Erreur vagrant halt: {result.stderr}")
            return jsonify({'message': f'Erreur lors de l\'arrêt : {result.stderr}'}), 500
        
        return jsonify({'message': f'VM {vm_name} arrêtée.'})
    except subprocess.TimeoutExpired:
        return jsonify({'message': 'Timeout lors de l\'arrêt de la VM'}), 500
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
    
    try:
        subprocess.run(['vagrant', 'destroy', '-f', '--provider', 'libvirt'], cwd=vm_path, check=True)
        shutil.rmtree(vm_path)
        return jsonify({'message': f'VM {vm_name} supprimée.'})
    except subprocess.CalledProcessError as e:
        return jsonify({'message': f'Erreur suppression VM : {e}'}), 500
    except Exception as e:
        return jsonify({'message': f'Erreur suppression VM : {e}'}), 500

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

    # Localiser noVNC (inclut ~/.noVNC)
    from pathlib import Path as _P
    candidates = [
        os.environ.get("NOVNC_WEB") or "",
        "/usr/share/novnc",
        "/usr/share/webapps/novnc",
        "/usr/local/share/novnc",
        str(_P.home() / "noVNC"),
    ]
    web_dir = next((p for p in candidates if p and os.path.isdir(p)), None)
    if not web_dir:
        print("noVNC introuvable. Installez 'novnc' ou définissez $NOVNC_WEB.")
        return None, None

    # binaire websockify ou fallback python -m websockify
    ws_bin = shutil.which("websockify")
    if ws_bin:
        cmd = [ws_bin, "--web", web_dir, str(ws_port), f"127.0.0.1:{vnc_port}"]
    else:
        cmd = [sys.executable, "-m", "websockify", "--web", web_dir, str(ws_port), f"127.0.0.1:{vnc_port}"]

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp
        )
        websockify_processes[vm_name] = {'process': process, 'ws_port': ws_port, 'vnc_port': vnc_port}
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

def ensure_box_installed(box_name, provider="libvirt"):
    """
    Vérifie si la box Vagrant est installée pour le provider donné.
    Sinon, tente de l'installer. Retourne True si OK, False sinon.
    """
    try:
        res = subprocess.run(["vagrant", "box", "list"], capture_output=True, text=True, check=True)
        if box_name in res.stdout:
            return True
        print(f"[ensure_box_installed] Installation de {box_name} ({provider})...")
        add = subprocess.run(["vagrant", "box", "add", box_name, "--provider", provider, "--clean"], check=True)
        return add.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"[ensure_box_installed] Erreur: {e}")
        return False

# -------------------- Helpers capacité (parsing + email + log) --------------------
def _parse_ram_to_mb(value: str):
    """
    Convertit une valeur texte en Mégaoctets (MB) pour la RAM.
    Exemples: '4096' -> 4096 MB, '4G'/'4GB'/'4Go' -> 4096 MB, '512M'/'512MB' -> 512 MB
    """
    if value is None:
        return None
    s = str(value).strip().lower().replace(',', '.')
    m = re.match(r'^\s*(\d+(?:\.\d+)?)\s*([a-z]{0,3})\s*$', s)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit in ('', 'm', 'mb'):
        mb = int(round(num))
    elif unit in ('g', 'gb', 'go'):
        mb = int(round(num * 1024))
    else:
        return None
    return mb if mb > 0 else None

def _parse_storage_to_gb(value: str):
    """
    Convertit une valeur texte en Gigaoctets (GB) pour le stockage.
    Par défaut: GB. Ex: '80' -> 80 GB, '80GB'/'80Go' -> 80 GB, '10240MB' -> 10 GB.
    """
    if value is None:
        return None
    s = str(value).strip().lower().replace(',', '.')
    m = re.match(r'^\s*(\d+(?:\.\d+)?)\s*([a-z]{0,3})\s*$', s)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit in ('', 'g', 'gb', 'go'):
        gb = int(round(num))
    elif unit in ('m', 'mb'):
        gb = int(round(num / 1024.0))
    elif unit in ('t', 'tb'):
        gb = int(round(num * 1024.0))
    else:
        return None
    return gb if gb > 0 else None

def _append_capacity_request_log(user_dn: str, vm_name: str, resource: str, value_str: str, reason: str):
    """
    Journalise la demande dans un CSV (capacity_requests.csv à la racine du projet).
    """
    csv_path = BASE_DIR / 'capacity_requests.csv'
    header = ['timestamp', 'user_dn', 'username', 'vm_name', 'resource', 'requested_value', 'reason']
    row = [
        datetime.datetime.utcnow().isoformat(),
        user_dn,
        getattr(current_user, 'username', ''),
        vm_name,
        resource,
        value_str,
        reason.replace('\n', ' ').strip()[:2000],
    ]
    write_header = not csv_path.exists()
    with open(csv_path, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(header)
        w.writerow(row)

def _send_capacity_request_email(username: str, vm_name: str, resource: str, human_value: str, reason: str) -> bool:
    """
    Envoie un email aux admins pour une demande d’augmentation.
    Requiert dans config.py: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, ADMIN_EMAILS (liste).
    Optionnels: SMTP_USE_TLS (True par défaut), SMTP_USE_SSL (False par défaut).
    """
    smtp_host = getattr(config, 'SMTP_HOST', None)
    smtp_port = int(getattr(config, 'SMTP_PORT', 587))
    smtp_user = getattr(config, 'SMTP_USER', None)
    smtp_pass = getattr(config, 'SMTP_PASSWORD', None)
    smtp_from = getattr(config, 'SMTP_FROM', None)
    admins = getattr(config, 'ADMIN_EMAILS', [])
    use_tls = bool(getattr(config, 'SMTP_USE_TLS', True))
    use_ssl = bool(getattr(config, 'SMTP_USE_SSL', False))

    if not smtp_host or not smtp_from or not admins:
        print("Email non envoyé: configuration SMTP incomplète (voir config.py).")
        return False

    subject = f"[VM Request] {username}/{vm_name} → {resource.upper()} {human_value}"
    body = (
        f"Demande d’augmentation de capacité\n"
        f"- Utilisateur: {username}\n"
        f"- VM: {vm_name}\n"
        f"- Ressource: {resource}\n"
        f"- Valeur demandée: {human_value}\n"
        f"- Motif: {reason}\n"
        f"- Horodatage (UTC): {datetime.datetime.utcnow().isoformat()}\n"
    )

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = smtp_from
    msg['To'] = ', '.join(admins)
    msg.set_content(body)

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as s:
                if smtp_user and smtp_pass:
                    s.login(smtp_user, smtp_pass)
                s.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
                s.ehlo()
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                if smtp_user and smtp_pass:
                    s.login(smtp_user, smtp_pass)
                s.send_message(msg)
        return True
    except Exception as e:
        print(f"Erreur envoi email: {e}")
        return False

# -------------------- Nouvelle API: demande d’augmentation de capacité --------------------
@app.route('/api/request_vm_capacity', methods=['POST'])
@login_required
def request_vm_capacity():
    """
    Permet à l'utilisateur de demander par email une augmentation de RAM ou de stockage.
    JSON attendu:
      {
        "vm_name": "nomVM",
        "resource": "ram" | "storage",
        "value": "8GB" | "8192" | "80GB" | "80",
        "reason": "motif obligatoire"
      }
    """
    data = request.get_json() or {}
    vm_name = (data.get('vm_name') or '').strip()
    resource = (data.get('resource') or '').strip().lower()
    value_str = (data.get('value') or '').strip()
    reason = (data.get('reason') or '').strip()

    if not vm_name:
        return jsonify({'success': False, 'message': 'Nom de VM requis.'}), 400
    if resource not in ('ram', 'storage', 'stockage', 'disk'):
        return jsonify({'success': False, 'message': "Ressource invalide. Utilisez 'ram' ou 'storage'."}), 400
    if not value_str:
        return jsonify({'success': False, 'message': 'Valeur demandée requise.'}), 400
    if not reason or len(reason) < 5:
        return jsonify({'success': False, 'message': 'Motif requis (5 caractères minimum).'}), 400

    # Vérifier la propriété
    allowed, _vm_path = check_vm_ownership(current_user.username, vm_name)
    if not allowed:
        return jsonify({'success': False, 'message': 'VM introuvable ou accès refusé.'}), 403

    # Parsing des valeurs
    human_value = None
    if resource == 'ram':
        mb = _parse_ram_to_mb(value_str)
        if not mb:
            return jsonify({'success': False, 'message': "Valeur RAM invalide (ex: '8192' ou '8GB')."}), 400
        human_value = f"{mb} MB ({mb//1024} GB)"
        # Garde-fous simples
        if mb < 512 or mb > 131072:  # 512MB à 128GB
            return jsonify({'success': False, 'message': 'RAM demandée hors limites (512MB - 128GB).'}), 400
        normalized_resource = 'ram'
    else:
        gb = _parse_storage_to_gb(value_str)
        if not gb:
            return jsonify({'success': False, 'message': "Valeur stockage invalide (ex: '80' ou '80GB')."}), 400
        human_value = f"{gb} GB"
        if gb < 10 or gb > 1024:  # 10GB à 1TB
            return jsonify({'success': False, 'message': 'Stockage demandé hors limites (10GB - 1TB).'}), 400
        normalized_resource = 'storage'

    # Journaliser
    try:
        _append_capacity_request_log(current_user.dn, vm_name, normalized_resource, value_str, reason)
    except Exception as e:
        print(f"Erreur log demande capacité: {e}")

    # Envoyer l'email
    ok = _send_capacity_request_email(current_user.username, vm_name, normalized_resource, human_value, reason)
    if not ok:
        return jsonify({'success': False, 'message': "Votre demande a été enregistrée mais l'email n'a pas pu être envoyé (voir logs serveur)."}), 202

    return jsonify({'success': True, 'message': 'Demande envoyée aux administrateurs. Vous recevrez un retour prochainement.'}), 200

# -------------------- Vérifier et créer le réseau libvirt par défaut --------------------
def ensure_libvirt_network():
    try:
        out = subprocess.run(["virsh","net-list","--all"], capture_output=True, text=True)
        if "default" in out.stdout:
            return True
        xml = ("<network><name>default</name><forward mode='nat'/>"
               "<bridge name='virbr0'/>"
               "<ip address='192.168.122.1' netmask='255.255.255.0'>"
               "<dhcp><range start='192.168.122.2' end='192.168.122.254'/></dhcp>"
               "</ip></network>")
        tmp = "/tmp/default-net.xml"
        open(tmp, "w").write(xml)
        subprocess.run(["sudo","virsh","net-define", tmp], check=True)
        subprocess.run(["sudo","virsh","net-start", "default"], check=True)
        subprocess.run(["sudo","virsh","net-autostart", "default"], check=True)
        return True
    except Exception as e:
        print(f"[ensure_libvirt_network] {e}")
        return False

# -------------------- Lancement Flask --------------------
if __name__ == '__main__':
    # Dev server
    app.run(debug=True, host='0.0.0.0', port=5000)
