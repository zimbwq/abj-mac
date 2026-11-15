from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from overlay_preferences import OverlayPreferences, PreferenceStore, POSITIONS, layout_frame, shortcut_label


class OverlayPreferenceTests(unittest.TestCase):
    def test_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'abj' / 'overlay.json'
            self.assertEqual(PreferenceStore(path).load(), OverlayPreferences())
            changed = OverlayPreferences(duration=0, position='top-left', font_size=32,
                color='#ff0044', opacity=0.6, width=650, margin=40,
                key_code=7, key_modifiers=1 << 20, key_label='⌘X')
            PreferenceStore(path).save(changed)
            self.assertEqual(PreferenceStore(path).load(), changed)
            self.assertNotIn('key', json.loads(path.read_text(encoding='utf-8')))

    def test_failed_save_preserves_prior_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PreferenceStore(Path(folder) / 'overlay.json')
            store.save(OverlayPreferences())
            with patch('overlay_preferences.os.replace', side_effect=OSError):
                with self.assertRaises(RuntimeError):
                    store.save(OverlayPreferences(font_size=40))
            self.assertEqual(store.load().font_size, 16)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_invalid_values_rejected(self):
        for field, value in [('duration', -1), ('duration', 301), ('font_size', True),
                             ('opacity', float('nan')), ('color', 'red'), ('position', 'other'),
                             ('key_modifiers', -1), ('key_label', '\n')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(OverlayPreferences(), **{field: value})

    def test_corrupt_file_reported_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'overlay.json'
            path.write_text('bad')
            with self.assertRaises(RuntimeError):
                PreferenceStore(path).load()
            self.assertEqual(path.read_text(), 'bad')

    def test_layout_all_positions_stay_in_visible_screen(self):
        for position in POSITIONS:
            prefs = OverlayPreferences(position=position, width=1200, margin=200)
            x, y, w, h = layout_frame(prefs, (-800, 100, 640, 480), 1000)
            self.assertGreaterEqual(x, -800)
            self.assertGreaterEqual(y, 100)
            self.assertLessEqual(x + w, -160)
            self.assertLessEqual(y + h, 580)
        self.assertEqual(layout_frame(OverlayPreferences(), (0, 0, 1440, 900), 100), (976, 24, 440, 100))

    def test_shortcut_requires_exact_modifiers_but_ignores_capslock(self):
        prefs = OverlayPreferences(key_code=7, key_modifiers=(1 << 20), key_label='⌘X')
        self.assertTrue(prefs.matches(7, (1 << 20) | (1 << 16)))
        self.assertFalse(prefs.matches(7, 0))
        self.assertFalse(prefs.matches(7, (1 << 20) | (1 << 17)))
        self.assertFalse(prefs.matches(53, (1 << 20)))
        self.assertEqual(shortcut_label(53, '\x1b', 0), 'Esc')
        self.assertEqual(shortcut_label(7, 'x', (1 << 20) | (1 << 17)), '⇧⌘X')

    def test_trigger_modes_and_modifiers(self):
        for mode, mouse, keyboard in [('triple', True, False), ('keyboard', False, True), ('both', True, True)]:
            prefs = OverlayPreferences(trigger_mode=mode)
            self.assertEqual(prefs.uses_mouse(), mouse)
            self.assertEqual(prefs.matches_trigger(49, (1 << 17) | (1 << 20)), keyboard)
            self.assertFalse(prefs.matches_trigger(49, 0))
            self.assertFalse(prefs.matches_trigger(7, (1 << 17) | (1 << 20)))

    def test_conflicting_shortcuts_rejected(self):
        with self.assertRaisesRegex(ValueError, 'разные клавиши'):
            OverlayPreferences(trigger_mode='both', trigger_code=53, trigger_modifiers=0)
        for field, value in [('trigger_mode', 'invalid'), ('trigger_code', 128),
                             ('trigger_modifiers', -1), ('trigger_label', '\n')]:
            with self.assertRaises(ValueError):
                replace(OverlayPreferences(), **{field: value})

    def test_old_settings_upgrade_and_new_trigger_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'overlay.json'
            path.write_text('{"font_size": 30, "duration": 0}')
            store = PreferenceStore(path)
            old = store.load()
            self.assertEqual((old.font_size, old.duration, old.trigger_mode), (30, 0, 'triple'))
            new = replace(old, trigger_mode='keyboard', trigger_code=8,
                          trigger_modifiers=1 << 19, trigger_label='⌥C')
            store.save(new)
            self.assertEqual(PreferenceStore(path).load(), new)
