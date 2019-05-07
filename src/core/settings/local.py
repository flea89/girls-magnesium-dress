# flake8: noqa
from core.settings.default import *
import os


INSTALLED_APPS = tuple(list(INSTALLED_APPS) + [
    'debug_toolbar',
])

MIDDLEWARE_CLASSES = tuple(list(MIDDLEWARE_CLASSES) + [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'angular.middleware.EnsureAngularProtectionMiddleware',
])

INTERNAL_IPS = [
    '127.0.0.1',
    '::1'
]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# This is just to allow the inline styles on Django error pages when DEBUG = True
# this settings file won't be used on production only during local development
CSP_STYLE_SRC += ("localhost:8000",)

# Enable this for Hot Module Replacement on development only
CSP_SCRIPT_SRC = CSP_SCRIPT_SRC + ("'unsafe-eval'", "localhost:8000",)
CSP_CONNECT_SRC = CSP_CONNECT_SRC + ("localhost:8000", "ws://localhost:8000")

CHROMEDRIVER_PATH = os.path.join(NODE_PREFIX, "node_modules", ".bin", "chromedriver")
JASMINE_NODE_PATH = os.path.join(NODE_PREFIX, "node_modules", "jasmine-node", "lib", "jasmine-node", "cli.js")
BABEL_NODE_PATH = os.path.join(NODE_PREFIX, "node_modules", ".bin", "babel-node")

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

ALLOWED_HOSTS = [
    '*',
]


CSP_CONNECT_SRC += ("ws://127.0.0.1:35729/livereload",)
CSP_SCRIPT_SRC += (
    "http://127.0.0.1:35729/livereload.js",
    "http://ajax.googleapis.com/ajax/libs/jquery/2.1.4/jquery.min.js",
    "'unsafe-inline'",  # we need this because of Google Closure Library.
)
PROJ_BASE = os.path.join(BASE_DIR, "..")

SHARE_LOCAL_EXPORT = [
    "marco.azzalin@potatolondon.com",
]
