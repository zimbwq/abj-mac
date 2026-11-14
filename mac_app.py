"""Native Cocoa menu-bar app. All AppKit work stays on the main thread."""
import json
import platform
import sys
import threading
from pathlib import Path

import AppKit as A
import Quartz
import objc
from Foundation import NSObject, NSMakeRect, NSRunLoop, NSDate
from PyObjCTools import AppHelper

from cloud_backend import Session, DEFAULT_MODELS, answer_visual, encode_image
from gestures import TripleClick


def alert(title, message):
    box = A.NSAlert.alloc().init()
    box.setMessageText_(title)
    box.setInformativeText_(message)
    box.addButtonWithTitle_('OK')
    A.NSApp.activateIgnoringOtherApps_(True)
    box.runModal()


def label(text, frame):
    field = A.NSTextField.alloc().initWithFrame_(frame)
    field.setStringValue_(text)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setBezeled_(False)
    field.setDrawsBackground_(False)
    return field


class Controller(NSObject):
    @objc.python_method
    def setup(self):
        self.session = None
        self.busy = False
        self.armed = True
        self.configuring = False
        self.generation = 0
        self.overlay_generation = 0
        self.gesture = TripleClick()
        self.monitors = []
        self.status = A.NSStatusBar.systemStatusBar().statusItemWithLength_(A.NSVariableStatusItemLength)
        self.status.button().setTitle_('abj')
        self.menu = A.NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        for title, action in [('Снять экран', 'capture:'), ('Тройной клик: вкл.', 'toggle:'),
                              ('Скрыть ответ (Esc)', 'hide:'), ('Провайдер и ключ…', 'settings:'),
                              ('Разрешения macOS…', 'permissions:'), ('Выход', 'quit:')]:
            item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, '')
            item.setTarget_(self)
            self.menu.addItem_(item)
        self.status.setMenu_(self.menu)
        style = A.NSWindowStyleMaskBorderless | A.NSWindowStyleMaskNonactivatingPanel
        self.panel = A.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 440, 100), style, A.NSBackingStoreBuffered, False)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(A.NSColor.clearColor())
        self.panel.setHasShadow_(False)
        self.panel.setLevel_(A.NSFloatingWindowLevel)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setIgnoresMouseEvents_(True)
        self.panel.setCollectionBehavior_(A.NSWindowCollectionBehaviorCanJoinAllSpaces |
                                          A.NSWindowCollectionBehaviorFullScreenAuxiliary)
        self.text = label('', NSMakeRect(0, 0, 440, 100))
        self.text.setTextColor_(A.NSColor.colorWithCalibratedWhite_alpha_(0.54, 1.0))
        self.text.setFont_(A.NSFont.systemFontOfSize_(16))
        self.text.setAlignment_(A.NSTextAlignmentRight)
        self.text.cell().setWraps_(True)
        self.panel.contentView().addSubview_(self.text)

    @objc.python_method
    def install_monitors(self):
        for monitor in self.monitors:
            A.NSEvent.removeMonitor_(monitor)
        self.monitors = []
        mask = A.NSEventMaskLeftMouseDown | A.NSEventMaskKeyDown
        monitor = A.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, self.event)
        if monitor is not None:
            self.monitors.append(monitor)
        # Local Esc also works while one of our own windows has focus.
        monitor = A.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            A.NSEventMaskKeyDown, self.local_event)
        if monitor is not None:
            self.monitors.append(monitor)

    @objc.python_method
    def local_event(self, event):
        if event.keyCode() == 53:
            self.hide_(None)
        return event

    @objc.python_method
    def event(self, event):
        if event.type() == A.NSEventTypeKeyDown:
            if event.keyCode() == 53:
                self.hide_(None)
        elif self.armed and self.session and not self.busy and not self.configuring:
            point = A.NSEvent.mouseLocation()
            if self.gesture.click(event.timestamp(), point.x, point.y):
                self.capture_(None)

    def toggle_(self, sender):
        self.armed = not self.armed
        self.gesture.reset()
        self.menu.itemAtIndex_(1).setTitle_('Тройной клик: ' + ('вкл.' if self.armed else 'выкл.'))

    def hide_(self, sender):
        self.overlay_generation += 1
        self.panel.orderOut_(None)

    @objc.python_method
    def show(self, text):
        self.hide_(None)
        rect = A.NSScreen.screens()[0].visibleFrame()
        width = min(440, rect.size.width - 48)
        self.text.setStringValue_(text)
        size = self.text.cell().cellSizeForBounds_(NSMakeRect(0, 0, width, 10000))
        height = min(max(40, size.height + 12), rect.size.height - 48)
        self.text.setFrame_(NSMakeRect(0, 0, width, height))
        self.panel.setFrame_display_(NSMakeRect(rect.origin.x + rect.size.width - width - 24,
                                              rect.origin.y + 24, width, height), True)
        self.panel.orderFrontRegardless()
        generation = self.overlay_generation
        AppHelper.callLater(25, self.expire_overlay, generation)

    @objc.python_method
    def expire_overlay(self, generation):
        if generation == self.overlay_generation:
            self.hide_(None)

    def settings_(self, sender):
        self.configuring = True
        self.hide_(None)
        self.gesture.reset()
        box = A.NSAlert.alloc().init()
        box.setMessageText_('abj — OpenAI / Gemini')
        box.setInformativeText_('Снимок основного экрана отправляется выбранному провайдеру. '
            'Нужны интернет, действующий API-ключ и квота. Ключ хранится только в памяти до выхода.')
        box.addButtonWithTitle_('Применить')
        box.addButtonWithTitle_('Отмена')
        view = A.NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 430, 175))
        view.addSubview_(label('Провайдер', NSMakeRect(0, 145, 100, 24)))
        provider = A.NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(110, 145, 310, 26), False)
        provider.addItemsWithTitles_(list(DEFAULT_MODELS))
        if self.session:
            provider.selectItemWithTitle_(self.session.provider)
        view.addSubview_(provider)
        view.addSubview_(label('API-ключ', NSMakeRect(0, 105, 100, 24)))
        key = A.NSSecureTextField.alloc().initWithFrame_(NSMakeRect(110, 105, 310, 26))
        view.addSubview_(key)
        view.addSubview_(label('Модель', NSMakeRect(0, 65, 100, 24)))
        model = A.NSTextField.alloc().initWithFrame_(NSMakeRect(110, 65, 310, 26))
        model.setPlaceholderString_('Пусто — модель по умолчанию')
        view.addSubview_(model)
        view.addSubview_(label('OpenAI: gpt-5-mini\nGemini: gemini-4-hydrogen', NSMakeRect(0, 5, 425, 48)))
        box.setAccessoryView_(view)
        A.NSApp.activateIgnoringOtherApps_(True)
        box.window().setInitialFirstResponder_(key)
        try:
            if box.runModal() == A.NSAlertFirstButtonReturn:
                try:
                    session = Session(str(provider.titleOfSelectedItem()), str(key.stringValue()),
                                      str(model.stringValue()))
                except ValueError as error:
                    alert('Настройки не сохранены', str(error))
                    return
                self.session = session
                self.generation += 1  # Discard a pending answer from an earlier session.
                self.status.button().setToolTip_('abj — ' + session.provider + ' / ' + session.model)
        finally:
            key.setStringValue_('')
            self.configuring = False

    def permissions_(self, sender):
        Quartz.CGRequestScreenCaptureAccess()
        Quartz.AXIsProcessTrustedWithOptions({Quartz.kAXTrustedCheckOptionPrompt: True})
        alert('Разрешения macOS',
              'В Системных настройках → Конфиденциальность и безопасность разрешите abj '
              '«Запись экрана» и «Универсальный доступ». Затем полностью закройте и откройте abj. '
              'Без этих разрешений снимок и глобальные клавиши могут не работать.')

    def capture_(self, sender):
        if self.busy or self.configuring:
            return
        if self.session is None:
            self.settings_(None)
            return
        if not Quartz.CGPreflightScreenCaptureAccess():
            self.permissions_(None)
            return
        self.busy = True
        self.hide_(None)
        self.status.button().setTitle_('abj …')
        # Let the menu/overlay disappear before capturing.
        AppHelper.callLater(0.35, self.start_worker, self.session, self.generation)

    @objc.python_method
    def start_worker(self, session, generation):
        threading.Thread(target=self.worker, args=(session, generation), daemon=True).start()

    @objc.python_method
    def worker(self, session, generation):
        try:
            from PIL import ImageGrab
            image = ImageGrab.grab()
            text = answer_visual(session, encode_image(image))
        except RuntimeError as error:
            text = str(error)
        except Exception:
            text = 'Не удалось получить снимок или ответ. Проверьте разрешения и настройки.'
        AppHelper.callAfter(self.finish, text, generation)

    @objc.python_method
    def finish(self, text, generation):
        self.busy = False
        self.status.button().setTitle_('abj')
        if generation == self.generation and not self.configuring:
            self.show(text)

    def quit_(self, sender):
        self.session = None
        for monitor in self.monitors:
            A.NSEvent.removeMonitor_(monitor)
        self.monitors = []
        A.NSApp.terminate_(None)


def self_test(controller, report_path):
    """Real Cocoa objects, synthetic answer, no key/prompt/capture/network."""
    controller.show('1) A\n2) B')
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
    assert controller.panel.isVisible()
    assert str(controller.text.stringValue()) == '1) A\n2) B'
    controller.hide_(None)
    assert not controller.panel.isVisible()
    controller.toggle_(None)
    assert not controller.armed
    controller.toggle_(None)
    assert controller.armed
    assert controller.status.menu().numberOfItems() == 6
    # Exercise native dependencies and the exact SSL CA path from the bundle.
    import certifi
    import ssl
    from PIL import Image
    ssl.create_default_context(cafile=certifi.where())
    assert encode_image(Image.new('RGB', (2, 2))).startswith('data:image/png;base64,')
    report = {'status': 'ok', 'architecture': platform.machine(),
              'checks': ['Cocoa menu', 'transparent panel show/hide', 'arm toggle',
                         'Pillow PNG', 'bundled TLS certificates'],
              'not_tested': ['user permissions', 'real screenshot', 'global input', 'live paid APIs']}
    Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')


def main():
    app = A.NSApplication.sharedApplication()
    app.setActivationPolicy_(A.NSApplicationActivationPolicyAccessory)
    controller = Controller.alloc().init()
    controller.setup()
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        self_test(controller, sys.argv[2])
        return
    controller.install_monitors()
    AppHelper.callAfter(controller.settings_, None)
    AppHelper.runEventLoop()


if __name__ == '__main__':
    main()
