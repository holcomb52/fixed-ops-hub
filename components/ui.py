def page_hero(title: str, subtitle: str, tag: str = "", tag_style: str = "live") -> str:
    tag_html = ""
    if tag:
        tag_html = f'<span class="hero-tag tag-{tag_style}">{tag}</span>'
    return f"""
    <div class="page-hero">
        <div class="hero-glow"></div>
        {tag_html}
        <h1 class="hero-title">{title}</h1>
        <p class="hero-sub">{subtitle}</p>
    </div>
    """


def stat_card(label: str, value: str, accent: str = "cyan", icon: str = "") -> str:
    icon_html = f'<span class="stat-icon">{icon}</span>' if icon else ""
    return f"""
    <div class="stat-card accent-{accent}">
        <div class="stat-top">
            {icon_html}
            <span class="stat-label">{label}</span>
        </div>
        <div class="stat-value">{value}</div>
        <div class="stat-glow"></div>
    </div>
    """


def module_card(title: str, desc: str, status: str, accent: str = "cyan") -> str:
    live = status.lower() in ("live", "connected")
    badge_cls = "badge-live" if live else "badge-soon"
    badge_txt = status if live else status
    return f"""
    <div class="module-card accent-{accent}">
        <div class="module-header">
            <h3>{title}</h3>
            <span class="badge {badge_cls}">{badge_txt}</span>
        </div>
        <p>{desc}</p>
        <div class="module-shine"></div>
    </div>
    """


def status_banner(message: str, kind: str = "success") -> str:
    icons = {"success": "●", "warn": "◆", "error": "▲", "info": "◎"}
    return f"""
    <div class="status-banner banner-{kind}">
        <span class="banner-icon">{icons.get(kind, "●")}</span>
        <span>{message}</span>
    </div>
    """


def section_title(title: str, subtitle: str = "") -> str:
    sub = f'<p class="section-sub">{subtitle}</p>' if subtitle else ""
    return f'<div class="section-title"><h2>{title}</h2>{sub}</div>'


def pay_plan_section_header(
    title: str,
    subtitle: str,
    count: int,
    accent: str = "cyan",
    icon: str = "📋",
    badge: str = "",
    count_label: str = "advisor",
) -> str:
    badge_html = f'<span class="pay-plan-badge">{badge}</span>' if badge else ""
    count_plural = f"{count_label}s" if count != 1 else count_label
    return f"""
    <div class="pay-plan-section-header accent-{accent}">
        <div class="pay-plan-section-icon">{icon}</div>
        <div class="pay-plan-section-body">
            <div class="pay-plan-section-top">
                <span class="pay-plan-section-title">{title}</span>
                {badge_html}
                <span class="pay-plan-section-count">{count} {count_plural}</span>
            </div>
            <p class="pay-plan-section-sub">{subtitle}</p>
        </div>
    </div>
    """


def team_section_header(
    title: str,
    subtitle: str,
    count: int,
    accent: str = "cyan",
    icon: str = "🔧",
    badge: str = "",
) -> str:
    return pay_plan_section_header(
        title=title,
        subtitle=subtitle,
        count=count,
        accent=accent,
        icon=icon,
        badge=badge,
        count_label="technician",
    )


ACCENT_COLORS = {
    "orange": {"border": "#ff6b35", "bg": "linear-gradient(135deg, rgba(255, 107, 53, 0.14), rgba(12, 18, 32, 0.82))", "title": "#ffbc9a", "avatar": "rgba(255, 107, 53, 0.22)", "divider": "rgba(255, 107, 53, 0.45)"},
    "cyan": {"border": "#00d4ff", "bg": "linear-gradient(135deg, rgba(0, 212, 255, 0.12), rgba(12, 18, 32, 0.82))", "title": "#7eeaff", "avatar": "rgba(0, 212, 255, 0.2)", "divider": "rgba(0, 212, 255, 0.35)"},
    "violet": {"border": "#a78bfa", "bg": "linear-gradient(135deg, rgba(167, 139, 250, 0.16), rgba(12, 18, 32, 0.82))", "title": "#c4b5fd", "avatar": "rgba(167, 139, 250, 0.22)", "divider": "rgba(167, 139, 250, 0.45)"},
    "green": {"border": "#34d399", "bg": "linear-gradient(135deg, rgba(52, 211, 153, 0.14), rgba(12, 18, 32, 0.82))", "title": "#86efac", "avatar": "rgba(52, 211, 153, 0.2)", "divider": "rgba(52, 211, 153, 0.35)"},
    "rose": {"border": "#fb7185", "bg": "linear-gradient(135deg, rgba(251, 113, 133, 0.14), rgba(12, 18, 32, 0.82))", "title": "#fecdd3", "avatar": "rgba(251, 113, 133, 0.22)", "divider": "rgba(251, 113, 133, 0.4)"},
    "amber": {"border": "#fbbf24", "bg": "linear-gradient(135deg, rgba(251, 191, 36, 0.14), rgba(12, 18, 32, 0.82))", "title": "#fde68a", "avatar": "rgba(251, 191, 36, 0.22)", "divider": "rgba(251, 191, 36, 0.4)"},
    "blue": {"border": "#60a5fa", "bg": "linear-gradient(135deg, rgba(96, 165, 250, 0.14), rgba(12, 18, 32, 0.82))", "title": "#bfdbfe", "avatar": "rgba(96, 165, 250, 0.22)", "divider": "rgba(96, 165, 250, 0.4)"},
    "teal": {"border": "#2dd4bf", "bg": "linear-gradient(135deg, rgba(45, 212, 191, 0.14), rgba(12, 18, 32, 0.82))", "title": "#99f6e4", "avatar": "rgba(45, 212, 191, 0.2)", "divider": "rgba(45, 212, 191, 0.38)"},
    "fuchsia": {"border": "#e879f9", "bg": "linear-gradient(135deg, rgba(232, 121, 249, 0.14), rgba(12, 18, 32, 0.82))", "title": "#f5d0fe", "avatar": "rgba(232, 121, 249, 0.22)", "divider": "rgba(232, 121, 249, 0.4)"},
    "lime": {"border": "#a3e635", "bg": "linear-gradient(135deg, rgba(163, 230, 53, 0.12), rgba(12, 18, 32, 0.82))", "title": "#d9f99d", "avatar": "rgba(163, 230, 53, 0.18)", "divider": "rgba(163, 230, 53, 0.35)"},
    "sky": {"border": "#38bdf8", "bg": "linear-gradient(135deg, rgba(56, 189, 248, 0.14), rgba(12, 18, 32, 0.82))", "title": "#bae6fd", "avatar": "rgba(56, 189, 248, 0.2)", "divider": "rgba(56, 189, 248, 0.38)"},
    "coral": {"border": "#ff8a65", "bg": "linear-gradient(135deg, rgba(255, 138, 101, 0.14), rgba(12, 18, 32, 0.82))", "title": "#ffccbc", "avatar": "rgba(255, 138, 101, 0.22)", "divider": "rgba(255, 138, 101, 0.4)"},
}

ADVISOR_ACCENT_PALETTE = list(ACCENT_COLORS.keys())


def advisor_accent_for_index(index: int) -> str:
    return ADVISOR_ACCENT_PALETTE[index % len(ADVISOR_ACCENT_PALETTE)]


def _accent_theme(accent: str) -> dict:
    return ACCENT_COLORS.get(accent, ACCENT_COLORS["cyan"])


def advisor_pay_card_header(
    name: str,
    total_pay: str,
    accent: str,
    *,
    expanded: bool = False,
) -> str:
    theme = _accent_theme(accent)
    initial = (name.strip() or "?")[0].upper()
    state_cls = " advisor-pay-card-open" if expanded else ""
    return f"""
    <div class="advisor-pay-card{state_cls}" style="
        border-left-color: {theme['border']};
        background: {theme['bg']};
    ">
        <div class="advisor-pay-card-icon" style="
            color: {theme['title']};
            background: {theme['avatar']};
            border-color: {theme['border']};
        ">{initial}</div>
        <div class="advisor-pay-card-body">
            <div class="advisor-pay-card-name" style="color: {theme['title']};">{name}</div>
        </div>
        <div class="advisor-pay-card-total" style="color: {theme['title']};">{total_pay}</div>
    </div>
    """


def advisor_pay_detail_panel(accent: str) -> str:
    theme = _accent_theme(accent)
    return f"""
    <div class="advisor-pay-detail-panel" style="
        border-left-color: {theme['border']};
        background: linear-gradient(180deg, {theme['avatar']}, rgba(12, 18, 32, 0.35));
    "></div>
    """


def team_section_divider(accent: str = "cyan") -> str:
    color = _accent_theme(accent)["divider"]
    return f"""
    <hr class="team-section-divider" style="
        height: 2px;
        border: none;
        margin: 2rem 0 1.25rem;
        background: linear-gradient(90deg, transparent, {color}, transparent);
    " />
    """


def employee_card(name: str, role: str, rate: str, status: str) -> str:
    active = status == "active"
    dot = "dot-live" if active else "dot-off"
    return f"""
    <div class="employee-card">
        <div class="emp-avatar">{name[0].upper()}</div>
        <div class="emp-info">
            <div class="emp-name">{name}</div>
            <div class="emp-role">{role}</div>
        </div>
        <div class="emp-meta">
            <div class="emp-rate">{rate}</div>
            <div class="emp-status"><span class="{dot}"></span>{status}</div>
        </div>
    </div>
    """


def coming_soon_panel(title: str, desc: str) -> str:
    return f"""
    <div class="coming-soon">
        <div class="coming-ring"></div>
        <h2>{title}</h2>
        <p>{desc}</p>
    </div>
    """
