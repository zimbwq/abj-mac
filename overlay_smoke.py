"""Cocoa regression checks run by --self-test with isolated preferences."""
from pathlib import Path
from dataclasses import replace
import tempfile
from unittest.mock import patch
import AppKit as A
from PyObjCTools import AppHelper
from Foundation import NSRunLoop, NSDate, NSMakeRect

from overlay_preferences import OverlayPreferences, PreferenceStore


def snapshot(view, path, background=False):
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
    bitmap = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), bitmap)
    if background:
        # cacheDisplay captures the content only; include the native window backing color.
        size = view.bounds().size
        canvas = A.NSImage.alloc().initWithSize_(size)
        canvas.lockFocus()
        A.NSColor.windowBackgroundColor().set()
        A.NSRectFill(NSMakeRect(0, 0, size.width, size.height))
        foreground = A.NSImage.alloc().initWithSize_(size)
        foreground.addRepresentation_(bitmap)
        foreground.drawInRect_fromRect_operation_fraction_(
            NSMakeRect(0, 0, size.width, size.height), NSMakeRect(0, 0, size.width, size.height),
            A.NSCompositingOperationSourceOver, 1.0)
        canvas.unlockFocus()
        bitmap = A.NSBitmapImageRep.imageRepWithData_(canvas.TIFFRepresentation())
    data = bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG, {})
    assert data.writeToFile_atomically_(str(path), True)


def check_editor(controller, report_path):
    with tempfile.TemporaryDirectory() as folder:
        controller.preference_store = PreferenceStore(Path(folder) / 'overlay.json')
        controller.hide_(None)
        controller.appearance_(None)
        editor = controller.editor
        assert editor.active and controller.configuring
        assert controller.panel.isVisible()
        editor.controls['font_size'].setDoubleValue_(30)
        editor.controls['position'].selectItemAtIndex_(3)
        editor.controls['color'].setColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(0.2, 0.6, 0.9, 1))
        editor.controls['opacity'].setDoubleValue_(70)
        editor.changed_(None)
        assert controller.preferences.font_size == 16
        assert controller.text.font().pointSize() == 30
        assert abs(controller.panel.alphaValue() - 0.7) < 0.01
        assert editor.draft.color == '#3399e6'
        assert not controller.preference_store.path.exists()
        screen = A.NSScreen.screens()[0].visibleFrame()
        assert controller.panel.frame().origin.x == screen.origin.x + 24
        assert controller.panel.frame().origin.y > screen.origin.y + screen.size.height / 2
        editor.cancel_(None)
        assert controller.preferences == OverlayPreferences()
        assert not controller.panel.isVisible() and not controller.configuring
        assert not controller.preference_store.path.exists()
        # Custom shortcut is recorded and can be tested before applying.
        controller.appearance_(None)
        editor = controller.editor
        editor.controls['duration'].setDoubleValue_(0)
        editor.controls['font_size'].setDoubleValue_(24)
        editor.changed_(None)
        event = A.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            A.NSEventTypeKeyDown, (0, 0), A.NSEventModifierFlagCommand, 0, 0, None, 'x', 'x', False, 7)
        editor.record_(None)
        assert controller.local_event(event) is None
        assert editor.draft.key_label == '⌘X'
        assert controller.panel.isVisible()
        controller.local_event(event)
        assert not controller.panel.isVisible()
        editor.testTimer_(None)
        assert controller.panel.isVisible() and controller.overlay_deadline is None
        # Bind capture independently, rejecting the currently assigned dismiss shortcut.
        trigger = A.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            A.NSEventTypeKeyDown, (0, 0), A.NSEventModifierFlagCommand, 0, 0, None, 'b', 'b', False, 11)
        repeated = A.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            A.NSEventTypeKeyDown, (0, 0), A.NSEventModifierFlagCommand, 0, 0, None, 'b', 'b', True, 11)
        editor.recordTrigger_(None)
        controller.local_event(event)
        assert editor.recording == 'trigger' and editor.draft.trigger_mode == 'triple'
        controller.local_event(trigger)
        assert not editor.recording and editor.draft.trigger_label == '⌘B'
        assert editor.draft.trigger_mode == 'keyboard'
        with patch.object(controller, 'capture_') as capture:
            controller.local_event(trigger)
            controller.event(trigger)
            capture.assert_not_called()  # Preview never calls the real capture/API path.
        assert 'Это тест' in str(editor.note.stringValue())
        snapshot(editor.window.contentView(), Path(report_path).with_name(Path(report_path).stem + '-settings.png'), background=True)
        snapshot(controller.panel.contentView(), Path(report_path).with_name(Path(report_path).stem + '-preview.png'))
        with patch.object(controller.preference_store, 'save', side_effect=RuntimeError('test save failure')):
            editor.apply_(None)
        assert editor.active and controller.preferences == OverlayPreferences()
        editor.apply_(None)
        assert controller.preferences.font_size == 24 and controller.preferences.key_label == '⌘X'
        assert PreferenceStore(controller.preference_store.path).load() == controller.preferences
        controller.show('real answer')
        controller.event(event)
        assert not controller.panel.isVisible()
        # Both event routes dispatch the binding; repeats, pause, busy and other keys do not.
        with patch.object(controller, 'capture_') as capture:
            controller.local_event(trigger)
            controller.event(trigger)
            assert capture.call_count == 2
            controller.event(repeated)
            controller.armed = False
            controller.event(trigger)
            controller.armed = True
            controller.busy = True
            controller.local_event(trigger)
            controller.busy = False
            controller.event(event)
            assert capture.call_count == 2
        from cloud_backend import Session
        controller.session = Session('Gemini', 'synthetic-smoke-test')
        for mode, expected in [('keyboard', 0), ('triple', 1), ('both', 1)]:
            controller.preferences = replace(controller.preferences, trigger_mode=mode)
            controller.gesture.reset()
            with patch.object(controller, 'capture_') as capture:
                for timestamp in (1.0, 1.1, 1.2):
                    mouse = A.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
                        A.NSEventTypeLeftMouseDown, (0, 0), 0, timestamp, 0, None, 0, 1, 1.0)
                    controller.event(mouse)
                assert capture.call_count == expected
        controller.preferences = replace(controller.preferences, trigger_mode='keyboard')
        controller.session = None
        # A newly opened editor starts from saved settings; reset can be cancelled.
        controller.appearance_(None)
        editor = controller.editor
        assert editor.draft == controller.preferences
        editor.reset_(None)
        assert editor.draft == OverlayPreferences()
        editor.cancel_(None)
        assert controller.preferences.key_label == '⌘X'
        controller.appearance_(None)
        editor = controller.editor
        editor.controls['duration'].setDoubleValue_(3)
        editor.changed_(None)
        with patch.object(AppHelper, 'callLater') as schedule:
            editor.testTimer_(None)
            assert schedule.call_args.args[0] == 3
        generation = controller.overlay_generation
        controller.expire_overlay(generation)
        assert not controller.panel.isVisible()
        # Closing the window is the same as Cancel.
        editor.window.close()
        assert not controller.configuring
        assert controller.preferences.duration == 0
        controller.preferences = OverlayPreferences()
        controller.update_shortcut_label()
