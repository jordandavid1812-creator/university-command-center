"""One welcome email after a student confirms their email (owner's choice: help new students get
started, with an eye-catching design). Public profiles only (UCC_WELCOME_EMAIL). Sent once, after
the confirming transaction commits; a delivery failure never affects sign-up. Generic logs only:
never the address or the message. No images, tracking pixels or external files in the email."""
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

SUBJECT = "🎉 You're in! Welcome to UniCommand"


def body(site_url):
    return ("You're in! Welcome to UniCommand 🎉\n"
            "Your study command centre: grades, deadlines and smart revision, all in one place.\n\n"
            "WHAT YOU JUST UNLOCKED\n"
            "📊 GPA & CGPA, instantly (5- or 4-point scale)\n"
            "🎯 Your road to First Class: the exact grade to aim for in every course\n"
            "🧠 AI quizzes, summaries and flashcards from YOUR notes\n"
            "🔥 Study streaks and a Mistake bank for the questions you got wrong\n\n"
            "GET SET UP IN 3 MINUTES\n"
            "1. Add your courses: your semester, courses and any grades you have. Your GPA appears straight away.\n"
            "2. Upload one lecture note (PDF or text) and turn it into a quiz in seconds.\n"
            "3. Set your target: open the Target CGPA Planner to see the grades you need.\n\n"
            f"🚀 Open your dashboard: {site_url}\n\n"
            "💡 Pro tip: after each quiz, save the ones you got wrong to your Mistake bank, then practise "
            "them before exams. Your dashboard's \"Get started\" checklist guides you too.\n\n"
            "Free for students. Your records stay private: only you can see them.\n"
            "You're getting this one-time email because an account was just confirmed with this address.")


def html(site_url):
    try:
        return render_to_string('accounts/email/welcome.html', {'site_url': site_url})
    except Exception:
        logging.getLogger(__name__).warning('Welcome email design unavailable; sending plain text.')
        return None


def deliver(email):
    if getattr(settings, 'UCC_WELCOME_EMAIL', False) is not True:
        return
    try:
        site_url = settings.AUTH_LINK_ORIGIN.rstrip('/') + '/'
        send_mail(SUBJECT, body(site_url), settings.DEFAULT_FROM_EMAIL, [email], html_message=html(site_url))
    except Exception:
        logging.getLogger(__name__).warning('Welcome email delivery failed; the account is unaffected.')
