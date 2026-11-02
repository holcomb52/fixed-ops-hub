<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Fixed Ops Hub

The product is the Streamlit app in `app.py`. The Next.js files under `src/` are a leftover scaffold. Do not run `npm run dev` expecting Fixed Ops Hub.

The app starts only on Python 3.11 or 3.12 (`repo_path.cloud_python_supported`). This image’s `python3` is 3.12. Use that interpreter.

Debian’s PyJWT package has no RECORD file, so a system-wide `pip install` fails while uninstalling it. Install into the user site instead:

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
```

`~/.local/bin` is not on the login-shell PATH. Run Streamlit as `python3 -m streamlit run app.py --server.port 8510 --server.address 0.0.0.0 --server.headless true`.

Supabase URL, service-role key, `APP_PASSWORD`, and `OPENAI_API_KEY` are optional for local UI and the unit tests. Without them Home shows Setup Required and the database stays offline. Labor Rate still builds a customer-pay grid from the inputs on the page.

```bash
python3 -m unittest discover -s tests -v
```
