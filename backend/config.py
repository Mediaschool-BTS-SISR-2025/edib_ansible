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