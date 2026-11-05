[app]
title = JM Accounts
package.name = jmaccounts
package.domain = com.jm
source.dir = .
source.include_exts = py,json,png,jpg
source.exclude_patterns = test_engine.py,README.md,.github/*
version = 1.0.0
requirements = python3,kivy==2.3.0,pyjnius
orientation = portrait
fullscreen = 0
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 0
