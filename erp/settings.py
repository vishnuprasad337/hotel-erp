from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


# ========================
# SECURITY
# ========================

SECRET_KEY = os.environ.get("SECRET_KEY")

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    ".onrender.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://*.onrender.com",
]


# ========================
# TENANT CONFIG
# ========================

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
    'billing',
)

INSTALLED_APPS = SHARED_APPS + TENANT_APPS

TENANT_MODEL = "customers.Client"
TENANT_DOMAIN_MODEL = "customers.Domain"
DEBUG=True
DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)


# ========================
# MIDDLEWARE
# ========================

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',

    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',

    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',

    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ========================
# AUTH
# ========================

AUTH_USER_MODEL = 'accounts.User'


# ========================
# URLS / WSGI
# ========================

ROOT_URLCONF = 'erp.urls'
PUBLIC_SCHEMA_URLCONF = 'erp.urls'

WSGI_APPLICATION = 'erp.wsgi.application'


# ========================
# TEMPLATES
# ========================

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


# ========================
# DATABASE (POSTGRESQL)
# ========================

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get("DATABASE_URL")
    )
}

DATABASES['default']['ENGINE'] = 'django_tenants.postgresql_backend'


# ========================
# STATIC FILES (RENDER)
# ========================

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# WhiteNoise compression
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# ========================
# EMAIL (SECURE)
# ========================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")


# ========================
# INTERNATIONALIZATION
# ========================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True
USE_TZ = True


# ========================
# DEFAULT AUTO FIELD
# ========================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'