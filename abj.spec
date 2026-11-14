# Build only on a native Apple Silicon macOS runner.
a = Analysis(['mac_app.py'], pathex=[], binaries=[], datas=[],
             hiddenimports=['PIL.ImageGrab', 'PIL.PngImagePlugin', 'certifi'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='abj', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          target_arch='arm64', codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='abj')
app = BUNDLE(coll, name='abj.app', bundle_identifier='io.github.zimbwq.abjmac',
             info_plist={'CFBundleShortVersionString': '1.1.0', 'CFBundleVersion': '2',
                         'LSUIElement': True, 'LSMinimumSystemVersion': '15.0',
                         'NSHighResolutionCapable': True,
                         'NSScreenCaptureUsageDescription': 'Send a screenshot to your selected AI provider.',
                         'NSAppleEventsUsageDescription': 'abj uses global input to detect triple-click and Escape.'})
