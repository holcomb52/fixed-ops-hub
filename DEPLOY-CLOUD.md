# Put Fixed Ops Hub in the Cloud

Use this when you want **one web link** that works on Mac, Windows, phone, or any browser — **no installs**.

You will get a URL like:

`https://fixed-ops-hub.streamlit.app`

Bookmark that in Google Chrome on every device.

---

## What you need (free)

1. A **GitHub** account — [github.com](https://github.com)
2. A **Supabase** account — [supabase.com](https://supabase.com) (stores saved reports)
3. A **Streamlit Cloud** account — [share.streamlit.io](https://share.streamlit.io) (hosts the app)

---

## Step 1 — Supabase database

1. Create a Supabase project.
2. Open **SQL Editor → New query**.
3. Paste everything from `supabase/schema.sql` and click **Run**.
   - New projects: this creates every table **and** enables Row Level Security (RLS).
   - Existing projects that already ran an older `schema.sql`: also run `supabase/enable_rls.sql`, and `supabase/advisor_training_logs_table.sql` if Advisor Training cloud save fails.
4. Go to **Project Settings → API** and copy:
   - **Project URL**
   - **service_role** key (keep this secret — the app cannot use the anon key after RLS)

---

## Step 2 — Push code to GitHub

On your **Mac** (in Terminal):

```bash
cd ~/Projects/fixed-ops-hub
git add .
git commit -m "Prepare Fixed Ops Hub for cloud deployment"
```

1. Go to [github.com/new](https://github.com/new)
2. Repository name: `fixed-ops-hub`
3. Leave it **Public** or **Private** (Streamlit works with both)
4. **Do not** add a README — this project already has one
5. Click **Create repository**

Then on your Mac:

```bash
cd ~/Projects/fixed-ops-hub
git remote add origin https://github.com/holcomb52/fixed-ops-hub.git
git push -u origin main
```

If your GitHub username is different, replace `holcomb52` in the URL.

---

## Step 3 — Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **Create app**.
3. Choose your `fixed-ops-hub` repo, branch `main`, main file `app.py`.
4. Click **Advanced settings**:
   - **Python version:** `3.12` or `3.11` — **required**. The app now refuses 3.13+ (and anything else) with on-screen Manage-app steps. Do **not** leave Cloud on 3.13/3.14.
   - **Secrets:** paste (see `streamlit-cloud-secrets.example.toml`):

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "your_service_role_key_here"
APP_PASSWORD = "choose-a-strong-admin-password"
PARTS_MANAGER_PASSWORD = "choose-a-strong-parts-password"
PARTS_MANAGER_LABEL = "Parts Manager"
```

Use the **service_role** key from Supabase (not the anon key). After RLS is enabled, the anon key cannot read or write payroll tables.

- `APP_PASSWORD` — full Fixed Ops Hub access (you). **Required** whenever the app is on a public URL with Supabase connected.
- `PARTS_MANAGER_PASSWORD` — Parts tab + Parts Returns / Stocking reports only (Parts Manager)

5. Click **Deploy**.

Wait 2–5 minutes. Streamlit gives you a public URL.

---

## Step 4 — Bookmark it

In **Google Chrome** on Mac and Windows, bookmark your Streamlit URL.

Sign in with `APP_PASSWORD` (full access) or give the Parts Manager `PARTS_MANAGER_PASSWORD`.

---

## Important notes

| Topic | Detail |
|-------|--------|
| **No Windows install** | Cloud runs on Streamlit servers — your PC only needs Chrome |
| **Saved reports** | Payroll and warranty saves go to Supabase when configured |
| **Passwords** | `APP_PASSWORD` = full app; `PARTS_MANAGER_PASSWORD` = Parts + Parts Returns only |
| **Updates** | Push changes to GitHub → Streamlit redeploys automatically |
| **AI** | This app does not use AI — it is spreadsheet math and reporting only |

---

## If deploy fails

- Check Streamlit **Manage app → Logs** for errors.
- Confirm `requirements.txt` is in the repo root.
- Confirm Supabase URL and key are correct in Secrets.
- Run `supabase/schema.sql` (or the matching `supabase/*_table.sql`) if a cloud save says a table is missing.
- Run `supabase/enable_rls.sql` on older projects so payroll tables are not readable with the anon key.
- **Redacted `ImportError` at `from lib.app_auth import` / Python 3.13+:**  
  The live crash is at that import, after the old 3.14-only guard, so Cloud is likely on **3.13**.  
  Current `app.py` stops on anything other than 3.11/3.12 **before** importing `lib.app_auth`, with this fix on screen:  
  **Manage app** (bottom right) → **Settings** → **Python version** → **3.12** → **Save** → **Reboot app**.  
  If the version is locked, delete and recreate the app with **Python 3.12** in Advanced settings, then paste secrets again.  
  The app also pins this repo ahead of the venv `lib/` folder, in case the ImportError is a package-name collision rather than the interpreter.

---

## Need help?

If you share your GitHub username, your developer can prepare the repo push for you. You only need to click Deploy in Streamlit Cloud and paste your Supabase secrets.
