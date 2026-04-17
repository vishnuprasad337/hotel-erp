"""
Django settings for erp project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-gdp^^*e2%+n&zle5_3#(e-w5zorxo+-a2+_4e*yzva^re8-xjc'

DEBUG = True

ALLOWED_HOSTS = ['*']


# ─────────────────────────────────────────────
#  Apps
# ─────────────────────────────────────────────

SHARED_APPS = (
    'django_tenants',
    'customers',
    'accounts',

    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
)

TENANT_APPS = (
    'hotel',
    'pms',
)

INSTALLED_APPS = SHARED_APPS + TENANT_APPS

TENANT_MODEL = "customers.Client"
TENANT_DOMAIN_MODEL = "customers.Domain"


# ─────────────────────────────────────────────
#  Middleware
#
#  FIX: TenantSecurityMiddleware was defined in accounts/middleware.py but was
#  never added here, so it never ran and the tenant mismatch was never caught.
#  It must come AFTER AuthenticationMiddleware so request.user is populated.
# ─────────────────────────────────────────────

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',   

    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',

    
    'accounts.middleware.TenantSecurityMiddleware',
]

AUTH_USER_MODEL = 'accounts.User'

ROOT_URLCONF = 'erp.urls'

# ─────────────────────────────────────────────
#  
# ─────────────────────────────────────────────
PUBLIC_SCHEMA_URLCONF = 'erp.urls'


# ─────────────────────────────────────────────
#  Templates
# ─────────────────────────────────────────────

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'erp.wsgi.application'


# ─────────────────────────────────────────────
#  Database
# ─────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': 'hoterp',
        'USER': 'postgres',
        'PASSWORD': 'vishnu123',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)


# ─────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]





# ─────────────────────────────────────────────
#  Static & Media
# ─────────────────────────────────────────────

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# ─────────────────────────────────────────────
#  Email
# ─────────────────────────────────────────────

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'msvishnu673@gmail.com'
EMAIL_HOST_PASSWORD = 'sjcf tyva aldr ashi'