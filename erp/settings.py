"""
Django settings for erp project.
"""

from pathlib import Path
import os
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-fallback-only-for-local-dev")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "False") == "True"

IS_RENDER = os.environ.get("RENDER") is not None
BASE_URL = os.environ.get("BASE_URL", "localhost")
PORT = "" if IS_RENDER else ":8000"

ALLOWED_HOSTS = [
    "localhost",
    ".localhost",
    "127.0.0.1",
    "hotel-erp-21.onrender.com",
    ".hotel-erp-21.onrender.com",   # allows tenant subdomains on Render
    ".onrender.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://hotel-erp-20.onrender.com",
    "https://*.hotel-erp-20.onrender.com",  # tenant subdomains
    "https://*.onrender.com",
]


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
    'housekeeping',
)

INSTALLED_APPS = SHARED_APPS + TENANT_APPS
TENANT_MODEL = "customers.Client"
TENANT_DOMAIN_MODEL = "customers.Domain"

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',
    'django.middleware.security.SecurityMiddleware',
    
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

AUTH_USER_MODEL = 'accounts.User'

ROOT_URLCONF = 'erp.urls'
PUBLIC_SCHEMA_URLCONF = 'erp.urls'

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


# Database
DATABASES = {
    'default': dj_database_url.config(
        default='postgresql://postgres:vishnu123@localhost:5432/hoterp',
        conn_max_age=600,
        ssl_require=IS_RENDER,   # enforce SSL on Render
    )
}

DATABASES['default']['ENGINE'] = 'django_tenants.postgresql_backend'

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')



STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'msvishnu673@gmail.com'
EMAIL_HOST_PASSWORD = 'sjcf tyva aldr ashi'