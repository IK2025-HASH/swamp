[app]
title = Swamp
package.name = swamp
package.domain = org.swamp

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0

requirements = python3,kivy,pillow,zeroconf,pyjnius,android

orientation = portrait

osx.python_version = 3
osx.kivy_version = 2.3.0

fullscreen = 0

android.permissions = INTERNET,ACCESS_WIFI_STATE,ACCESS_NETWORK_STATE,READ_CONTACTS,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,FOREGROUND_SERVICE,CHANGE_NETWORK_STATE,CHANGE_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE

android.api = 33
android.minapi = 26
android.ndk = 25b
android.sdk = 33
android.ndk_api = 21
android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
