import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-me')
LDAP_HOST = os.getenv('LDAP_HOST', 'ldap://localhost')
LDAP_BASE_DN = os.getenv('LDAP_BASE_DN', 'dc=example,dc=com')
LDAP_USER_DN = os.getenv('LDAP_USER_DN', 'ou=users')
LDAP_GROUP_DN = os.getenv('LDAP_GROUP_DN', 'ou=groups')
LDAP_USER_RDN_ATTR = 'uid'
LDAP_USER_LOGIN_ATTR = 'uid'
LDAP_BIND_USER_DN = os.getenv('LDAP_BIND_USER_DN', '')
LDAP_BIND_USER_PASSWORD = os.getenv('LDAP_BIND_USER_PASSWORD', '')

SMTP_HOST = "smtp.example.com"
SMTP_PORT = 587          # 587 (STARTTLS) ou 465 (SSL)
SMTP_USER = "no-reply@example.com"
SMTP_PASSWORD = "motdepasse"
SMTP_FROM = "no-reply@example.com"
SMTP_USE_TLS = True      # True pour STARTTLS
SMTP_USE_SSL = False     # True si vous utilisez le port 465
ADMIN_EMAILS = ["admin@example.com"]  # destinataires des demandes