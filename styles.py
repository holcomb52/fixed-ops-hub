CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@500;600;700;800&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=JetBrains+Mono:wght@500;600&display=swap');

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header[data-testid="stHeader"] {visibility: hidden; height: 0;}
.stDeployButton {display: none;}

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    color: #e8edf5;
}

.stApp {
    background: #05070d;
}

.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 90% 60% at 10% -10%, rgba(0, 212, 255, 0.18), transparent 55%),
        radial-gradient(ellipse 70% 50% at 95% 5%, rgba(255, 107, 53, 0.14), transparent 50%),
        radial-gradient(ellipse 60% 40% at 50% 110%, rgba(124, 58, 237, 0.12), transparent 55%),
        linear-gradient(180deg, #05070d 0%, #080c16 50%, #05070d 100%);
    pointer-events: none;
    z-index: 0;
}

.stApp::after {
    content: "";
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
    background-size: 48px 48px;
    mask-image: radial-gradient(ellipse 80% 70% at 50% 30%, black, transparent);
    pointer-events: none;
    z-index: 0;
}

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1280px !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(8,12,22,0.98), rgba(5,7,13,0.99)) !important;
    border-right: 1px solid rgba(0, 212, 255, 0.12);
    box-shadow: 8px 0 40px rgba(0,0,0,0.4);
}

section[data-testid="stSidebar"] > div {
    background: transparent !important;
}

.brand-block {
    padding: 0.5rem 0 1.25rem;
}

.brand-logo {
    width: 44px;
    height: 44px;
    border-radius: 14px;
    background: linear-gradient(135deg, #00d4ff, #ff6b35);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
    box-shadow: 0 0 30px rgba(0, 212, 255, 0.35);
    margin-bottom: 0.75rem;
}

.brand-name {
    font-family: 'Syne', sans-serif;
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(90deg, #fff 0%, #94a3b8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.brand-tag {
    font-size: 0.72rem;
    color: #64748b;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 0.15rem;
}

.sidebar-footer {
    margin-top: 2rem;
    padding: 1rem;
    border-radius: 12px;
    background: rgba(0, 212, 255, 0.05);
    border: 1px solid rgba(0, 212, 255, 0.12);
    font-size: 0.75rem;
    color: #64748b;
}

.sidebar-footer strong {
    color: #00d4ff;
    font-family: 'JetBrains Mono', monospace;
}

/* Radio nav pills */
div[data-testid="stSidebar"] div[role="radiogroup"] {
    gap: 0.35rem;
}

div[data-testid="stSidebar"] div[role="radiogroup"] label {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px !important;
    padding: 0.65rem 0.9rem !important;
    margin: 0 !important;
    transition: all 0.2s ease !important;
    font-weight: 500 !important;
}

div[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    border-color: rgba(0, 212, 255, 0.35) !important;
    background: rgba(0, 212, 255, 0.06) !important;
    transform: translateX(3px);
}

div[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"],
div[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: linear-gradient(135deg, rgba(0,212,255,0.15), rgba(255,107,53,0.1)) !important;
    border-color: rgba(0, 212, 255, 0.5) !important;
    box-shadow: 0 0 20px rgba(0, 212, 255, 0.15), inset 0 1px 0 rgba(255,255,255,0.08) !important;
}

div[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {
    display: none !important;
}

/* ── Hero ── */
.page-hero {
    position: relative;
    padding: 2rem 0 2.5rem;
    margin-bottom: 0.5rem;
}

.hero-glow {
    position: absolute;
    top: -20px;
    left: -20px;
    width: 200px;
    height: 200px;
    background: radial-gradient(circle, rgba(0,212,255,0.2), transparent 70%);
    filter: blur(40px);
    animation: pulse-glow 4s ease-in-out infinite;
}

@keyframes pulse-glow {
    0%, 100% { opacity: 0.6; transform: scale(1); }
    50% { opacity: 1; transform: scale(1.1); }
}

.hero-tag {
    display: inline-block;
    padding: 0.3rem 0.75rem;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.85rem;
}

.tag-live {
    background: rgba(0, 212, 255, 0.12);
    color: #00d4ff;
    border: 1px solid rgba(0, 212, 255, 0.35);
    box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
}

.tag-warn {
    background: rgba(255, 107, 53, 0.12);
    color: #ff8c5a;
    border: 1px solid rgba(255, 107, 53, 0.35);
}

.hero-title {
    font-family: 'Syne', sans-serif !important;
    font-size: clamp(2.4rem, 5vw, 3.6rem) !important;
    font-weight: 800 !important;
    letter-spacing: -0.04em !important;
    line-height: 1.05 !important;
    margin: 0 0 0.5rem 0 !important;
    background: linear-gradient(135deg, #ffffff 0%, #00d4ff 45%, #ff6b35 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
}

.hero-sub {
    color: #8b9cb3 !important;
    font-size: 1.1rem !important;
    margin: 0 !important;
    max-width: 540px;
}

/* ── Stat cards ── */
.stat-card {
    position: relative;
    overflow: hidden;
    padding: 1.35rem 1.4rem 1.2rem;
    border-radius: 18px;
    background: rgba(12, 18, 32, 0.75);
    border: 1px solid rgba(255,255,255,0.07);
    backdrop-filter: blur(16px);
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}

.stat-card:hover {
    transform: translateY(-4px);
    border-color: rgba(255,255,255,0.14);
}

.stat-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 18px 18px 0 0;
}

.accent-cyan::before { background: linear-gradient(90deg, #00d4ff, transparent); }
.accent-cyan:hover { box-shadow: 0 12px 40px rgba(0, 212, 255, 0.15); }
.accent-cyan .stat-value { color: #00d4ff; }

.accent-orange::before { background: linear-gradient(90deg, #ff6b35, transparent); }
.accent-orange:hover { box-shadow: 0 12px 40px rgba(255, 107, 53, 0.15); }
.accent-orange .stat-value { color: #ff8c5a; }

.accent-violet::before { background: linear-gradient(90deg, #a78bfa, transparent); }
.accent-violet:hover { box-shadow: 0 12px 40px rgba(167, 139, 250, 0.15); }
.accent-violet .stat-value { color: #c4b5fd; }

.accent-green::before { background: linear-gradient(90deg, #34d399, transparent); }
.accent-green:hover { box-shadow: 0 12px 40px rgba(52, 211, 153, 0.15); }
.accent-green .stat-value { color: #6ee7b7; }

.stat-top {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-bottom: 0.6rem;
}

.stat-icon { font-size: 1rem; }

.stat-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #64748b;
}

.stat-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.1rem;
    font-weight: 600;
    line-height: 1;
}

.stat-value-sm {
    font-size: 1.25rem !important;
}

.stat-glow {
    position: absolute;
    bottom: -30px;
    right: -30px;
    width: 100px;
    height: 100px;
    background: radial-gradient(circle, rgba(0,212,255,0.12), transparent);
    pointer-events: none;
}

/* ── Module cards ── */
.module-card {
    position: relative;
    overflow: hidden;
    padding: 1.5rem;
    border-radius: 20px;
    background: rgba(12, 18, 32, 0.65);
    border: 1px solid rgba(255,255,255,0.07);
    backdrop-filter: blur(12px);
    min-height: 150px;
    transition: all 0.3s ease;
}

.module-card:hover {
    transform: translateY(-3px) scale(1.01);
    border-color: rgba(0, 212, 255, 0.25);
}

.module-card h3 {
    font-family: 'Syne', sans-serif;
    font-size: 1.15rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0;
}

.module-card p {
    color: #64748b;
    font-size: 0.88rem;
    margin: 0.6rem 0 0 0;
    line-height: 1.5;
}

.module-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
}

.module-shine {
    position: absolute;
    top: 0; left: -100%;
    width: 60%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.04), transparent);
    animation: shine 6s ease-in-out infinite;
}

@keyframes shine {
    0%, 100% { left: -100%; }
    50% { left: 150%; }
}

/* ── Badges ── */
.badge {
    display: inline-block;
    padding: 0.22rem 0.65rem;
    border-radius: 999px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
}

.badge-live {
    background: rgba(0, 212, 255, 0.12);
    color: #00d4ff;
    border: 1px solid rgba(0, 212, 255, 0.35);
}

.badge-soon {
    background: rgba(255, 107, 53, 0.1);
    color: #ff8c5a;
    border: 1px solid rgba(255, 107, 53, 0.3);
}

/* ── Status banner ── */
.status-banner {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0.85rem 1.1rem;
    border-radius: 14px;
    font-size: 0.92rem;
    font-weight: 500;
    margin-bottom: 1.5rem;
}

.banner-success {
    background: rgba(0, 212, 255, 0.08);
    border: 1px solid rgba(0, 212, 255, 0.25);
    color: #7dd3fc;
}

.banner-warn {
    background: rgba(255, 107, 53, 0.08);
    border: 1px solid rgba(255, 107, 53, 0.25);
    color: #fdba74;
}

.banner-icon {
    font-size: 0.7rem;
    animation: blink 2s ease infinite;
}

@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* ── Section titles ── */
.section-title h2 {
    font-family: 'Syne', sans-serif !important;
    font-size: 1.35rem !important;
    font-weight: 700 !important;
    color: #f1f5f9 !important;
    margin: 0 0 0.25rem 0 !important;
    letter-spacing: -0.02em !important;
}

.section-sub {
    color: #64748b;
    font-size: 0.88rem;
    margin: 0 0 1rem 0;
}

/* ── Employee cards ── */
.employee-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.15rem;
    border-radius: 16px;
    background: rgba(12, 18, 32, 0.6);
    border: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 0.65rem;
    transition: all 0.2s ease;
}

.employee-card:hover {
    border-color: rgba(0, 212, 255, 0.3);
    background: rgba(0, 212, 255, 0.04);
    transform: translateX(4px);
}

.emp-avatar {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    background: linear-gradient(135deg, rgba(0,212,255,0.25), rgba(255,107,53,0.2));
    border: 1px solid rgba(0,212,255,0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 1rem;
    color: #00d4ff;
    flex-shrink: 0;
}

.emp-info { flex: 1; min-width: 0; }

.emp-name {
    font-weight: 600;
    color: #f1f5f9;
    font-size: 0.95rem;
}

.emp-role {
    color: #64748b;
    font-size: 0.8rem;
    margin-top: 0.1rem;
}

.emp-meta { text-align: right; }

.emp-rate {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    color: #34d399;
    font-size: 0.95rem;
}

.emp-status {
    font-size: 0.72rem;
    color: #64748b;
    text-transform: capitalize;
    margin-top: 0.15rem;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.35rem;
}

.dot-live, .dot-off {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
}

.dot-live {
    background: #34d399;
    box-shadow: 0 0 8px #34d399;
}

.dot-off { background: #64748b; }

/* ── Panels ── */
.glass-panel {
    padding: 1.5rem;
    border-radius: 20px;
    background: rgba(12, 18, 32, 0.55);
    border: 1px solid rgba(255,255,255,0.07);
    backdrop-filter: blur(14px);
}

.coming-soon {
    position: relative;
    text-align: center;
    padding: 4rem 2rem;
    border-radius: 24px;
    background: rgba(12, 18, 32, 0.5);
    border: 1px dashed rgba(0, 212, 255, 0.25);
    overflow: hidden;
}

.coming-soon h2 {
    font-family: 'Syne', sans-serif;
    color: #e2e8f0;
    font-size: 1.6rem;
    margin: 0 0 0.5rem;
}

.coming-soon p {
    color: #64748b;
    margin: 0;
}

.coming-ring {
    position: absolute;
    top: 50%; left: 50%;
    width: 300px; height: 300px;
    transform: translate(-50%, -50%);
    border: 1px solid rgba(0, 212, 255, 0.08);
    border-radius: 50%;
    animation: ring-pulse 3s ease infinite;
}

@keyframes ring-pulse {
    0%, 100% { transform: translate(-50%, -50%) scale(0.8); opacity: 0.3; }
    50% { transform: translate(-50%, -50%) scale(1.1); opacity: 0.8; }
}

/* ── Streamlit widgets ── */
.stButton > button {
    border-radius: 12px !important;
    border: 1px solid rgba(0, 212, 255, 0.35) !important;
    background: linear-gradient(135deg, rgba(0,212,255,0.18), rgba(255,107,53,0.12)) !important;
    color: #f1f5f9 !important;
    font-weight: 600 !important;
    font-family: 'DM Sans', sans-serif !important;
    padding: 0.6rem 1.2rem !important;
    transition: all 0.2s ease !important;
}

.stButton > button:hover {
    border-color: #00d4ff !important;
    box-shadow: 0 0 28px rgba(0, 212, 255, 0.3) !important;
    transform: translateY(-1px) !important;
}

.stTextInput input, .stNumberInput input, .stSelectbox > div > div,
.stDateInput input {
    background: rgba(12, 18, 32, 0.8) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
}

div[data-testid="stForm"] {
    border: 1px solid rgba(0, 212, 255, 0.15);
    border-radius: 18px;
    padding: 1.25rem;
    background: rgba(12, 18, 32, 0.4);
}

div[data-testid="stAlert"] {
    border-radius: 12px;
}

hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, rgba(0,212,255,0.2), transparent) !important;
    margin: 2rem 0 !important;
}

/* Hide default markdown h2/h3 styling conflicts */
h2, h3 { font-family: 'Syne', sans-serif; }

/* ── Warranty RO grid ── */
.warranty-ro-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
    margin-top: 0.75rem;
}

@media (max-width: 1100px) {
    .warranty-ro-grid {
        grid-template-columns: 1fr;
    }
}

.warranty-ro-card {
    padding: 1rem 1.1rem;
    border-radius: 16px;
    background: rgba(12, 18, 32, 0.62);
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.warranty-ro-card.excluded-ro {
    border-color: rgba(148, 163, 184, 0.35);
    opacity: 0.92;
}

.warranty-ro-header {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: flex-start;
    padding-bottom: 0.65rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 0.65rem;
}

.warranty-ro-title {
    font-family: 'Syne', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    color: #f8fafc;
}

.warranty-ro-meta {
    color: #94a3b8;
    font-size: 0.78rem;
    margin-top: 0.2rem;
}

.warranty-ro-total {
    text-align: right;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: #cbd5e1;
    white-space: nowrap;
}

.warranty-ro-line-panel {
    margin-top: 0.75rem;
    padding: 0.75rem 0.85rem;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
}

.warranty-ro-line-panel.excluded-line {
    opacity: 0.78;
    border-color: rgba(148, 163, 184, 0.25);
}

.warranty-ro-line-title {
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #94a3b8;
    margin-bottom: 0.55rem;
}

.warranty-ro-line-top {
    display: grid;
    grid-template-columns: 1.1fr 1.6fr 0.7fr 0.8fr 0.8fr;
    gap: 0.45rem;
    font-size: 0.8rem;
    color: #e2e8f0;
    margin-bottom: 0.45rem;
}

.warranty-ro-line-label {
    color: #64748b;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.1rem;
}

.warranty-ro-line.excluded-line {
    opacity: 0.72;
}

.warranty-ro-elr-good {
    color: #86efac;
    font-weight: 700;
}

.warranty-ro-elr-bad {
    color: #fca5a5;
    font-weight: 700;
}

.warranty-ro-wrap.warranty-ro-card-pending [data-testid="stVerticalBlockBorderWrapper"] {
    border-color: rgba(251, 191, 36, 0.72) !important;
    box-shadow:
        0 0 0 1px rgba(251, 191, 36, 0.2),
        0 0 22px rgba(251, 191, 36, 0.14),
        inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.warranty-ro-wrap.warranty-ro-card-reviewed [data-testid="stVerticalBlockBorderWrapper"] {
    border-color: rgba(34, 197, 94, 0.55) !important;
    opacity: 0.92;
    box-shadow: 0 0 16px rgba(34, 197, 94, 0.1);
}

.warranty-ro-wrap.warranty-ro-card-focus [data-testid="stVerticalBlockBorderWrapper"] {
    border-color: rgba(0, 212, 255, 0.75) !important;
    box-shadow: 0 0 18px rgba(0, 212, 255, 0.18);
}

.warranty-ro-review-strip {
    margin: -0.35rem -0.35rem 1rem;
    padding: 0.95rem 1rem 0.95rem 1.15rem;
    border-radius: 14px 14px 10px 10px;
    border: 2px solid rgba(255, 255, 255, 0.1);
    border-left-width: 6px;
}

.warranty-ro-review-strip.pending {
    background: linear-gradient(90deg, rgba(251, 191, 36, 0.34), rgba(251, 191, 36, 0.12) 55%, rgba(251, 191, 36, 0.05));
    border-color: rgba(251, 191, 36, 0.75);
    border-left-color: #fbbf24;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.08),
        0 0 24px rgba(251, 191, 36, 0.16);
    animation: warranty-review-pulse 2.2s ease-in-out infinite;
}

.warranty-ro-review-strip.done {
    background: linear-gradient(90deg, rgba(34, 197, 94, 0.3), rgba(34, 197, 94, 0.1) 55%, rgba(34, 197, 94, 0.04));
    border-color: rgba(74, 222, 128, 0.55);
    border-left-color: #4ade80;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.07),
        0 0 18px rgba(34, 197, 94, 0.12);
}

@keyframes warranty-review-pulse {
    0%, 100% {
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.08),
            0 0 18px rgba(251, 191, 36, 0.12);
    }
    50% {
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.08),
            0 0 30px rgba(251, 191, 36, 0.28);
    }
}

.warranty-review-status {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    min-height: 2.6rem;
}

.warranty-review-status-copy {
    display: flex;
    flex-direction: column;
    gap: 0.12rem;
}

.warranty-review-headline {
    font-family: 'Syne', sans-serif;
    font-size: 1.18rem;
    font-weight: 800;
    line-height: 1.1;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}

.warranty-review-sub {
    font-size: 0.82rem;
    font-weight: 600;
    opacity: 0.92;
}

.warranty-review-status-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.15rem;
    height: 2.15rem;
    border-radius: 999px;
    font-size: 1.05rem;
    font-weight: 900;
    flex-shrink: 0;
    box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.08);
}

.warranty-review-status.pending .warranty-review-headline {
    color: #fef3c7;
    text-shadow: 0 0 18px rgba(251, 191, 36, 0.35);
}

.warranty-review-status.pending .warranty-review-sub {
    color: #fde68a;
}

.warranty-review-status.pending .warranty-review-status-icon {
    color: #78350f;
    background: #fbbf24;
}

.warranty-review-status.done .warranty-review-headline {
    color: #dcfce7;
    text-shadow: 0 0 16px rgba(74, 222, 128, 0.28);
}

.warranty-review-status.done .warranty-review-sub {
    color: #bbf7d0;
}

.warranty-review-status.done .warranty-review-status-icon {
    color: #14532d;
    background: #4ade80;
}

.warranty-ro-wrap [data-testid="stButton"] {
    margin-top: 0.15rem;
}

.warranty-ro-wrap [data-testid="stButton"] > button {
    min-height: 3.1rem !important;
    padding: 0.7rem 1rem !important;
    border-radius: 12px !important;
    font-family: 'Syne', sans-serif !important;
    font-size: 1.02rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.03em !important;
    text-transform: uppercase !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.28) !important;
}

.warranty-ro-wrap.warranty-ro-card-pending [data-testid="stButton"] > button {
    background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%) !important;
    color: #1f1300 !important;
    border: 2px solid #fde68a !important;
    box-shadow:
        0 0 0 1px rgba(251, 191, 36, 0.35),
        0 10px 24px rgba(251, 191, 36, 0.35) !important;
}

.warranty-ro-wrap.warranty-ro-card-pending [data-testid="stButton"] > button:hover {
    border-color: #fff7d6 !important;
    filter: brightness(1.05);
}

.warranty-ro-wrap.warranty-ro-card-reviewed [data-testid="stButton"] > button {
    background: linear-gradient(180deg, #4ade80 0%, #16a34a 100%) !important;
    color: #052e16 !important;
    border: 2px solid #bbf7d0 !important;
    box-shadow:
        0 0 0 1px rgba(74, 222, 128, 0.35),
        0 8px 20px rgba(34, 197, 94, 0.28) !important;
}

.warranty-review-resume {
    margin: 0.35rem 0 0.85rem;
    padding: 0.65rem 0.85rem;
    border-radius: 12px;
    background: rgba(0, 212, 255, 0.08);
    border: 1px solid rgba(0, 212, 255, 0.22);
    color: #cbd5e1;
    font-size: 0.88rem;
}

.warranty-review-resume-ro {
    color: #67e8f9;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
}

/* ── Payroll grid legend ── */
.legend-chip {
    display: inline-block;
    padding: 0.3rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-right: 0.5rem;
    margin-bottom: 0.5rem;
}

.chip-manual {
    background: rgba(255, 255, 0, 0.12);
    color: #fde047;
    border: 1px solid rgba(253, 224, 71, 0.35);
}

.chip-calc {
    background: rgba(255, 140, 0, 0.12);
    color: #ff8c5a;
    border: 1px solid rgba(255, 140, 0, 0.35);
}

.chip-total {
    background: rgba(52, 211, 153, 0.12);
    color: #6ee7b7;
    border: 1px solid rgba(52, 211, 153, 0.35);
}

.cell-tag {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.2rem 0.5rem;
    border-radius: 6px;
    margin-bottom: 0.5rem;
}

.tag-manual {
    background: rgba(255, 255, 0, 0.15);
    color: #fde047;
}

.tag-calc {
    background: rgba(255, 140, 0, 0.15);
    color: #ff8c5a;
}

.tag-total {
    background: rgba(52, 211, 153, 0.15);
    color: #6ee7b7;
}

.total-pay-box {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2rem;
    font-weight: 700;
    color: #6ee7b7;
    padding: 1rem;
    border-radius: 16px;
    background: rgba(52, 211, 153, 0.08);
    border: 1px solid rgba(52, 211, 153, 0.3);
    text-align: center;
    box-shadow: 0 0 30px rgba(52, 211, 153, 0.12);
}

.team-total-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.25rem;
    border-radius: 14px;
    background: linear-gradient(135deg, rgba(0,212,255,0.1), rgba(255,107,53,0.08));
    border: 1px solid rgba(0, 212, 255, 0.25);
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #94a3b8;
}

.team-total-val {
    font-family: 'JetBrains Mono', monospace;
    color: #00d4ff;
    font-size: 1.1rem;
}
</style>
"""
