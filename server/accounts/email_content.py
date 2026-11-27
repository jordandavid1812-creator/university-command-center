"""Optional email presentation; sending and authentication policy stay with callers."""
import logging
from urllib.parse import urlsplit

from django.template.loader import render_to_string


def branded_html(body, *, code=None, action_url=None):
    """Render a self-contained alternative, retaining plain text if presentation fails.

    Callers supply generated codes and existing account links, never template names or
    markup from a request. No delivery, tracking, logging of payloads or network I/O here.
    """
    try:
        safe_url = None
        if isinstance(action_url, str) and not any(ord(c) <= 32 or ord(c) == 127 for c in action_url):
            parsed = urlsplit(action_url)
            if parsed.scheme in ('https', 'http') and parsed.netloc:
                safe_url = action_url
        return render_to_string('accounts/email/message.html', {
            'body': body, 'code': code, 'action_url': safe_url,
        })
    except Exception:
        # Cosmetic failure must not suppress an otherwise valid account email.
        # Never log the exception, message body, URL, code or recipient.
        try:
            logging.getLogger('accounts').warning('Account email formatting unavailable; using plain text.')
        except Exception:
            # An unavailable diagnostic sink must not suppress the plain alternative.
            pass
        return None
