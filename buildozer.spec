[app]
title = Cafe POS
package.name = cafepos
package.domain = org.cafepos
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,sqlite3,md
version = 0.1.0
requirements = python3,kivy,requests==2.25.1
orientation = portrait
fullscreen = 0
android.accept_sdk_license = True
android.ndk = 25b
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
