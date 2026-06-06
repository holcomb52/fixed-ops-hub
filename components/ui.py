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
