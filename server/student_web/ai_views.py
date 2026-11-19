"""AI study assistant pages (stage 3b). See docs/AI_STUDY_ASSISTANT.md.

Only `send` can call a provider, and only after the confirm page's POST with a valid
consent token. The call runs with no database transaction open. Every other page only
reads or deletes the student's own records.
"""
import logging
from django.conf import settings as django_settings
from django.contrib import messages
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from academics import services
from academics.ownership import OwnershipRequired
from academics.services import AiLimitReached, AiRequestClosed
from . import ai_consent, ai_providers, forms, text_extraction
from .views import error_page, protected

TOOL_NAMES = dict(forms.AI_TOOL_CHOICES)
AI_NOTES_COOKIE = 'ucc_ai_notes'  # 'hidden' after "Got it, don't show again"; nothing else is stored
LIMIT_MESSAGES = {
    "daily": "You have used all 50 AI requests for today. The count starts again at midnight (Lagos time).",
    "results": "You have 500 saved AI results, the most you can keep. Delete some results to make room.",
    "busy": "Another AI request of yours is still in progress. Wait for it to finish, then try again.",
    "site": "The AI tools have reached today's limit for the whole site. They open again at midnight (Lagos time).",
}
FAILURE_MESSAGES = {
    "network": "The request to the AI service could not be completed (for example no internet connection, or an "
               "unexpected problem in this app). Nothing was saved; you can try again.",
    "timeout": "The AI service did not answer within 60 seconds, so we stopped waiting and nothing was saved. "
               "This is usually a busy moment at the service or a slow connection. Please try again in a minute.",
    "redirect": "The AI service answered in an unexpected way (a redirect), so nothing was used.",
    "http_error": "The AI service refused the request. If this keeps happening, check the API key and model name.",
    "too_large": "The AI service sent back far too much, so the answer was not used.",
    "invalid_response": "The AI's answer was not in the expected format, so it was not saved.",
    "blocked": "The AI service declined to answer this request.",
    "truncated": "The AI's answer was cut off before it finished, so it was not saved.",
    "save": "The answer arrived but could not be saved.",
}


STATUS_HINTS = {
    "4xx": "The service rejected the request itself (a 4xx reply). This usually means the API key or model name "
           "is wrong, or the account has no quota left.",
    "5xx": "The service had a problem on its side (a 5xx reply). Try again later.",
}


# (tool, name, mark, description, button) for the tools page cards.
QUICK_TOOLS = [
    ("summary", "Summary", "S", "The key points of this file in up to 10 short bullets.", "Create summary"),
    ("quiz", "Quiz", "Q", "5 to 10 multiple-choice questions with instant feedback and a score.", "Create quiz"),
    ("flashcards", "Flashcards", "F", "5 to 20 flip cards with piles for what you know and what to review.",
     "Create flashcards"),
]


def _material_with_text(identity, identifier, tool='', question=''):
    """The student's stored material and the text that would be sent. For "Ask a question" only
    the parts that best match the question are sent (the same on the confirm page and at send)."""
    material, content = services.materials.read_file(identity, identifier)
    extracted = text_extraction.extract_text_remembered(material.file_type, content)
    if tool == 'answer':
        extracted = text_extraction.focus_on_question(extracted, question)
    return material, extracted


def _tools_context(identity, material, form):
    results = [{'saved': saved, 'tool_name': TOOL_NAMES[saved.tool]}
               for saved in services.ai.results_for(identity, material.pk)]
    return {'material': material, 'form': form, 'results': results, 'usage': services.ai.usage(identity),
            'providers': ai_providers.available_providers(), 'quick_tools': QUICK_TOOLS}


@protected()
def tools(request, identity, identifier):
    material = services.materials.retrieve(identity, identifier)
    if material.pk not in services.materials.stored_ids(identity):
        return error_page(request, 'File not stored', 'This material has no stored file. Upload it again to use '
                          'the study tools.', 404)
    return render(request, 'student_web/ai_tools.html',
                  _tools_context(identity, material, forms.AiToolForm(initial={'tool': 'summary'})))


@protected(('POST',))
def confirm(request, identity, identifier):
    """Show exactly what would be sent. Never sends and never counts."""
    form = forms.AiToolForm(request.POST)
    material = services.materials.retrieve(identity, identifier)
    if not form.is_valid():
        if material.pk not in services.materials.stored_ids(identity):
            raise services.RecordNotFound()
        return render(request, 'student_web/ai_tools.html', _tools_context(identity, material, form), status=400)
    # "Got it, don't show again" is remembered in this browser only (like the Display setting),
    # even if the file cannot be read this time.
    choice = form.cleaned_data.get('notes')
    try:
        material, extracted = _material_with_text(identity, identifier, form.cleaned_data['tool'],
                                                  form.cleaned_data['question'])
    except text_extraction.ExtractionFailed as failure:
        return _remember_notes(error_page(request, 'Cannot use this file', failure.message,
                                          503 if failure.reason == 'busy' else 422), choice)
    tool, question = form.cleaned_data['tool'], form.cleaned_data['question']
    token = ai_consent.issue(request.user.pk, material.pk, tool, question, extracted.characters)
    providers = ai_providers.available_providers()
    send_form = forms.AiSendForm(initial={'tool': tool, 'question': question, 'token': token}, providers=providers,
                                 auto_id=False)
    notes_hidden = choice == 'hide' or (choice != 'show' and request.COOKIES.get(AI_NOTES_COOKIE) == 'hidden')
    response = render(request, 'student_web/ai_confirm.html', {
        'material': material, 'tool': tool, 'tool_name': TOOL_NAMES[tool], 'question': question,
        'amount': text_extraction.describe(extracted), 'send_form': send_form,
        'providers': ai_providers.send_buttons(providers),
        'usage': services.ai.usage(identity), 'notes_hidden': notes_hidden})
    return _remember_notes(response, choice)


def _remember_notes(response, choice):
    """Store or clear the "Got it, don't show again" choice on this response."""
    if choice == 'hide':
        response.set_cookie(AI_NOTES_COOKIE, 'hidden', max_age=365 * 24 * 60 * 60, httponly=True, samesite='Lax',
                            secure=django_settings.SESSION_COOKIE_SECURE)
    elif choice == 'show':
        response.delete_cookie(AI_NOTES_COOKIE, samesite='Lax')
    return response


@protected(('POST',))
def send(request, identity, identifier):
    """The only route that can call a provider. Always ends in a redirect."""
    form = forms.AiSendForm(request.POST, providers=list(ai_providers.HOSTS))
    if not form.is_valid():
        return error_page(request, 'Request not sent', 'This request was incomplete, so nothing was sent. Start '
                          'again from the study tools.', 400)
    data = form.cleaned_data
    material = services.materials.retrieve(identity, identifier)
    try:
        token_hash, characters = ai_consent.check(data['token'], request.user.pk, material.pk, data['tool'],
                                                  data['question'])
    except ai_consent.ConsentInvalid:
        return error_page(request, 'Request not sent', 'This confirmation is not valid for this file, so nothing '
                          'was sent. Start again from the study tools.', 400)
    # 0. A request already made with this token (a refresh or double click): show it, send nothing.
    existing = services.ai.find_request(identity, token_hash)
    if existing is not None:
        return redirect('student_web:ai-request', existing.pk)
    try:
        ai_consent.check_fresh(data['token'])
    except ai_consent.ConsentExpired:
        return error_page(request, 'Confirmation expired', 'Confirmations last 10 minutes. Nothing was sent; '
                          'start again from the study tools.', 400)
    if data['provider'] not in ai_providers.available_providers():
        return error_page(request, 'Request not sent', 'That AI service is not set up, so nothing was sent.', 400)
    # 1. Read and extract again. A bad file stops here: nothing sent, nothing counted.
    try:
        material, extracted = _material_with_text(identity, identifier, data['tool'], data['question'])
    except text_extraction.ExtractionFailed as failure:
        return error_page(request, 'Cannot use this file', failure.message, 503 if failure.reason == 'busy' else 422)
    if extracted.characters != characters:
        return error_page(request, 'Request not sent', 'The text no longer matches what you confirmed, so nothing '
                          'was sent. Start again from the study tools.', 409)
    # 2. Reserve under the per-student lock (its own short transactions).
    _, model = ai_providers.configured(data['provider'])
    try:
        ledger, created = services.ai.reserve(identity, tool=data['tool'], provider=data['provider'], model=model,
                                              characters_sent=extracted.characters,
                                              truncated=extracted.truncated or extracted.picked_from is not None,
                                              consent_token_hash=token_hash)
    except AiLimitReached as refused:
        message = LIMIT_MESSAGES[refused.reason]
        if refused.reason == "daily" and getattr(django_settings, "UCC_AI_REQUESTS_PER_DAY", None):
            message = (f"You have used all {django_settings.UCC_AI_REQUESTS_PER_DAY} AI requests for today. "
                       "The count starts again at midnight (Lagos time).")
        return error_page(request, 'Request not sent', message, 429)
    if not created:
        return redirect('student_web:ai-request', ledger.pk)
    # 3. Call the provider with no database transaction open. From here on every outcome is
    #    recorded on the ledger row and the response is a redirect to it.
    try:
        result = ai_providers.ask(data['provider'], data['tool'], extracted.text, data['question'])
    except ai_providers.ProviderError as failure:
        _close_failed(request, identity, ledger.pk, failure.category, failure.status_class or '')
        return redirect('student_web:ai-request', ledger.pk)
    except Exception:  # an unexpected client error: never retried, counted as a network failure
        _close_failed(request, identity, ledger.pk, 'network')
        return redirect('student_web:ai-request', ledger.pk)
    # 4. Save in a new short transaction, only while the request is still in progress.
    try:
        services.ai.succeed(identity, ledger.pk, material_id=material.pk, result=result, question=data['question'],
                            shape_version=ai_providers.SHAPE_VERSION)
    except AiRequestClosed:
        pass  # already marked interrupted: the late answer is discarded
    except (services.InvalidRecord, services.RecordNotFound, DatabaseError):
        _close_failed(request, identity, ledger.pk, 'save')
    return redirect('student_web:ai-request', ledger.pk)


def _close_failed(request, identity, request_id, category, status_class=''):
    """Record a failure. If even that fails (database down, session ended), the row stays
    'sent' and is shown as interrupted after two minutes; it is never retried."""
    # Fixed-label log line (route and level only): details live on the ledger row.
    logging.getLogger('student_web.ai').warning('AI request failed', extra={'request': request})
    try:
        services.ai.fail(identity, request_id, category, status_class)
    except (AiRequestClosed, DatabaseError, OwnershipRequired):
        pass


def _effective_status(ledger):
    if ledger.status == 'sent' and ledger.created_at < timezone.now() - services.AI_STALE_AFTER:
        return 'interrupted'
    return ledger.status


@protected()
def request_status(request, identity, identifier):
    ledger = services.ai.get_request(identity, identifier)
    status = _effective_status(ledger)
    if status == 'succeeded':
        saved = services.ai.result_for_request(identity, ledger.pk)
        if saved is not None:
            return redirect('student_web:ai-result', saved.pk)
        status = 'deleted'
    return render(request, 'student_web/ai_request.html', {
        'ledger': ledger, 'status': status, 'tool_name': TOOL_NAMES[ledger.tool],
        'failure': FAILURE_MESSAGES.get(ledger.error_category, ''),
        'status_hint': STATUS_HINTS.get(ledger.status_class, '')}, status=200)


def _checked(saved):
    try:
        return ai_providers.check_result(saved.tool, saved.result) if saved.shape_version == 1 else None
    except ValueError:
        return None


@protected()
def result(request, identity, identifier):
    saved = services.ai.get_result(identity, identifier)
    material = services.materials.retrieve(identity, saved.material_id)
    data = _checked(saved)
    return render(request, 'student_web/ai_result.html', {
        'saved': saved, 'material': material, 'tool_name': TOOL_NAMES[saved.tool], 'data': data,
        'text': result_as_text(saved, material, data) if data is not None else ''})


def result_as_text(saved, material, data):
    lines = [f"{TOOL_NAMES[saved.tool]}: {material.title}", "AI-generated: check it against your notes.", ""]
    if saved.question:
        lines += [f"Question: {saved.question}", ""]
    if saved.tool == 'summary':
        lines += [f"- {point}" for point in data['points']]
    elif saved.tool == 'quiz':
        for number, item in enumerate(data['questions'], 1):
            lines.append(f"{number}. {item['question']}")
            lines += [f"   {'ABCD'[index]}. {option}" for index, option in enumerate(item['options'])]
            lines += [f"   Answer: {'ABCD'[item['correct']]}. {item['reason']}", ""]
    elif saved.tool == 'flashcards':
        for number, card in enumerate(data['cards'], 1):
            lines += [f"{number}. {card['front']}", f"   {card['back']}", ""]
    else:
        lines.append(data['answer'])
        if data['not_covered']:
            lines.append("(The file does not cover this question.)")
    return "\n".join(lines).rstrip() + "\n"


@protected()
def result_download(request, identity, identifier):
    saved = services.ai.get_result(identity, identifier)
    material = services.materials.retrieve(identity, saved.material_id)
    data = _checked(saved)
    if data is None:
        return error_page(request, 'Result unavailable', 'This result can no longer be displayed.', 410)
    response = HttpResponse(result_as_text(saved, material, data), content_type='text/plain; charset=utf-8')
    name = f"{saved.tool}-{timezone.localtime(saved.created_at):%Y-%m-%d}.txt"
    response['Content-Disposition'] = content_disposition_header(True, name)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return response


@protected(('GET', 'POST'))
def result_delete(request, identity, identifier):
    saved = services.ai.get_result(identity, identifier)
    material = services.materials.retrieve(identity, saved.material_id)
    form = forms.ConfirmDeleteForm(request.POST if request.method == 'POST' else None)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            services.ai.delete_result(identity, saved.pk)
            messages.success(request, 'Result deleted. It still counts towards today\'s requests.')
            return redirect('student_web:ai-tools', material.pk)
        status = 400
    return render(request, 'student_web/ai_delete.html', {
        'form': form, 'saved': saved, 'material': material, 'tool_name': TOOL_NAMES[saved.tool],
        'cancel_url': reverse('student_web:ai-result', args=[saved.pk])}, status=status)
