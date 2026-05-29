[app]
title = Swamp
package.name = swamp
package.domain = app.swamp
source.dir = .
source.include_exts = py
# Only the minimal entry point — no src/ needed yet
source.include_patterns = main_minimal.py

version = 0.1.0
requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 26
android.ndk = 25b
android.sdk = 33
android.ndk_api = 21
android.archs = arm64-v8a

[buildozer]
log_level = 1
warn_on_root = 1
