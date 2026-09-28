# Cafe POS (Android / Kivy)

An offline-first point-of-sale starter app for a cafe. It uses Python, Kivy,
and SQLite; sales and inventory remain on the device. The UI is in English and
prices are shown in ETB.

## Included

- Menu item and ingredient setup
- Recipe-based inventory usage in grams, millilitres, or individual units
- POS cart with Cash, Card, and Other payment types
- Transactional checkout: a sale is rejected if its recipe is missing or
  ingredient stock is insufficient
- Restock, waste, and stock adjustment records
- Low-stock indicators and a current-day sales summary

## Run on a computer

Python 3.10 or newer is recommended.

```powershell
python -m pip install kivy
python main.py
```

The SQLite database is created in Kivy's app-specific user data directory.

To verify the database and sales logic without installing Kivy:

```powershell
python -m unittest discover -s tests -v
```

## Build for Android

### Build with GitHub Actions (no local Android tools required)

The included `.github/workflows/android-apk.yml` builds a debug APK on a hosted
Linux runner using a pinned python-for-android release and NDK for reproducible
Android dependencies. To use it:

1. Create a repository in your own GitHub account and add this project.
2. Push the project to the repository's `main` or `master` branch, or open the
   repository's **Actions** tab and manually run **Build Android APK**.
3. When the workflow finishes, open its run and download the
   `cafe-pos-debug-apk` artifact.
4. Extract the APK and install it in your Android emulator. A debug APK is for
   testing; it is not a Play Store release.

The source is built in your GitHub repository. Check your account's current
Actions usage limits before relying on hosted build minutes.

### Build locally on Linux

Alternatively, Buildozer/python-for-android can be run on Linux. With Buildozer
installed, from this project directory run:

```sh
buildozer android debug
```

The resulting APK is under `bin/`. Android packaging and physical-device testing
should be done on the target device before using the app for live sales.

## First setup

1. Add ingredients and their opening stock. Choose `g`, `ml`, or `each`.
2. Add menu items and their ETB prices.
3. Add one or more recipe ingredients per menu item.
4. Open POS, add menu items, and record the payment method at checkout.

## Data notes

The database stores money as integer cents and sales with local timezone
timestamps. It is intended for a single-device MVP. Back up the database
regularly; uninstalling the app may remove its private app data.
