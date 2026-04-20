from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-gdp^^*e2%+n&zle5_3#(e-w5zorxo+-a2+_4e*yzva^re8-xjc"
)

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    ".onrender.com",
    "hotel-erp-20.onrender.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://*.onrender.com",
    "https://hotel-erp-20.onrender.com",
    "http://localhost:8000",
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

# Still needed for django_tenants DB backend
TENANT_MODEL = "customers.Client"
TENANT_DOMAIN_MODEL = "customers.Domain"

MIDDLEWARE = [
    'customers.middleware.PathTenantMiddleware',  # our custom middleware
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
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

DATABASES = {
    'default': dj_database_url.config(
        default='postgresql://postgres:vishnu123@localhost:5432/hoterp',
        conn_max_age=600,
    )
}
DATABASES['default']['ENGINE'] = 'django_tenants.postgresql_backend'

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

IS_RENDER = os.environ.get('RENDER', False)
BASE_URL = "hotel-erp-20.onrender.com" if IS_RENDER else "localhost:8000"
PROTOCOL = "https" if IS_RENDER else "http"
PORT = ""

DEFAULT_FROM_EMAIL = 'msvishnu673@gmail.com'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'msvishnu673@gmail.com'
EMAIL_HOST_PASSWORD = 'sjcf tyva aldr ashi'