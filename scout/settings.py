from pathlib import Path
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_q',
    'core',
    'dashboard',
    'runs',
    'suites',
    'items',
    'reviews',
    'assessments',
    'environments',
    'test_cases',
    'builder',
    'admin_config',
    'baselines',
    'test_data',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'scout.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.nav_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'scout.wsgi.application'

# Database
_database_url = config('DATABASE_URL', default='postgresql://scout:scout@localhost:5432/scout')
DATABASES = {
    'default': dj_database_url.parse(_database_url, conn_max_age=600)
}

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
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# SCOUT-specific settings
PLAYWRIGHT_TESTS_DIR = config('PLAYWRIGHT_TESTS_DIR', default=str(BASE_DIR.parent / 'ETS/SCOUT/poc/tests'))
PLAYWRIGHT_PROJECT_ROOT = config('PLAYWRIGHT_PROJECT_ROOT', default=str(BASE_DIR.parent / 'ETS/SCOUT/poc'))
SCOUT_SCRIPT_TIMEOUT = config('SCOUT_SCRIPT_TIMEOUT', default=180000, cast=int)
SCOUT_MOCK = config('SCOUT_MOCK', default='0')
DASHBOARD_AUTH = config('DASHBOARD_AUTH', default=True, cast=bool)

AI_PROVIDER = config('AI_PROVIDER', default='mock')
MOCK_AI_MODE = config('MOCK_AI_MODE', default='clean')

AZURE_ENDPOINT = config('AZURE_AI_ENDPOINT', default='')
AZURE_API_KEY = config('AZURE_AI_API_KEY', default='')
AZURE_TEXT_DEPLOYMENT = config('AZURE_AI_TEXT_DEPLOYMENT', default='gpt-4o')
AZURE_VISION_DEPLOYMENT = config('AZURE_AI_VISION_DEPLOYMENT', default='gpt-4o')
AZURE_API_VERSION = config('AZURE_AI_API_VERSION', default='2024-02-01')

CSRF_TRUSTED_ORIGINS = [o for o in config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv()) if o]

OLLAMA_HOST = config('OLLAMA_HOST', default='localhost:11434')
OLLAMA_TEXT_MODEL = config('OLLAMA_TEXT_MODEL', default='qwen2.5:14b')
OLLAMA_VISION_MODEL = config('OLLAMA_VISION_MODEL', default='gemma3:12b')

# django-q2 cluster config
Q_CLUSTER = {
    'name': 'scout',
    'workers': 2,
    'timeout': 300,
    'retry': 360,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
}
