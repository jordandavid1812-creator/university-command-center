"""Mistake bank (owner's choice): save the quiz questions you got wrong, revise them, and practise
them as a new quiz. No AI is called: practice quizzes are built from the student's own saved quizzes.
Only pointers are stored (which saved quiz, which question); see academics.services.Mistakes."""
import random
from django.contrib import messages
from django.shortcuts import redirect, render
from academics import services
from academics.models import MAX_MISTAKES_PER_STUDENT
from . import ai_providers
from .views import error_page, protected

PRACTICE_SIZE = 20


def _question(mistake):
    """The saved question a mistake points at, re-checked like any saved result, or None if the
    quiz can no longer be shown (an unknown shape, or a question number that is no longer there)."""
    result = mistake.result
    try:
        data = ai_providers.check_result('quiz', result.result) if result.shape_version == 1 else None
    except ValueError:
        return None
    if data is None or mistake.question_index >= len(data['questions']):
        return None
    return data['questions'][mistake.question_index]


def _rows(identity):
    rows = []
    for mistake in services.mistakes.list(identity):
        item = _question(mistake)
        if item is not None:
            rows.append({'mistake': mistake, 'item': item, 'answer': item['options'][item['correct']],
                         'material': mistake.result.material, 'number': mistake.question_index + 1})
    return rows


def _indices(values):
    """Question numbers from the form (1-based, as shown), as 0-based indices; ValueError if not numbers."""
    if not values or len(values) > 60:
        raise ValueError('Choose at least one question.')
    numbers = []
    for value in values:
        if not value.isdigit() or len(value) > 2:
            raise ValueError('Not a question number.')
        numbers.append(int(value) - 1)
    return numbers


@protected(methods=('POST',))
def save(request, identity, identifier):
    """Save the questions the student marked wrong on one of their saved quizzes."""
    saved = services.ai.get_result(identity, identifier)
    if saved.tool != 'quiz':
        raise services.RecordNotFound()
    try:
        data = ai_providers.check_result('quiz', saved.result) if saved.shape_version == 1 else None
    except ValueError:
        data = None
    if data is None:
        return error_page(request, 'Result unavailable', 'This quiz can no longer be displayed.', 410)
    try:
        indices = _indices(request.POST.getlist('question'))
    except ValueError:
        messages.error(request, 'Tick at least one question you got wrong, then save.')
        return redirect('student_web:ai-result', saved.pk)
    try:
        added = services.mistakes.add(identity, saved.pk, indices, len(data['questions']))
    except services.MistakeLimit as limit:
        messages.error(request, f'{limit} Remove some you now know, then try again.')
        return redirect('student_web:ai-result', saved.pk)
    if added:
        messages.success(request, f'Saved {added} question{"s" if added != 1 else ""} to your Mistake bank.')
    else:
        messages.info(request, 'Those questions are already in your Mistake bank.')
    return redirect('student_web:mistakes')


@protected()
def bank(request, identity):
    rows = _rows(identity)
    return render(request, 'student_web/mistakes.html', {'rows': rows, 'limit': MAX_MISTAKES_PER_STUDENT,
                                                          'practice_size': min(len(rows), PRACTICE_SIZE)})


@protected()
def practice(request, identity):
    """An interactive quiz of up to 20 of the student's saved mistakes, in a random order. Nothing is
    sent to an AI service and nothing is saved."""
    rows = _rows(identity)
    if not rows:
        messages.info(request, 'Your Mistake bank is empty. Save the questions you get wrong after a quiz.')
        return redirect('student_web:mistakes')
    chosen = random.sample(rows, min(len(rows), PRACTICE_SIZE))  # nosec B311: question order only
    return render(request, 'student_web/mistakes_practice.html', {'rows': chosen, 'total': len(rows)})


@protected(methods=('POST',))
def remove(request, identity, identifier):
    services.mistakes.remove(identity, identifier)
    messages.success(request, 'Removed from your Mistake bank.')
    return redirect('student_web:mistakes')


@protected(methods=('POST',))
def clear(request, identity):
    if request.POST.get('confirm') != 'yes':
        messages.error(request, 'Tick the box to confirm, then press "Empty my Mistake bank".')
        return redirect('student_web:mistakes')
    removed = services.mistakes.clear(identity)
    messages.success(request, f'Your Mistake bank is empty ({removed} removed).')
    return redirect('student_web:mistakes')
