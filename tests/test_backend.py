import json
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

from cloud_backend import Session, build_request, format_response, answer_visual, NoRedirect
from gestures import TripleClick


def response(provider, items):
    text = json.dumps({'answers': items})
    if provider == 'OpenAI':
        return {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': text}]}]}
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}


class BackendTests(unittest.TestCase):
    def test_provider_routes_and_image_payloads(self):
        for provider, host in [('OpenAI', 'api.openai.com'), ('Gemini', 'generativelanguage.googleapis.com')]:
            with self.subTest(provider=provider):
                request = build_request(Session(provider, 'synthetic-key'), 'data:image/png;base64,AA==')
                self.assertEqual(request.host, host)
                self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-key')
                payload = json.loads(request.data)
                self.assertNotIn('synthetic-key', request.full_url)
                self.assertNotIn('synthetic-key', str(payload))
                if provider == 'OpenAI':
                    self.assertFalse(payload['store'])
                    self.assertEqual(payload['input'][0]['content'][1]['type'], 'input_image')
                else:
                    self.assertEqual(payload['messages'][1]['content'][1]['type'], 'image_url')

    def test_credentials_are_explicit_and_not_repr(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'do-not-read'}):
            with self.assertRaises(ValueError):
                Session('OpenAI', '')
        self.assertNotIn('secret', repr(Session('Gemini', 'secret')))
        for provider, key in [('OpenAI', 'AIza-synthetic'), ('Gemini', 'sk-synthetic'),
                              ('unknown', 'abc'), ('OpenAI', 'two words')]:
            with self.assertRaises(ValueError):
                Session(provider, key)

    def test_custom_model(self):
        self.assertEqual(Session('Gemini', 'test', 'custom-vision-model').model, 'custom-vision-model')

    def test_answers_both_providers(self):
        for provider in ('OpenAI', 'Gemini'):
            result = response(provider, [{'number': 3, 'choices': ['B', 'B']},
                {'number': 4, 'choices': []}, {'number': 5, 'choices': ['A', 'C']}])
            self.assertEqual(format_response(provider, result), '3) B\n4) ?\n5) A,C')

    def test_conflicts_remain_unknown(self):
        items = [{'number': 1, 'choices': [c]} for c in ('A', 'B', 'A')]
        self.assertEqual(format_response('Gemini', response('Gemini', items)), '1) ?')

    def test_bad_answers_rejected(self):
        for item in [{'number': True, 'choices': ['A']}, {'number': 1, 'choices': ['AB']},
                     {'number': 0, 'choices': []}, {'number': 2, 'choices': 'A'}]:
            with self.assertRaises(RuntimeError):
                format_response('OpenAI', response('OpenAI', [item]))
        with self.assertRaises(RuntimeError):
            format_response('Gemini', {'choices': [{'finish_reason': 'length', 'message': {}}]})
        with self.assertRaises(RuntimeError):
            format_response('OpenAI', {'status': 'incomplete'})

    def test_empty_screen(self):
        self.assertEqual(format_response('Gemini', response('Gemini', [])), 'Не видно полных вопросов.')

    def test_http_errors_do_not_echo_key_or_body(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError('https://example.com', 401, 'secret', {}, None)
        with patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'Gemini HTTP 401') as caught:
                answer_visual(Session('Gemini', 'secret'), 'data:image/png;base64,AA==')
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)

    def test_redirect_blocked(self):
        with self.assertRaises(RuntimeError):
            NoRedirect().redirect_request(None, None, 307, '', {}, 'https://other.example')

    def test_request_success(self):
        for provider in ('OpenAI', 'Gemini'):
            import io
            opener = MagicMock()
            opener.open.return_value = io.BytesIO(json.dumps(response(provider,
                [{'number': 1, 'choices': ['C']}])).encode())
            with patch('urllib.request.build_opener', return_value=opener):
                self.assertEqual(answer_visual(Session(provider, 'test'),
                    'data:image/png;base64,AA=='), '1) C')


class GestureTests(unittest.TestCase):
    def test_triple_click_and_reset(self):
        gesture = TripleClick()
        self.assertFalse(gesture.click(1, 10, 10))
        self.assertFalse(gesture.click(1.2, 10, 10))
        self.assertTrue(gesture.click(1.4, 10, 10))
        self.assertFalse(gesture.click(1.5, 10, 10))

    def test_slow_or_moving_clicks_ignored(self):
        for clicks in [[(1, 0, 0), (2, 0, 0), (3, 0, 0)],
                       [(1, 0, 0), (1.1, 100, 0), (1.2, 200, 0)]]:
            gesture = TripleClick()
            self.assertFalse(any(gesture.click(*click) for click in clicks))


if __name__ == '__main__':
    unittest.main()
