import csv
import io
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode

from dash import Dash, html, dcc, Input, Output, State, ALL, ctx, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import requests

from config import API_KEY


NEWS_URL = "https://newsapi.org/v2/everything"

QUICK_TOPICS = [
    ("Artificial Intelligence", "bi-cpu"),
    ("Climate", "bi-globe-americas"),
    ("Space", "bi-rocket-takeoff"),
    ("Crypto", "bi-currency-bitcoin"),
    ("Health", "bi-heart-pulse"),
    ("Startups", "bi-lightbulb"),
    ("Gaming", "bi-controller"),
    ("Electric Vehicles", "bi-ev-front"),
]

SORT_LABELS = {"publishedAt": "Newest", "relevancy": "Relevance", "popularity": "Popularity"}

# Chart ink per theme (single-series blue from the validated reference palette)
CHART_INK = {
    "light": {"bar": "#2a78d6", "text": "#0b0b0b", "text2": "#52514e", "muted": "#898781",
              "grid": "#e1e0d9", "axis": "#c3c2b7", "tooltip": "#ffffff"},
    "dark": {"bar": "#3987e5", "text": "#ffffff", "text2": "#c3c2b7", "muted": "#898781",
             "grid": "#2c2c2a", "axis": "#383835", "tooltip": "#1a1a19"},
}

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had
has have having he her here hers herself him himself his how i if in into is it its itself just
me more most my myself no nor not now of off on once only or other our ours ourselves out over
own same she should so some such than that the their theirs them themselves then there these
they this those through to too under until up very was we were what when where which while who
whom why will with would you your yours yourself yourselves new says said say get gets got one
two three first last year years day days week weeks time like make makes made may might many
much us via per amid how's it's that's what's who's don't can't won't chars com www http https
""".split())


# ---------------------------------------------------------------- data

def fetch_news(topic, sort_by="publishedAt", page_size=10):
    """Return (articles, error_message). Exactly one of them is meaningful."""

    if not API_KEY:
        return [], "NEWS_API_KEY is missing. Add it to the .env file."

    params = {
        "q": topic,
        "apiKey": API_KEY,
        "language": "en",
        "sortBy": sort_by,
        "pageSize": page_size,
    }

    try:
        response = requests.get(NEWS_URL, params=params, timeout=10)
        data = response.json()
    except requests.RequestException as e:
        return [], f"Could not reach NewsAPI: {e}"
    except ValueError:
        return [], "NewsAPI returned an invalid response."

    if data.get("status") != "ok":
        return [], data.get("message", "Unknown error from NewsAPI.")

    # NewsAPI marks deleted articles with the title "[Removed]"
    articles = [
        a for a in data.get("articles", [])
        if a.get("title") and a["title"] != "[Removed]"
    ]
    return articles, None


def parse_date(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def time_ago(dt):
    if not dt:
        return ""
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"


def source_name(article):
    return (article.get("source") or {}).get("name") or "Unknown"


def top_keywords(articles, topic, n=14):
    exclude = STOPWORDS | set(re.findall(r"[a-z]+", topic.lower()))
    words = Counter()
    for a in articles:
        text = f"{a.get('title') or ''} {a.get('description') or ''}".lower()
        words.update(w for w in re.findall(r"[a-z][a-z'-]{2,}", text) if w not in exclude)
    return [w for w, _ in words.most_common(n)]


# ---------------------------------------------------------------- charts

def chart_layout(theme, **extra):
    ink = CHART_INK[theme]
    layout = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", color=ink["text2"], size=12),
        margin=dict(l=8, r=16, t=8, b=8),
        height=280,
        bargap=0.3,
        showlegend=False,
        hoverlabel=dict(bgcolor=ink["tooltip"], bordercolor=ink["axis"],
                        font=dict(color=ink["text"], family="Inter, system-ui, sans-serif")),
        xaxis=dict(showgrid=False, linecolor=ink["axis"], tickfont=dict(color=ink["muted"])),
        yaxis=dict(gridcolor=ink["grid"], zeroline=False, tickfont=dict(color=ink["muted"])),
    )
    layout.update(extra)
    return layout


def timeline_chart(articles, theme):
    dates = sorted(d for d in (parse_date(a.get("publishedAt")) for a in articles) if d)
    if not dates:
        return None

    hourly = dates[-1] - dates[0] <= timedelta(hours=48)
    step = timedelta(hours=1) if hourly else timedelta(days=1)
    floor = (lambda d: d.replace(minute=0, second=0, microsecond=0)) if hourly else \
            (lambda d: d.replace(hour=0, minute=0, second=0, microsecond=0))

    counts = Counter(floor(d) for d in dates)
    buckets, cur = [], floor(dates[0])
    while cur <= floor(dates[-1]):
        buckets.append(cur)
        cur += step

    fig = go.Figure(go.Bar(
        x=buckets, y=[counts.get(b, 0) for b in buckets],
        marker=dict(color=CHART_INK[theme]["bar"], cornerradius=4),
        hovertemplate=("%{x|%b %d, %H:00}" if hourly else "%{x|%b %d}") +
                      "<br><b>%{y}</b> articles<extra></extra>",
    ))
    fig.update_layout(chart_layout(theme))
    fig.update_xaxes(tickformat="%H:%M<br>%b %d" if hourly else "%b %d")
    fig.update_yaxes(rangemode="tozero", dtick=max(1, max(counts.values()) // 4))
    return fig


def sources_chart(articles, theme):
    top = Counter(source_name(a) for a in articles).most_common(8)[::-1]
    ink = CHART_INK[theme]
    fig = go.Figure(go.Bar(
        x=[c for _, c in top], y=[s for s, _ in top], orientation="h",
        marker=dict(color=ink["bar"], cornerradius=4),
        text=[c for _, c in top], textposition="outside",
        textfont=dict(color=ink["text2"]), cliponaxis=False,
        hovertemplate="%{y}<br><b>%{x}</b> articles<extra></extra>",
    ))
    fig.update_layout(chart_layout(
        theme,
        xaxis=dict(visible=False),
        yaxis=dict(automargin=True, tickfont=dict(color=ink["text2"]), showgrid=False, ticksuffix="  "),
    ))
    return fig


# ---------------------------------------------------------------- components

def chip(label, src, icon=None):
    return html.Button(
        [html.I(className=f"bi {icon}") if icon else None, label],
        id={"type": "chip", "topic": label, "src": src},
        className=f"chip chip-{src}", n_clicks=0,
    )


def stat_tile(icon, label, value, i):
    return html.Div([
        html.Div(html.I(className=f"bi {icon}"), className="stat-icon"),
        html.Div([html.Div(value, className="stat-value"), html.Div(label, className="stat-label")]),
    ], className="stat-tile fade-up", style={"animationDelay": f"{i * 70}ms"})


def panel(title, icon, body, class_name=""):
    return html.Div([
        html.Div([html.I(className=f"bi {icon}"), title], className="panel-title"),
        body,
    ], className=f"panel fade-up {class_name}")


def article_card(article, i):
    title = article["title"]
    image = article.get("urlToImage")
    source = source_name(article)
    media_style = {"backgroundImage": f'url("{image.replace(chr(34), "%22")}")'} if image else {}

    return html.A([
        html.Div([
            html.Span(source[:1].upper(), className="media-letter"),
            html.Div(className="media-img", style=media_style),
            html.Span(source, className="source-badge"),
        ], className="card-media"),
        html.Div([
            html.Div([
                html.I(className="bi bi-clock"),
                time_ago(parse_date(article.get("publishedAt"))),
                html.Span("·", className="dot") if article.get("author") else None,
                html.Span(article.get("author") or "", className="author"),
            ], className="card-meta"),
            html.H3(title, className="card-headline"),
            html.P(article.get("description") or "No description available.", className="card-desc"),
            html.Span(["Read story", html.I(className="bi bi-arrow-up-right")], className="read-more"),
        ], className="card-content"),
    ], href=article.get("url"), target="_blank", rel="noopener noreferrer",
       className="news-card fade-up" + (" featured" if i == 0 else ""),
       style={"animationDelay": f"{min(i, 12) * 60}ms"})


def welcome():
    features = [
        ("bi-search", "Search anything", "Any topic, company or person across thousands of outlets."),
        ("bi-bar-chart-line", "See the trends", "Publishing activity, top sources and keywords at a glance."),
        ("bi-download", "Take it with you", "Export every result to CSV in one click."),
    ]
    return html.Div([
        html.Div([
            html.Div(html.I(className=f"bi {icon}"), className="feature-icon"),
            html.H4(title), html.P(text),
        ], className="feature fade-up", style={"animationDelay": f"{i * 100}ms"})
        for i, (icon, title, text) in enumerate(features)
    ], className="feature-grid")


def message(icon, title, text, tone=""):
    return html.Div([
        html.Div(html.I(className=f"bi {icon}"), className="message-icon"),
        html.H4(title), html.P(text),
    ], className=f"message fade-up {tone}")


# ---------------------------------------------------------------- app

app = Dash(
    __name__,
    title="AI News Analyzer",
    suppress_callback_exceptions=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        dbc.icons.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    ],
)

# Apply the saved / OS theme before first paint to avoid a flash
app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}
<script>
try {
  var t = JSON.parse(localStorage.getItem("theme")) ||
          (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = t;
  document.documentElement.setAttribute("data-bs-theme", t);
} catch (e) {}
</script>
{%css%}
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>"""

app.layout = html.Div([
    dcc.Store(id="theme", storage_type="local"),
    dcc.Store(id="theme-applied"),
    dcc.Store(id="recent", storage_type="local", data=[]),
    dcc.Download(id="download"),
    dcc.Location(id="url", refresh=False),

    html.Div([html.Span(className="orb orb-1"), html.Span(className="orb orb-2"),
              html.Span(className="orb orb-3")], className="bg-orbs"),

    html.Header(html.Div([
        html.Div([
            html.Div(html.I(className="bi bi-broadcast"), className="logo"),
            html.Span(["AI News ", html.B("Analyzer")], className="brand-name"),
        ], className="brand"),
        html.Button([html.I(className="bi bi-moon-stars icon-dark"), html.I(className="bi bi-sun icon-light")],
                    id="theme-toggle", className="icon-btn", title="Toggle theme", n_clicks=0),
    ], className="wrap topbar-inner"), className="topbar"),

    html.Main([
        html.Section([
            html.Div([html.Span(className="live-dot"), "Live headlines from thousands of sources"],
                     className="eyebrow fade-up"),
            html.H1(["Track the stories ", html.Span("shaping the world", className="gradient-text")],
                    className="hero-title fade-up"),
            html.P("Search any topic and get instant analytics on who's covering it, when, and what they're saying.",
                   className="hero-sub fade-up"),

            html.Div([
                html.Div([
                    html.I(className="bi bi-search"),
                    dbc.Input(id="topic", placeholder="Search a topic, e.g. Artificial Intelligence",
                              type="text", autoComplete="off", className="search-input"),
                ], className="search-field"),
                dbc.Select(id="sort-by", value="publishedAt", className="search-select",
                           options=[{"label": v, "value": k} for k, v in SORT_LABELS.items()]),
                dbc.Select(id="page-size", value="20", className="search-select",
                           options=[{"label": f"{n} results", "value": n} for n in ("10", "20", "50", "100")]),
                html.Button([html.Span("Search"), html.I(className="bi bi-arrow-right")],
                            id="search", className="btn-primary-glow", n_clicks=0),
            ], className="search-panel fade-up"),

            html.Div([html.Span("Trending", className="chip-label")] +
                     [chip(t, "quick", icon) for t, icon in QUICK_TOPICS],
                     className="chip-row fade-up"),
            html.Div(id="recent-row", className="chip-row"),
        ], className="hero wrap"),

        dcc.Loading(
            html.Div([dcc.Store(id="results-store"), html.Div(welcome(), id="results")], className="wrap"),
            delay_show=250,
            custom_spinner=html.Div([html.Div(className="loader"), html.P("Fetching headlines…")],
                                    className="loader-wrap"),
            overlay_style={"visibility": "visible", "opacity": 0.35, "filter": "blur(2px)"},
        ),
    ]),

    html.Footer(html.Div([
        html.Span(["Built with ", html.B("Dash"), " · Data from ",
                   html.A("NewsAPI", href="https://newsapi.org", target="_blank")]),
    ], className="wrap"), className="site-footer"),
], className="app-shell")


# ---------------------------------------------------------------- callbacks

app.clientside_callback(
    """function(n) {
        var cur = document.documentElement.dataset.theme;
        return cur === "dark" ? "light" : "dark";
    }""",
    Output("theme", "data"),
    Input("theme-toggle", "n_clicks"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """function(t) {
        t = t || document.documentElement.dataset.theme || "light";
        document.documentElement.dataset.theme = t;
        document.documentElement.setAttribute("data-bs-theme", t);
        return t;
    }""",
    Output("theme-applied", "data"),
    Input("theme", "data"),
)


@app.callback(
    Output("results-store", "data"),
    Output("topic", "value"),
    Output("recent", "data"),
    Output("url", "search"),
    Input("search", "n_clicks"),
    Input("topic", "n_submit"),
    Input({"type": "chip", "topic": ALL, "src": ALL}, "n_clicks"),
    State("topic", "value"),
    State("sort-by", "value"),
    State("page-size", "value"),
    State("recent", "data"),
    State("url", "search"),
)
def search(_clicks, _submits, _chips, topic, sort_by, page_size, recent, url_search):
    if ctx.triggered_id is None:
        # page load: run the search from a shared ?q= link, if any
        topic = parse_qs((url_search or "").lstrip("?")).get("q", [None])[0]
        if not topic:
            raise PreventUpdate
    elif not ctx.triggered[0]["value"]:
        raise PreventUpdate  # chips being (re)rendered, not clicked
    elif isinstance(ctx.triggered_id, dict):
        topic = ctx.triggered_id["topic"]

    topic = (topic or "").strip()
    if not topic:
        return {"error": "Type a topic to search for."}, no_update, no_update, no_update

    articles, error = fetch_news(topic, sort_by, int(page_size))
    recent = [topic] + [r for r in (recent or []) if r.lower() != topic.lower()][:5]

    return ({"topic": topic, "sort": sort_by, "articles": articles, "error": error},
            topic, recent, "?" + urlencode({"q": topic}))


@app.callback(Output("recent-row", "children"), Input("recent", "data"))
def show_recent(recent):
    if not recent:
        return None
    return [html.Span("Recent", className="chip-label")] + [chip(r, "recent", "bi-clock-history") for r in recent]


@app.callback(
    Output("results", "children"),
    Input("results-store", "data"),
    Input("theme-applied", "data"),
)
def render_results(data, theme):
    theme = theme if theme in CHART_INK else "light"

    if not data:
        return welcome()
    if data.get("error"):
        return message("bi-exclamation-triangle", "Something went wrong", data["error"], "error")

    topic, articles = data["topic"], data["articles"]
    if not articles:
        return message("bi-inbox", "No stories found",
                       f'Nothing matched "{topic}". Try a broader or different keyword.')

    dates = [d for d in (parse_date(a.get("publishedAt")) for a in articles) if d]
    span = max(dates) - min(dates) if dates else timedelta(0)
    span_text = f"{span.days}d" if span.days else f"{max(1, round(span.total_seconds() / 3600))}h"
    graph_config = {"displayModeBar": False}
    timeline = timeline_chart(articles, theme)

    return [
        html.Div([
            html.Div([
                html.H2(["Results for ", html.Span(topic, className="gradient-text")]),
                html.P(f"{len(articles)} articles · sorted by {SORT_LABELS[data['sort']].lower()}",
                       className="results-meta"),
            ]),
            html.Button([html.I(className="bi bi-download"), "Export CSV"],
                        id="export", className="btn-ghost", n_clicks=0),
        ], className="results-head fade-up"),

        html.Div([
            stat_tile("bi-newspaper", "Articles", len(articles), 0),
            stat_tile("bi-building", "Sources", len({source_name(a) for a in articles}), 1),
            stat_tile("bi-lightning-charge", "Latest story", time_ago(max(dates)) if dates else "—", 2),
            stat_tile("bi-calendar-range", "Coverage window", span_text, 3),
        ], className="stat-grid"),

        html.Div([
            panel("Publishing activity", "bi-activity",
                  dcc.Graph(figure=timeline, config=graph_config) if timeline else html.P("No dates available.")),
            panel("Top sources", "bi-trophy",
                  dcc.Graph(figure=sources_chart(articles, theme), config=graph_config)),
        ], className="chart-grid"),

        panel("Trending keywords · click to explore", "bi-hash",
              html.Div([chip(k, "kw") for k in top_keywords(articles, topic)], className="chip-row tight")),

        html.Div([article_card(a, i) for i, a in enumerate(articles)], className="news-grid"),
    ]


@app.callback(
    Output("download", "data"),
    Input("export", "n_clicks"),
    State("results-store", "data"),
    prevent_initial_call=True,
)
def export_csv(clicks, data):
    if not clicks or not data or not data.get("articles"):
        raise PreventUpdate
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "source", "author", "published_at", "url", "description"])
    for a in data["articles"]:
        writer.writerow([a.get("title"), source_name(a), a.get("author"), a.get("publishedAt"),
                         a.get("url"), a.get("description")])
    slug = re.sub(r"[^a-z0-9]+", "-", data["topic"].lower()).strip("-")
    return dcc.send_string(buf.getvalue(), f"news-{slug}.csv")


if __name__ == "__main__":
    app.run(debug=True, dev_tools_ui=False)
