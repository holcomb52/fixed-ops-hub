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

Opens at [http://localhost:8501](http://localhost:8501).

## 3. Deploy to the cloud

### Push to GitHub

```bash
git add app.py requirements.txt .streamlit/config.toml styles.py views/ lib/ supabase/ README.md .gitignore .env.example .streamlit/secrets.toml.example
git commit -m "Add Streamlit + Supabase fixed ops dashboard"
git remote add origin https://github.com/YOUR_USERNAME/fixed-ops-hub.git
git push -u origin main
```

### Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub
2. **New app** → repo `fixed-ops-hub`, branch `main`, main file `app.py`
3. Open **Advanced settings → Secrets** and add:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "your_service_role_key"
```

4. **Deploy** — you get a shareable URL like `https://fixed-ops-hub.streamlit.app`

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
