# Fixed Ops Hub

Interactive dealership operations dashboard — **Streamlit** frontend, **Supabase** backend, deployable on **Streamlit Community Cloud**.

## Stack

| Layer | Tech |
|-------|------|
| UI | Streamlit |
| Database | Supabase (Postgres) |
| Cloud | Streamlit Community Cloud + GitHub |

## 1. Set up Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Open **SQL Editor** → paste contents of `supabase/schema.sql` → **Run**
3. Go to **Project Settings → API** and copy:
   - **Project URL**
   - **service_role** key *(server-side Streamlit app — keep in secrets, never commit)*

## 2. Run locally

```bash
cd ~/Projects/fixed-ops-hub
pip3 install -r requirements.txt
cp .env.example .env
# Edit .env with your Supabase URL and key
streamlit run app.py
```

Or use Streamlit secrets locally:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml with your credentials
streamlit run app.py
```

Opens at [http://localhost:8510](http://localhost:8510).

### Open from a bookmark (Mac or Windows)

In **Google Chrome**, bookmark:

**[http://localhost:8510](http://localhost:8510)**

Use the same bookmark on every computer where Fixed Ops Hub is installed.

#### Mac — one-time setup

```bash
/Users/bigstud/Projects/fixed-ops-hub/scripts/install-autostart.sh
```

Then double-click **Fixed Ops Hub** on your Desktop or in Applications anytime. It starts the server and opens Chrome.

Optional: add **Fixed Ops Hub.app** to **System Settings → General → Login Items** so the bookmark works right after login.

#### Windows — one-time setup

1. Copy or sync this project folder to the Windows PC (OneDrive, Git, or USB).
2. Install [Python 3](https://www.python.org/downloads/) and check **Add Python to PATH**.
3. Double-click **`SETUP-WINDOWS.bat`** in the project folder.

That installs packages, creates a **Fixed Ops Hub** Desktop shortcut, adds Windows startup, and opens Chrome.

**Important:** a Chrome bookmark alone does not start the app on Windows. Run setup once, then use the Desktop shortcut or startup entry. See **[SETUP-WINDOWS.md](SETUP-WINDOWS.md)** if the bookmark will not open.

## 3. Cloud (recommended for Windows / no installs)

**Best if you cannot install Python on Windows.** One URL works on Mac, Windows, and any browser.

See **[DEPLOY-CLOUD.md](DEPLOY-CLOUD.md)** for the full walkthrough.

Quick summary:

1. Run `supabase/schema.sql` in Supabase
2. Push this repo to GitHub
3. Deploy at [share.streamlit.io](https://share.streamlit.io) with secrets:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "your_service_role_key"
APP_PASSWORD = "choose-a-strong-password"
```

4. Bookmark your `https://something.streamlit.app` URL in Chrome

No AI runs in this app — it is payroll and warranty spreadsheet math only.

## Project structure

```
app.py                          # Main entry
lib/supabase_client.py          # Supabase connection
supabase/schema.sql             # Database tables (run once in Supabase)
views/
  home.py                       # Dashboard home
  payroll.py                    # Payroll tab + employee roster
```

## Current modules

| Tab | Status |
|-----|--------|
| Home | Live — shows Supabase connection status |
| Payroll | Live — employee roster, add employees |
| Inventory | Placeholder |
| Reports | Placeholder |
