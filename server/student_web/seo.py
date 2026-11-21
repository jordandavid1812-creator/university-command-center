"""robots.txt and sitemap.xml for search engines (owner's choice).

Only public pages are listed. Everything with student data needs a login anyway, and robots.txt
also asks AI training crawlers to stay away (the Vercel firewall's AI-bot rule is the hard block).
No database access, no cookies, nothing personal.
"""
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods

AI_TRAINING_BOTS = ('GPTBot', 'ClaudeBot', 'anthropic-ai', 'Claude-Web', 'CCBot', 'Google-Extended',
                    'Applebot-Extended', 'Bytespider', 'PerplexityBot', 'meta-externalagent', 'Amazonbot')


def _origin():
    return settings.AUTH_LINK_ORIGIN.rstrip('/')


def public_pages():
    return [reverse('student_web:dashboard'), reverse('accounts:register'), reverse('accounts:login'),
            reverse('accounts:privacy'), reverse('accounts:terms')]


def _cached(response):
    response['Cache-Control'] = 'public, max-age=3600'
    return response


@require_http_methods(['GET', 'HEAD'])
def robots(request):
    lines = []
    for bot in AI_TRAINING_BOTS:
        lines += [f'User-agent: {bot}', 'Disallow: /', '']
    lines += ['User-agent: *']
    lines += ['Allow: /$'] + [f'Allow: {page}$' for page in public_pages()[1:]]
    lines += ['Allow: /static/', 'Disallow: /', '', f'Sitemap: {_origin()}{reverse("student_web:sitemap")}', '']
    return _cached(HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8'))


@require_http_methods(['GET', 'HEAD'])
def sitemap(request):
    urls = ''.join(f'<url><loc>{_origin()}{page}</loc></url>' for page in public_pages())
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    return _cached(HttpResponse(body, content_type='application/xml; charset=utf-8'))
