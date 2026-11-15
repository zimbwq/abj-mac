"""Native nonmodal appearance editor with an on-desktop draft preview."""
from dataclasses import replace
import AppKit as A
import objc
from Foundation import NSObject, NSMakeRect
from overlay_preferences import OverlayPreferences, POSITIONS, MODIFIERS, shortcut_label

SAMPLE = '1) A\n2) B, C\n3) D — пример ответа'


def label(text, frame):
    view = A.NSTextField.labelWithString_(text)
    view.setFrame_(frame)
    return view


class OverlayEditor(NSObject):
    @objc.python_method
    def setup(self, owner):
        self.owner = owner
        self.draft = owner.preferences
        self.active = True
        self.recording = False
        self.controls = {}
        self.values = {}
        style = A.NSWindowStyleMaskTitled | A.NSWindowStyleMaskClosable
        self.window = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 570, 570), style, A.NSBackingStoreBuffered, False)
        self.window.setTitle_('abj — Настройка текста')
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self)
        view = self.window.contentView()
        title = label('Настройте текст прямо на экране', NSMakeRect(24, 526, 520, 28))
        title.setFont_(A.NSFont.boldSystemFontOfSize_(19))
        view.addSubview_(title)
        view.addSubview_(label('Предпросмотр не отправляет снимки и не использует API.', NSMakeRect(24, 500, 520, 22)))
        for name, title, low, high, y in [
                ('duration', 'Время показа', 0, 300, 450),
                ('font_size', 'Размер шрифта', 10, 72, 360),
                ('width', 'Ширина текста', 180, 1200, 315),
                ('margin', 'Отступ от края', 0, 200, 270),
                ('opacity', 'Непрозрачность', 15, 100, 225)]:
            view.addSubview_(label(title, NSMakeRect(24, y, 155, 24)))
            slider = A.NSSlider.alloc().initWithFrame_(NSMakeRect(182, y, 255, 24))
            slider.setMinValue_(low)
            slider.setMaxValue_(high)
            slider.setContinuous_(True)
            slider.setTarget_(self)
            slider.setAction_('changed:')
            self.controls[name] = slider
            self.values[name] = label('', NSMakeRect(445, y, 110, 24))
            view.addSubview_(slider)
            view.addSubview_(self.values[name])
        view.addSubview_(label('Положение', NSMakeRect(24, 405, 150, 24)))
        position = A.NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(182, 405, 355, 26), False)
        position.addItemsWithTitles_(list(POSITIONS.values()))
        position.setTarget_(self)
        position.setAction_('changed:')
        self.controls['position'] = position
        view.addSubview_(position)
        view.addSubview_(label('Цвет текста', NSMakeRect(24, 180, 150, 24)))
        color = A.NSColorWell.alloc().initWithFrame_(NSMakeRect(182, 178, 65, 30))
        color.setTarget_(self)
        color.setAction_('changed:')
        color.setContinuous_(True)
        self.controls['color'] = color
        view.addSubview_(color)
        self.color_value = label('', NSMakeRect(260, 180, 160, 24))
        view.addSubview_(self.color_value)
        view.addSubview_(label('Скрыть текст', NSMakeRect(24, 135, 150, 24)))
        self.key_button = self.button('Esc', 'record:', NSMakeRect(182, 130, 355, 32))
        self.hint = label('Нажмите кнопку, затем клавишу или сочетание клавиш.', NSMakeRect(24, 100, 520, 25))
        view.addSubview_(self.hint)
        self.button('Сбросить', 'reset:', NSMakeRect(20, 52, 105, 30))
        self.button('Проверить время', 'testTimer:', NSMakeRect(130, 52, 160, 30))
        self.button('Отмена', 'cancel:', NSMakeRect(325, 52, 100, 30))
        self.button('Применить', 'apply:', NSMakeRect(430, 52, 120, 30))
        self.note = label('Изменения сохранятся только после «Применить».', NSMakeRect(24, 17, 520, 24))
        view.addSubview_(self.note)
        self.populate()
        self.window.center()

    @objc.python_method
    def button(self, title, action, frame):
        button = A.NSButton.alloc().initWithFrame_(frame)
        button.setTitle_(title)
        button.setBezelStyle_(A.NSBezelStyleRounded)
        button.setTarget_(self)
        button.setAction_(action)
        self.window.contentView().addSubview_(button)
        return button

    @objc.python_method
    def populate(self):
        for name in self.values:
            value = getattr(self.draft, name)
            self.controls[name].setDoubleValue_(value * 100 if name == 'opacity' else value)
        self.controls['position'].selectItemAtIndex_(list(POSITIONS).index(self.draft.position))
        rgb = [int(self.draft.color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        self.controls['color'].setColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(*rgb, 1.0))
        self.update_labels()

    @objc.python_method
    def update_labels(self):
        for name, field in self.values.items():
            value = getattr(self.draft, name)
            text = str(value)
            if name == 'duration':
                text = f'{value} сек.' if value else 'До закрытия'
            elif name == 'opacity':
                text = f'{round(value * 100)}%'
            elif name == 'font_size':
                text += ' pt'
            else:
                text += ' px'
            field.setStringValue_(text)
        self.color_value.setStringValue_(self.draft.color.upper())
        self.key_button.setTitle_(self.draft.key_label)

    @objc.python_method
    def open(self):
        A.NSApp.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
        self.preview()

    @objc.python_method
    def preview(self, timed=False):
        self.owner.show(SAMPLE, preferences=self.draft, preview=not timed)

    def changed_(self, sender):
        if not self.active:
            return
        values = {name: int(round(control.doubleValue())) for name, control in self.controls.items()
                  if name in self.values}
        values['opacity'] /= 100
        values['position'] = list(POSITIONS)[self.controls['position'].indexOfSelectedItem()]
        color = self.controls['color'].color().colorUsingColorSpace_(A.NSColorSpace.sRGBColorSpace())
        if color is not None:
            values['color'] = '#' + ''.join(f'{round(c * 255):02x}' for c in
                (color.redComponent(), color.greenComponent(), color.blueComponent()))
        self.draft = replace(self.draft, **values)
        self.update_labels()
        self.preview()

    def record_(self, sender):
        self.recording = not self.recording
        self.key_button.setTitle_('Нажмите клавишу…' if self.recording else self.draft.key_label)

    @objc.python_method
    def key_event(self, event):
        if self.recording:
            flags = int(event.modifierFlags()) & MODIFIERS
            code = int(event.keyCode())
            self.draft = replace(self.draft, key_code=code, key_modifiers=flags,
                key_label=shortcut_label(code, str(event.charactersIgnoringModifiers() or ''), flags))
            self.recording = False
            self.update_labels()
            self.preview()
            self.note.setStringValue_('Клавиша выбрана. Нажмите её ещё раз для проверки.')
            return None
        if self.draft.matches(event.keyCode(), event.modifierFlags()):
            self.owner.hide_(None)
            self.note.setStringValue_('Предпросмотр скрыт. Измените настройку, чтобы показать его снова.')
            return None
        return event

    def reset_(self, sender):
        self.recording = False
        self.draft = OverlayPreferences()
        self.populate()
        self.preview()

    def testTimer_(self, sender):
        self.preview(timed=True)
        self.note.setStringValue_('Тест времени запущен.' if self.draft.duration else 'Текст остаётся до нажатия клавиши скрытия.')

    def apply_(self, sender):
        try:
            self.owner.preference_store.save(self.draft)
        except RuntimeError as error:
            self.note.setStringValue_(str(error))
            return
        self.finish(self.draft)

    def cancel_(self, sender):
        self.finish(None)

    def windowWillClose_(self, notification):
        if self.active:
            self.finish(None, close=False)

    @objc.python_method
    def finish(self, preferences, close=True):
        if not self.active:
            return
        self.active = False
        self.controls['color'].deactivate()
        A.NSColorPanel.sharedColorPanel().orderOut_(None)
        self.owner.finish_preferences(preferences)
        if close:
            self.window.close()
