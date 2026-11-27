"""Long-lived caching for style sheets, scripts and icons on Vercel (owner's choice, for speed).

Every static URL gets a version stamp (?v=<deployment>) taken from Vercel's own deployment
variables. A new deployment changes the stamp, so browsers and Vercel's network can keep these
files for a year and still fetch the new design after every update. With no stamp available
(local or test runs), nothing changes: the 60-second default stays.
"""
import os
import re

from django.contrib.staticfiles.storage import StaticFilesStorage

YEAR = 31_536_000
_STAMP = re.compile(r'[A-Za-z0-9_-]{6,64}')


def deployment_stamp(environ=None):
    environ = os.environ if environ is None else environ
    for name in ('VERCEL_GIT_COMMIT_SHA', 'VERCEL_DEPLOYMENT_ID'):
        value = (environ.get(name) or '').strip()
        if _STAMP.fullmatch(value):
            return value[:12]
    return ''


class VersionedStaticFilesStorage(StaticFilesStorage):
    """StaticFilesStorage whose URLs carry the deployment stamp (WhiteNoise ignores the query)."""

    def url(self, name):
        url = super().url(name)
        stamp = deployment_stamp()
        return f'{url}?v={stamp}' if stamp else url


def add_cache_headers(headers, path, url):
    """WhiteNoise hook: versioned files may be kept by browsers and Vercel's CDN for a year."""
    if deployment_stamp():
        headers['Cache-Control'] = f'public, max-age={YEAR}, s-maxage={YEAR}, immutable'
