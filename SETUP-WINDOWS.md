# Fixed Ops Hub — Windows Setup

A Chrome bookmark to `http://localhost:8510` only works **after** the app is running on that Windows PC.  
The bookmark does not start the app by itself.

## Quick fix (do this on your Windows computer)

1. Make sure the full `fixed-ops-hub` project folder is on the Windows PC  
   (OneDrive sync, USB copy, or Git clone).

2. Open the `fixed-ops-hub` folder in File Explorer.

3. Double-click **`SETUP-WINDOWS.bat`**  
   - Installs Python packages  
   - Creates a **Fixed Ops Hub** shortcut on your Desktop  
   - Adds startup so the app is ready after login  
   - Opens Google Chrome to the app

4. In Google Chrome, bookmark: **http://localhost:8510**

## Every day

- **Best:** double-click **Fixed Ops Hub** on your Desktop  
  (starts the app and opens Chrome)

- **Or:** click your Chrome bookmark **after** the PC has logged in  
  (works once startup is installed)

## If the bookmark still will not open

1. Double-click **`Open Fixed Ops Hub.bat`** in the project folder  
2. Read any error message on screen  
3. If it says Python is missing:
   - Install Python 3 from https://www.python.org/downloads/
   - Check **Add Python to PATH**
   - Run **`SETUP-WINDOWS.bat`** again

## Same app on Mac and Windows

| | Mac | Windows |
|---|-----|---------|
| Bookmark | http://localhost:8510 | http://localhost:8510 |
| First-time setup | `scripts/install-autostart.sh` | `SETUP-WINDOWS.bat` |
| Daily launcher | Fixed Ops Hub app / Desktop | Fixed Ops Hub Desktop shortcut |

Each computer runs its own copy. Install setup once on **each** machine.
