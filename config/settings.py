"""
Configuración del sistema de abarrotes.
Todo lo sensible viene de variables de entorno (ver .env.example). Nada de secretos en el código.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"


def env(nombre, default=None):
    return os.environ.get(nombre, default)


def env_bool(nombre, default=False):
    return str(env(nombre, str(default))).strip().lower() in ("1", "true", "yes", "si", "sí")


def env_lista(nombre):
    return [x.strip() for x in env(nombre, "").split(",") if x.strip()]


# --------------------------------------------------------------------------- núcleo
DEBUG = env_bool("DJANGO_DEBUG", False)  # seguro por defecto: False
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "solo-desarrollo-" + "x" * 50
    else:
        raise ImproperlyConfigured("Falta la variable DJANGO_SECRET_KEY.")

ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS") or ["*"]
# Garantizar acceso desde Vercel y localhost
for h in ["*", ".vercel.app", "viveres-stalin-back.vercel.app", "localhost", "127.0.0.1"]:
    if h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(h)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "apps.core",
    "apps.usuarios",
    "apps.catalogo",
    "apps.inventario",
    "apps.clientes",
    "apps.caja",
    "apps.ventas",
    "apps.pedidos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "usuarios.Usuario"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

# --------------------------------------------------------------------------- base de datos (Supabase = PostgreSQL)
_db_url = env("DATABASE_URL")
if _db_url:
    _pooler = env_bool("DB_POOLER_TRANSACCION", False)  # puerto 6543 de Supabase (pgbouncer)
    DATABASES = {"default": dj_database_url.parse(
        _db_url,
        conn_max_age=0 if _pooler else int(env("DB_CONN_MAX_AGE", "60")),
        ssl_require=not DEBUG,  # TLS obligatorio fuera de desarrollo
    )}
    if _pooler:
        DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
elif DEBUG or TESTING:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    raise ImproperlyConfigured("Falta DATABASE_URL (cadena de conexión de Supabase).")
# Cada petición HTTP es una transacción: o se guarda todo o no se guarda nada.
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# --------------------------------------------------------------------------- caché (límites de peticiones)
if env("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("REDIS_URL")}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --------------------------------------------------------------------------- contraseñas
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------- API
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],  # todo cerrado por defecto
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min", "user": "600/min",
        "login": "5/min", "registro": "5/hour", "pedidos": "30/hour",
    },
}
if TESTING:
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {k: "100000/min" for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),    # sesión extendida (30 días de inactividad)
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

CORS_ALLOWED_ORIGINS = env_lista("CORS_ALLOWED_ORIGINS")  # lista blanca explícita
CORS_ALLOW_CREDENTIALS = False
CSRF_TRUSTED_ORIGINS = env_lista("CSRF_TRUSTED_ORIGINS")

# --------------------------------------------------------------------------- archivos: imágenes en Supabase Storage (S3 compatible)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

_estaticos = {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}
if env("SUPABASE_S3_BUCKET"):
    _default = {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {
        "bucket_name": env("SUPABASE_S3_BUCKET"),
        "endpoint_url": env("SUPABASE_S3_ENDPOINT"),   # https://<ref>.supabase.co/storage/v1/s3
        "access_key": env("SUPABASE_S3_ACCESS_KEY"),
        "secret_key": env("SUPABASE_S3_SECRET_KEY"),
        "region_name": env("SUPABASE_S3_REGION", "us-east-1"),
        "signature_version": "s3v4",
        "addressing_style": "path",
        "querystring_auth": True,       # bucket PRIVADO: URLs firmadas que caducan
        "querystring_expire": 3600,
        "file_overwrite": False,
        "default_acl": None,
    }}
else:
    _default = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
STORAGES = {"default": _default, "staticfiles": _estaticos}

# --------------------------------------------------------------------------- regional
LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- reglas del negocio
# True: en mostrador nunca se bloquea una venta por stock desactualizado (queda registrado y se corrige con un ajuste).
STOCK_NEGATIVO_PERMITIDO = env_bool("STOCK_NEGATIVO_PERMITIDO", True)
ADMIN_URL = env("ADMIN_URL", "gestion-interna/")  # no usar /admin/

# --------------------------------------------------------------------------- endurecimiento HTTP
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# --------------------------------------------------------------------------- email
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Abarrotes POS <noreply@abarrotes.local>")
