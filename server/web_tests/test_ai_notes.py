"""'Before you send' notes: shown in full until the student presses "Got it, don't show again".

The choice is a browser cookie only (like the Display setting). It never changes what is sent,
never sends anything, never counts towards the daily limit, and the full notes stay one click away.
"""
from .test_ai_pages import AiCase

FULL = '<section class="notice warning ai-warning"'
SHORT = '<section class="ai-notes-short"'


class AiNotesTests(AiCase):
    def post(self, notes, tool='summary', question=''):
        return self.client_a.post(self.url('ai-confirm'), {'tool': tool, 'question': question, 'notes': notes})

    def test_full_notes_until_got_it_then_a_short_line_with_details(self):
        first = self.confirm()
        self.assertContains(first, FULL)
        self.assertContains(first, 'Got it, don&#x27;t show again')
        self.assertNotContains(first, SHORT)
        got_it = self.post('hide', 'answer', 'What do mitochondria do?')
        self.assertEqual(got_it.status_code, 200)
        self.assertEqual(got_it.cookies['ucc_ai_notes'].value, 'hidden')
        self.assertTrue(got_it.cookies['ucc_ai_notes']['httponly'])
        self.assertEqual(got_it.cookies['ucc_ai_notes']['samesite'], 'Lax')
        # The same confirm page again, for the same tool and question, with a fresh send button.
        self.assertContains(got_it, '“What do mitochondria do?”')
        self.assertContains(got_it, SHORT)
        self.assertNotContains(got_it, FULL)
        self.assertContains(got_it, 'AI answers can be wrong.')
        self.assertContains(got_it, '<summary>Show details</summary>')
        self.assertContains(got_it, 'Sent text cannot be recalled.')  # still there behind Show details
        self.assertTrue(got_it.context['send_form'].initial['token'])
        # Remembered on the next file confirmation.
        later = self.confirm()
        self.assertContains(later, SHORT)
        self.assertNotContains(later, FULL)

    def test_show_every_time_brings_the_full_notes_back(self):
        self.post('hide')
        shown = self.post('show')
        self.assertContains(shown, FULL)
        self.assertEqual(shown.cookies['ucc_ai_notes'].value, '')
        self.assertContains(self.confirm(), FULL)

    def test_hiding_notes_never_sends_or_counts_and_rejects_bad_values(self):
        self.post('hide')
        self.post('show')
        self.assertEqual(self.usage()['used_today'], 0)
        self.assertEqual(self.during_call, [])  # no provider connection at all
        refused = self.post('forever')
        self.assertEqual(refused.status_code, 400)
        self.assertNotIn('ucc_ai_notes', refused.cookies)
        # Another student's file is still not found, whatever the notes choice.
        self.assertEqual(self.client_b.post(self.url('ai-confirm'), {'tool': 'summary', 'notes': 'hide'}).status_code, 404)

    def test_a_cookie_alone_cannot_change_anything_but_the_notes(self):
        self.client_a.cookies['ucc_ai_notes'] = 'something-else'
        self.assertContains(self.confirm(), FULL)
