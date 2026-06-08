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
4. Go to **Project Settings → API** and copy:
   - **Project URL**
   - **service_role** key (keep this secret)

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
4. Click **Advanced settings → Secrets** and paste (see `streamlit-cloud-secrets.example.toml`):

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "your_service_role_key_here"
APP_PASSWORD = "choose-a-strong-password"
```

Use the **service_role** key from Supabase (not the anon key). Pick a strong `APP_PASSWORD` you will use to sign in.

5. Click **Deploy**.

Wait 2–5 minutes. Streamlit gives you a public URL.

---

## Step 4 — Bookmark it

In **Google Chrome** on Mac and Windows, bookmark your Streamlit URL.

Sign in with the `APP_PASSWORD` you set in secrets.

---

## Important notes

| Topic | Detail |
|-------|--------|
| **No Windows install** | Cloud runs on Streamlit servers — your PC only needs Chrome |
| **Saved reports** | Payroll and warranty saves go to Supabase when configured |
| **Password** | `APP_PASSWORD` in secrets protects the app — required for dealership data |
| **Updates** | Push changes to GitHub → Streamlit redeploys automatically |
| **AI** | This app does not use AI — it is spreadsheet math and reporting only |

---

## If deploy fails

- Check Streamlit **Manage app → Logs** for errors.
- Confirm `requirements.txt` is in the repo root.
- Confirm Supabase URL and key are correct in Secrets.
- Run the new `warranty_labor_runs` SQL in Supabase if warranty save fails.

---

## Need help?

If you share your GitHub username, your developer can prepare the repo push for you. You only need to click Deploy in Streamlit Cloud and paste your Supabase secrets.
