# JM-ACCOUNTS SYSTEM - Android (APK project)

Same accounting engine as the desktop app (chart of accounts, journal, T-accounts, trial balance, income statement,
financial position, inventory + stock report, users and permissions) with a touch screen on top (Kivy).

Two APKs are built from this one project:
* **A - Automatic posting**  (inventory purchases / sales / adjustments write their journal entries)
* **B - Separate list**      (inventory is only a stock list; the journal is never touched)
They have different package names, so both can be installed side by side. Each keeps its own data file.

## Get the APK with GitHub (no Android Studio, no Python on your PC)
1. Make a new empty repository on github.com (private is fine).
2. Unzip this project, then on the repo page: **Add file > Upload files** and drag in EVERYTHING inside the folder
   (including the hidden `.github` folder). Commit.
   - If `.github/workflows/android.yml` did not upload: **Add file > Create new file**, type that exact path as the name,
     and paste the contents of the file.
3. Open the **Actions** tab > **Build Android APK** > **Run workflow**. First run takes about 20-40 minutes (it downloads the
   Android SDK/NDK); later runs are faster.
4. When both jobs are green, open the run, scroll to **Artifacts**, download `JM-Accounts-A-apk` (and/or `-B-`), unzip it.
5. Copy the `.apk` to the phone, tap it, allow "Install unknown apps" if asked, install.

## First start
Sign in with `admin` / `admin123`. You are made to choose your own password straight away.
The first start loads the accounts and journal from `seed.json` (taken from your desktop app). Data is saved automatically
inside the app's private storage.

## Tabs
* **Stock** - items, purchases, sales, adjustments, movements, stock value, LOW/OUT flags
* **Accounts** - add / edit / delete accounts
* **Journal** - add / edit / delete entries (entries made by Stock in version A are managed from Stock)
* **Reports** - General Journal, T-Accounts, Trial Balance, Income Statement, Financial Position, Stock Report; Share button
* **More** - business settings, backup / share backup / restore, change password and username, Manage users (Admin)

## Moving your real books from the desktop
Desktop: File > Back up (gives a .json). Open the .json on the PC, copy all the text, send it to yourself (WhatsApp/email),
copy it on the phone, then **More > Restore from clipboard**. (Desktop and phone use the same data format.)

## Not in the phone version (yet)
Excel import, PDF/Excel export and Gmail sending (reports are shared as text instead), printing.

## Switching version in code
`variant.py` - the default is A. The GitHub workflow sets it for each APK, so you normally never touch it.
