"""Streamlit Executive Dashboard — U.S. Telecom Social Listening.

Inspired by Brandwatch / Talkwalker / Meltwater dashboard patterns.
Layout: wide landscape, structured as:
  1. Header & KPIs
  2. Total Conversations / Share of Voice
  3. Sentiment Overview
  4. Top Issues + Platform Breakdown
  5. Topic Word Cloud (treemap) by Brand
  6. Trend Analysis
  7. Taxonomy Breakdown
  8. Competitive Intelligence
  9. Executive Insights

Launch:
    python3 -m streamlit run app/dashboard.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Telecom Social Listening | Procogia",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# Procogia design tokens
# ─────────────────────────────────────────────
BG          = "#FAFAFB"
SURFACE     = "#FFFFFF"
BORDER      = "#E5E7EB"
TEXT        = "#111827"
TEXT_MUTED  = "#6B7280"
ACCENT      = "#1FBBCC"   # Procogia teal
GREEN       = "#95C100"   # Procogia green
SLATE       = "#374151"   # neutral dark
RED         = "#EF4444"

# Per-brand colors
BRAND_COLORS = {
    "T-Mobile US":   ACCENT,
    "Verizon":       SLATE,
    "AT&T Mobility": GREEN,
}

# Pastel palette for stacked/grouped series
PASTEL = ["#BFD7FF", "#BFEFE8", "#D8C7FF", "#FFD7C2", "#FFF1B8"]

# Platform colors
PLATFORM_COLORS = {
    "Reddit":     "#FF4500",
    "Instagram":  "#C13584",
    "AppReview":  "#007AFF",
    "YouTube":    "#FF0000",
    "X":          "#000000",
    "Twitter":    "#1DA1F2",
}

# ─────────────────────────────────────────────
# Global CSS — Procogia Apple-style
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
  html, body, [data-testid="stAppViewContainer"] {{
      background: {BG};
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      color: {TEXT};
  }}
  [data-testid="stSidebar"] {{
      background: {SURFACE};
      border-right: 1px solid {BORDER};
  }}
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stMarkdown p {{
      color: {TEXT_MUTED};
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
  }}
  #MainMenu, footer, header {{ visibility: hidden; }}

  h1 {{
      font-size: 22px !important;
      font-weight: 700 !important;
      letter-spacing: -0.5px;
      color: {TEXT} !important;
      margin-bottom: 2px !important;
  }}
  h2 {{
      font-size: 15px !important;
      font-weight: 700 !important;
      letter-spacing: -0.2px !important;
      color: {TEXT} !important;
      margin-top: 32px !important;
      margin-bottom: 12px !important;
      padding-bottom: 8px !important;
      border-bottom: 1px solid {BORDER} !important;
  }}
  h3 {{
      font-size: 11px !important;
      font-weight: 600 !important;
      letter-spacing: 0.08em !important;
      text-transform: uppercase !important;
      color: {TEXT_MUTED} !important;
      margin-top: 0 !important;
      margin-bottom: 8px !important;
  }}
  hr {{
      border: none;
      border-top: 1px solid {BORDER};
      margin: 20px 0;
  }}
  .kpi-card {{
      background: {SURFACE};
      border: 1px solid {BORDER};
      border-radius: 12px;
      padding: 18px 22px 16px;
      min-height: 90px;
  }}
  .kpi-label {{
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: {TEXT_MUTED};
      margin-bottom: 6px;
  }}
  .kpi-value {{
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -1px;
      color: {TEXT};
      line-height: 1;
  }}
  .kpi-delta {{
      font-size: 11px;
      font-weight: 500;
      color: {TEXT_MUTED};
      margin-top: 5px;
  }}
  .kpi-delta.pos {{ color: {ACCENT}; }}
  .kpi-delta.neg {{ color: {RED}; }}

  .section-card {{
      background: {SURFACE};
      border: 1px solid {BORDER};
      border-radius: 12px;
      padding: 18px 18px 10px;
  }}
  .chart-label {{
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: {TEXT_MUTED};
      margin-bottom: 6px;
  }}
  .issue-item {{
      display: flex;
      align-items: flex-start;
      padding: 10px 0;
      border-bottom: 1px solid {BORDER};
  }}
  .issue-item:last-child {{ border-bottom: none; }}
  .issue-num {{
      font-size: 13px;
      font-weight: 700;
      color: {ACCENT};
      min-width: 24px;
      margin-right: 10px;
      margin-top: 1px;
  }}
  .issue-text {{
      font-size: 13px;
      color: {TEXT};
      line-height: 1.4;
  }}
  .insight-quote {{
      background: {BG};
      border-left: 3px solid {ACCENT};
      border-radius: 0 8px 8px 0;
      padding: 12px 16px;
      font-size: 13px;
      color: {TEXT};
      line-height: 1.6;
      margin-bottom: 10px;
      font-style: italic;
  }}
  .brand-badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-right: 6px;
  }}
  [data-testid="stDataFrame"] {{
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid {BORDER};
  }}
  .stAlert {{ border-radius: 8px; font-size: 13px; }}
  .stTabs [data-baseweb="tab-list"] {{
      background: {BG};
      border-bottom: 1px solid {BORDER};
      gap: 0;
  }}
  .stTabs [data-baseweb="tab"] {{
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: {TEXT_MUTED};
      padding: 8px 18px;
      border-bottom: 2px solid transparent;
  }}
  .stTabs [aria-selected="true"] {{
      color: {ACCENT};
      border-bottom: 2px solid {ACCENT};
  }}
  [data-testid="stSelectbox"] > div > div {{
      border-radius: 8px;
      border-color: {BORDER};
      font-size: 13px;
  }}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Plotly theme helpers
# ─────────────────────────────────────────────
def _layout(**overrides) -> dict:
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                  color=TEXT, size=12),
        margin=dict(t=16, b=16, l=8, r=8),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(size=11, color=TEXT_MUTED),
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=11, color=TEXT_MUTED),
            title_font=dict(size=11, color=TEXT_MUTED),
            linecolor=BORDER,
            tickcolor=BORDER,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=BORDER,
            zeroline=False,
            tickfont=dict(size=11, color=TEXT_MUTED),
            title_font=dict(size=11, color=TEXT_MUTED),
            linecolor="rgba(0,0,0,0)",
        ),
    )
    base.update(overrides)
    return base


def _chart(fig: go.Figure, height: int = 280, **layout_overrides):
    fig.update_layout(**_layout(**layout_overrides))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def kpi(label: str, value: str, delta: str = "", delta_positive: bool | None = None):
    css_class = ""
    if delta_positive is True:
        css_class = "pos"
    elif delta_positive is False:
        css_class = "neg"
    delta_html = f'<div class="kpi-delta {css_class}">{delta}</div>' if delta else ""
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {delta_html}
    </div>
    """, unsafe_allow_html=True)


def chart_label(text: str):
    st.markdown(f'<div class="chart-label">{text}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────
def _get_conn():
    db_path = os.environ.get("DB_PATH", "data/telecom.db")
    return sqlite3.connect(db_path, check_same_thread=False)


@st.cache_data(ttl=300)
def _query(sql: str, params=None) -> pd.DataFrame:
    sql = sql.replace("%s", "?")
    conn = _get_conn()
    return pd.read_sql(sql, conn, params=params)


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="padding:8px 0 18px">
      <div style="font-size:18px;font-weight:700;color:{TEXT};letter-spacing:-0.5px">Procogia</div>
      <div style="font-size:10px;color:{TEXT_MUTED};letter-spacing:0.08em;text-transform:uppercase;margin-top:2px">Telecom Social Listening</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown(f"<hr style='border-color:{BORDER};margin:0 0 16px'>", unsafe_allow_html=True)

    run_df = _query(
        "SELECT run_id, completed_at FROM pipeline_runs "
        "WHERE status='completed' ORDER BY completed_at DESC LIMIT 10"
    )
    if run_df.empty:
        st.warning("No completed pipeline runs found.")
        st.stop()

    run_options = run_df["run_id"].tolist()
    run_labels = {r: f"{r[:8]}… ({t[:10]})" for r, t in zip(run_df["run_id"], run_df["completed_at"].astype(str))}
    selected_run = st.selectbox("Pipeline Run", run_options, format_func=lambda x: run_labels.get(x, x))

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0 12px'>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:10px;color:{TEXT_MUTED}'>Taxonomy v1.0.0 · Schema v1.0.0</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:10px;color:{TEXT_MUTED};margin-top:4px'>Refreshes every 5 min</div>", unsafe_allow_html=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0 12px'>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style='font-size:10px;color:{TEXT_MUTED};line-height:1.8'>
      <div><span style='color:{ACCENT};font-weight:700'>■</span> T-Mobile US (client)</div>
      <div><span style='color:{SLATE};font-weight:700'>■</span> Verizon</div>
      <div><span style='color:{GREEN};font-weight:700'>■</span> AT&amp;T Mobility</div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_metrics(run_id: str) -> pd.DataFrame:
    return _query("SELECT * FROM brand_metrics WHERE pipeline_run_id = ? ORDER BY brand", (run_id,))


@st.cache_data(ttl=300)
def load_trends(run_id: str) -> pd.DataFrame:
    return _query("SELECT * FROM daily_trends WHERE pipeline_run_id = ? ORDER BY trend_date, brand", (run_id,))


@st.cache_data(ttl=300)
def load_topics(run_id: str) -> pd.DataFrame:
    return _query("SELECT * FROM top_topics WHERE pipeline_run_id = ? ORDER BY brand, rank", (run_id,))


@st.cache_data(ttl=300)
def load_insight(run_id: str) -> dict:
    df = _query("SELECT insight_json FROM executive_insights WHERE pipeline_run_id = ?", (run_id,))
    if df.empty:
        return {}
    raw = df["insight_json"].iloc[0]
    return json.loads(raw) if isinstance(raw, str) else raw


@st.cache_data(ttl=300)
def load_run_meta(run_id: str) -> dict:
    df = _query("SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,))
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=300)
def load_platform_data(run_id: str) -> pd.DataFrame:
    return _query(
        "SELECT platform, brand, COUNT(*) as post_count FROM posts "
        "WHERE pipeline_run_id = ? GROUP BY platform, brand ORDER BY platform, brand",
        (run_id,),
    )


@st.cache_data(ttl=300)
def load_sentiment_by_brand(run_id: str) -> pd.DataFrame:
    return _query(
        "SELECT brand, sentiment, COUNT(*) as post_count FROM posts "
        "WHERE pipeline_run_id = ? GROUP BY brand, sentiment",
        (run_id,),
    )


metrics_df   = load_metrics(selected_run)
trends_df    = load_trends(selected_run)
topics_df    = load_topics(selected_run)
insight_data = load_insight(selected_run)
run_meta     = load_run_meta(selected_run)
platform_df  = load_platform_data(selected_run)
sentiment_raw = load_sentiment_by_brand(selected_run)

if metrics_df.empty:
    st.warning("No metrics found for this run.")
    st.stop()


def safe_val(df: pd.DataFrame, col: str, default=0):
    return df[col].iloc[0] if not df.empty and col in df.columns else default


tmobile = metrics_df[metrics_df["brand"] == "T-Mobile US"]
verizon = metrics_df[metrics_df["brand"] == "Verizon"]
att     = metrics_df[metrics_df["brand"] == "AT&T Mobility"]

period_start = run_meta.get("period_start", "")[:10]
period_end   = run_meta.get("period_end", "")[:10]
post_count   = run_meta.get("post_count", 0)


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown(
    f"<h1>Telecom Social Listening Dashboard</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<div style='font-size:13px;color:{TEXT_MUTED};margin-bottom:4px'>"
    f"Client: <strong style='color:{ACCENT}'>T-Mobile US</strong>"
    f"&nbsp;·&nbsp; Competitors: Verizon, AT&T Mobility"
    f"&nbsp;·&nbsp; {period_start} – {period_end}"
    f"&nbsp;·&nbsp; <strong style='color:{TEXT}'>{post_count:,}</strong> posts analysed"
    f"</div>" if isinstance(post_count, int) else
    f"<div style='font-size:13px;color:{TEXT_MUTED};margin-bottom:4px'>"
    f"Client: <strong style='color:{ACCENT}'>T-Mobile US</strong>"
    f"&nbsp;·&nbsp; Competitors: Verizon, AT&T Mobility</div>",
    unsafe_allow_html=True,
)
st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0 20px'>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SECTION 1: TOTAL CONVERSATIONS (7 days)
# ─────────────────────────────────────────────
st.markdown("<h2>Total Conversations (7 Days)</h2>", unsafe_allow_html=True)

total_posts = int(metrics_df["total_posts"].sum())
nss_tm  = safe_val(tmobile, "net_sentiment_score")
nss_vz  = safe_val(verizon, "net_sentiment_score")
nss_att = safe_val(att, "net_sentiment_score")
nss_gap = nss_tm - nss_vz

# KPI row
k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    kpi("Total Posts", f"{total_posts:,}")
with k2:
    kpi("T-Mobile Share",
        f"{safe_val(tmobile, 'conversation_share_pct'):.0f}%",
        delta="Client")
with k3:
    kpi("Verizon Share",
        f"{safe_val(verizon, 'conversation_share_pct'):.0f}%")
with k4:
    kpi("AT&T Share",
        f"{safe_val(att, 'conversation_share_pct'):.0f}%")
with k5:
    kpi("T-Mobile NSS",
        f"{nss_tm:+.1f}",
        delta=f"{nss_gap:+.1f} vs Verizon",
        delta_positive=nss_gap > 0)
with k6:
    kpi("T-Mobile Complaint Rate",
        f"{safe_val(tmobile, 'complaint_pct'):.1f}%",
        delta=f"{safe_val(tmobile,'complaint_pct') - safe_val(verizon,'complaint_pct'):+.1f}pp vs Verizon",
        delta_positive=safe_val(tmobile,'complaint_pct') < safe_val(verizon,'complaint_pct'))

st.markdown("<br>", unsafe_allow_html=True)

# Conversation share donut + NSS bar side by side
c1a, c1b = st.columns([1, 1])
with c1a:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Share of Voice")
    fig = px.pie(
        metrics_df,
        names="brand", values="total_posts",
        color="brand", color_discrete_map=BRAND_COLORS,
        hole=0.56,
    )
    fig.update_traces(
        textinfo="label+percent",
        textfont=dict(size=12, color=TEXT),
        marker=dict(line=dict(color=SURFACE, width=3)),
    )
    fig.update_layout(showlegend=False, **_layout(margin=dict(t=10, b=10, l=8, r=8)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

with c1b:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Net Sentiment Score by Brand")
    nss_df = metrics_df[["brand", "net_sentiment_score"]].copy()
    fig = go.Figure(go.Bar(
        x=nss_df["brand"],
        y=nss_df["net_sentiment_score"],
        marker_color=[BRAND_COLORS.get(b, SLATE) for b in nss_df["brand"]],
        marker_line_width=0,
        text=nss_df["net_sentiment_score"].apply(lambda x: f"{x:+.1f}"),
        textposition="outside",
        textfont=dict(size=13, color=TEXT, family="-apple-system, sans-serif"),
    ))
    fig.add_hline(y=0, line_dash="dot", line_color=BORDER, line_width=1)
    _chart(fig, yaxis_title="NSS (Positive% − Negative%)", xaxis_title="")
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SECTION 2: SENTIMENT OVERVIEW
# ─────────────────────────────────────────────
st.markdown("<h2>Sentiment Trend</h2>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-size:12px;color:{TEXT_MUTED};margin-bottom:12px'>"
    f"<strong style='color:{RED}'>Negative</strong> &nbsp;|&nbsp; "
    f"<strong style='color:{TEXT_MUTED}'>Neutral</strong> &nbsp;|&nbsp; "
    f"<strong style='color:{GREEN}'>Positive</strong>"
    f"</div>",
    unsafe_allow_html=True,
)

s1, s2 = st.columns([2, 1])

with s1:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("7-Day Net Sentiment Trend")
    if not trends_df.empty:
        fig = px.line(
            trends_df,
            x="trend_date", y="net_sentiment_score",
            color="brand", color_discrete_map=BRAND_COLORS,
            markers=True,
            labels={"net_sentiment_score": "NSS", "trend_date": "", "brand": ""},
        )
        fig.add_hline(y=0, line_dash="dot", line_color=BORDER, line_width=1)
        fig.update_traces(line=dict(width=2.5), marker=dict(size=7))
        _chart(fig)
    else:
        st.info("No trend data available.")
    st.markdown("</div>", unsafe_allow_html=True)

with s2:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Sentiment Distribution by Brand")
    if not sentiment_raw.empty:
        sentiment_colors = {"Positive": GREEN, "Neutral": TEXT_MUTED, "Negative": RED}
        fig = px.bar(
            sentiment_raw,
            x="brand", y="post_count",
            color="sentiment",
            color_discrete_map=sentiment_colors,
            barmode="stack",
            labels={"post_count": "Posts", "brand": "", "sentiment": ""},
        )
        fig.update_traces(marker_line_width=0)
        _chart(fig)
    else:
        # Fallback from brand_metrics
        sent_cols = ["brand", "positive_pct", "neutral_pct", "negative_pct"]
        sdf = metrics_df[sent_cols].melt(id_vars="brand", var_name="sentiment", value_name="pct")
        sdf["sentiment"] = sdf["sentiment"].str.replace("_pct", "").str.capitalize()
        fig = px.bar(
            sdf, x="brand", y="pct", color="sentiment",
            barmode="stack",
            color_discrete_map={"Positive": GREEN, "Neutral": TEXT_MUTED, "Negative": RED},
            labels={"pct": "% Posts", "brand": "", "sentiment": ""},
        )
        fig.update_traces(marker_line_width=0)
        _chart(fig)
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SECTION 3: TOP ISSUES + PLATFORM BREAKDOWN
# ─────────────────────────────────────────────
st.markdown("<h2>Top Issues & Platform Breakdown</h2>", unsafe_allow_html=True)
i1, i2 = st.columns([1, 1])

with i1:
    st.markdown("<div class='section-card' style='min-height:300px'>", unsafe_allow_html=True)
    chart_label("Top Issues (by Conversation Volume)")

    # Build top issues from topics: aggregate by pillar/category
    if not topics_df.empty:
        top_issues = (
            topics_df.groupby("topic", as_index=False)["post_count"]
            .sum()
            .sort_values("post_count", ascending=False)
            .head(8)
            .reset_index(drop=True)
        )
        html_issues = ""
        for i, row in top_issues.iterrows():
            # Truncate long topic names
            topic_text = row["topic"]
            if len(topic_text) > 80:
                topic_text = topic_text[:77] + "…"
            html_issues += f"""
            <div class="issue-item">
              <div class="issue-num">{i + 1}</div>
              <div class="issue-text">{topic_text}
                <span style="color:{TEXT_MUTED};font-size:11px;margin-left:6px">{int(row['post_count'])} posts</span>
              </div>
            </div>"""
        st.markdown(html_issues, unsafe_allow_html=True)
    else:
        st.info("No topic data available.")
    st.markdown("</div>", unsafe_allow_html=True)

with i2:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Platform Breakdown")
    if not platform_df.empty:
        plat_total = platform_df.groupby("platform", as_index=False)["post_count"].sum()
        plat_colors = [PLATFORM_COLORS.get(p, ACCENT) for p in plat_total["platform"]]
        fig = go.Figure(go.Bar(
            y=plat_total["platform"],
            x=plat_total["post_count"],
            orientation="h",
            marker_color=plat_colors,
            marker_line_width=0,
            text=plat_total["post_count"],
            textposition="outside",
            textfont=dict(size=12, color=TEXT),
        ))
        _chart(fig, xaxis_title="Posts", yaxis_title="",
               margin=dict(t=10, b=10, l=70, r=40),
               yaxis=dict(showgrid=False, tickfont=dict(size=12, color=TEXT)))
    else:
        st.info("No platform data.")

    # Platform × Brand breakdown
    if not platform_df.empty:
        st.markdown(f"<div style='font-size:10px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:{TEXT_MUTED};margin:12px 0 6px'>By Brand</div>", unsafe_allow_html=True)
        fig2 = px.bar(
            platform_df,
            x="platform", y="post_count",
            color="brand", barmode="group",
            color_discrete_map=BRAND_COLORS,
            labels={"post_count": "Posts", "platform": "", "brand": ""},
        )
        fig2.update_traces(marker_line_width=0)
        _chart(fig2, margin=dict(t=6, b=10, l=8, r=8))
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SECTION 4: TOPIC WORD CLOUD (Treemap) by Brand
# ─────────────────────────────────────────────
st.markdown("<h2>Common Topics by Brand</h2>", unsafe_allow_html=True)

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "need",
    "vs", "vs.", "due", "per", "via", "than", "into", "up", "after",
    "over", "its", "their", "my", "your", "our", "his", "her", "this",
    "that", "these", "those", "it", "he", "she", "they", "we", "i",
    "not", "no", "if", "then", "so", "yet", "both", "either", "nor",
    "while", "about", "against", "between", "under", "through", "during",
    "before", "between", "without", "around",
}


def extract_keywords(topics_series: pd.Series, weights: pd.Series | None = None) -> pd.DataFrame:
    """Extract word frequencies from topic strings for treemap/word-cloud."""
    freq: dict[str, float] = {}
    for i, topic in enumerate(topics_series):
        w = float(weights.iloc[i]) if weights is not None else 1.0
        words = re.findall(r"[a-zA-Z]{3,}", str(topic).lower())
        for word in words:
            if word not in STOP_WORDS:
                freq[word] = freq.get(word, 0) + w
    df = pd.DataFrame({"word": list(freq.keys()), "count": list(freq.values())})
    return df.sort_values("count", ascending=False).head(40)


brand_tabs = st.tabs(["T-Mobile US", "Verizon", "AT&T Mobility"])
for tab, brand_name, brand_color in zip(
    brand_tabs,
    ["T-Mobile US", "Verizon", "AT&T Mobility"],
    [ACCENT, SLATE, GREEN],
):
    with tab:
        bdf = topics_df[topics_df["brand"] == brand_name].copy()
        if bdf.empty:
            st.info(f"No topic data for {brand_name}")
            continue

        kw_df = extract_keywords(bdf["topic"], weights=bdf["post_count"])
        if kw_df.empty:
            st.info("No keywords extracted.")
            continue

        # Treemap as word cloud substitute
        fig = px.treemap(
            kw_df,
            path=["word"],
            values="count",
            color="count",
            color_continuous_scale=[[0, "#F0F9FA"], [1, brand_color]],
        )
        fig.update_traces(
            textfont=dict(size=14, family="-apple-system, BlinkMacSystemFont, sans-serif"),
            marker=dict(line=dict(width=1, color=SURFACE)),
        )
        fig.update_coloraxes(showscale=False)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=10, l=4, r=4),
            height=260,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────
# SECTION 5: TREND ANALYSIS
# ─────────────────────────────────────────────
st.markdown("<h2>Trend Analysis (7 Days)</h2>", unsafe_allow_html=True)

t1, t2 = st.columns(2)

with t1:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Conversation Volume Trend")
    if not trends_df.empty:
        fig = px.line(
            trends_df, x="trend_date", y="post_count",
            color="brand", color_discrete_map=BRAND_COLORS,
            markers=True,
            labels={"post_count": "Posts", "trend_date": "", "brand": ""},
        )
        fig.update_traces(line=dict(width=2.5), marker=dict(size=7))
        _chart(fig)
    else:
        st.info("No trend data.")
    st.markdown("</div>", unsafe_allow_html=True)

with t2:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Complaint Trend")
    if not trends_df.empty:
        fig = px.area(
            trends_df, x="trend_date", y="complaint_pct",
            color="brand", color_discrete_map=BRAND_COLORS,
            labels={"complaint_pct": "Complaint %", "trend_date": "", "brand": ""},
            line_group="brand",
        )
        fig.update_traces(line=dict(width=1.5))
        _chart(fig)
    else:
        st.info("No trend data.")
    st.markdown("</div>", unsafe_allow_html=True)

t3, t4 = st.columns(2)

with t3:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Frustration vs Satisfaction Trend")
    if not trends_df.empty:
        emotion_trend_df = trends_df.melt(
            id_vars=["trend_date", "brand"],
            value_vars=["frustration_pct", "satisfaction_pct"],
            var_name="emotion", value_name="pct",
        )
        emotion_trend_df["emotion"] = emotion_trend_df["emotion"].str.replace("_pct", "").str.capitalize()
        fig = px.line(
            emotion_trend_df,
            x="trend_date", y="pct",
            color="brand", line_dash="emotion",
            color_discrete_map=BRAND_COLORS,
            markers=True,
            labels={"pct": "% Posts", "trend_date": "", "brand": "", "emotion": ""},
        )
        fig.update_traces(line=dict(width=2), marker=dict(size=6))
        _chart(fig)
    else:
        st.info("No trend data.")
    st.markdown("</div>", unsafe_allow_html=True)

with t4:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    chart_label("Intent & Emotion Distribution")
    intent_df = metrics_df[["brand", "complaint_pct", "inquiry_pct", "praise_pct", "recommendation_pct"]].melt(
        id_vars="brand", var_name="intent", value_name="pct"
    )
    intent_df["intent"] = intent_df["intent"].str.replace("_pct", "").str.capitalize()
    fig = px.bar(
        intent_df, x="brand", y="pct", color="intent",
        barmode="group", color_discrete_sequence=PASTEL,
        labels={"pct": "% Posts", "brand": "", "intent": ""},
    )
    fig.update_traces(marker_line_width=0)
    _chart(fig)
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SECTION 6: TAXONOMY BREAKDOWN
# ─────────────────────────────────────────────
st.markdown("<h2>Topic Taxonomy</h2>", unsafe_allow_html=True)

if not topics_df.empty:
    tax1, tax2 = st.columns([1, 1])

    with tax1:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        chart_label("Topic Volume by Pillar")
        pillar_df = topics_df.groupby(["brand", "pillar"], as_index=False)["post_count"].sum()
        fig = px.bar(
            pillar_df, x="pillar", y="post_count",
            color="brand", barmode="group",
            color_discrete_map=BRAND_COLORS,
            labels={"post_count": "Posts", "pillar": "", "brand": ""},
        )
        fig.update_traces(marker_line_width=0)
        _chart(fig, xaxis_tickangle=-15)
        st.markdown("</div>", unsafe_allow_html=True)

    with tax2:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        chart_label("Top Topics per Brand")
        brand_tab_topics = st.tabs(["T-Mobile US", "Verizon", "AT&T Mobility"])
        for tab, brand_name in zip(brand_tab_topics, ["T-Mobile US", "Verizon", "AT&T Mobility"]):
            with tab:
                bdf = topics_df[topics_df["brand"] == brand_name].head(8).copy()
                if bdf.empty:
                    st.info(f"No data for {brand_name}")
                    continue
                display = bdf[["rank", "pillar", "topic", "post_count", "topic_share_pct", "is_emerging"]].copy()
                display.columns = ["#", "Pillar", "Topic", "Posts", "Share%", "New"]
                display["New"] = display["New"].map({True: "★", False: "", 1: "★", 0: ""})
                display["Share%"] = display["Share%"].apply(lambda x: f"{x:.1f}%")
                st.dataframe(display, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Category drill-down
    pillars = sorted(topics_df["pillar"].unique().tolist())
    sel_pillar = st.selectbox("Drill down by Pillar → Category", pillars, key="pillar_select")
    cat_df = (
        topics_df[topics_df["pillar"] == sel_pillar]
        .groupby(["brand", "category"], as_index=False)["post_count"].sum()
    )
    if not cat_df.empty:
        fig = px.bar(
            cat_df, x="category", y="post_count",
            color="brand", barmode="group",
            color_discrete_map=BRAND_COLORS,
            labels={"post_count": "Posts", "category": "", "brand": ""},
            title=f"Category Breakdown — {sel_pillar}",
        )
        fig.update_traces(marker_line_width=0)
        fig.update_layout(title_font=dict(size=12, color=TEXT_MUTED), title_x=0)
        _chart(fig)

    # Emotion heatmap
    st.markdown("<div class='section-card' style='margin-top:0'>", unsafe_allow_html=True)
    chart_label("Emotion Heatmap by Brand")
    emotion_cols   = ["frustration_pct", "satisfaction_pct", "confusion_pct", "excitement_pct"]
    emotion_labels = ["Frustration", "Satisfaction", "Confusion", "Excitement"]
    heat_data = metrics_df.set_index("brand")[emotion_cols].rename(
        columns=dict(zip(emotion_cols, emotion_labels))
    )
    fig = px.imshow(
        heat_data,
        color_continuous_scale=[[0, "#F0FDF4"], [0.5, "#8FDDEA"], [1, ACCENT]],
        text_auto=".1f",
        aspect="auto",
        labels={"color": "%"},
    )
    fig.update_coloraxes(showscale=False)
    fig.update_traces(textfont=dict(size=13, color=TEXT))
    _chart(fig)
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SECTION 7: COMPETITIVE INTELLIGENCE
# ─────────────────────────────────────────────
st.markdown("<h2>Competitive Intelligence</h2>", unsafe_allow_html=True)
comp_data = []
for comp in ["Verizon", "AT&T Mobility"]:
    comp_row = metrics_df[metrics_df["brand"] == comp]
    if comp_row.empty:
        continue
    nss_gap_c     = safe_val(tmobile, "net_sentiment_score") - safe_val(comp_row, "net_sentiment_score")
    complaint_gap = safe_val(tmobile, "complaint_pct") - safe_val(comp_row, "complaint_pct")
    comp_data.append({
        "Competitor":        comp,
        "T-Mobile NSS":      f"{safe_val(tmobile, 'net_sentiment_score'):+.1f}",
        f"{comp} NSS":       f"{safe_val(comp_row, 'net_sentiment_score'):+.1f}",
        "NSS Gap":           f"{nss_gap_c:+.1f}",
        "Complaint Gap":     f"{complaint_gap:+.1f}pp",
        "T-Mobile Praise":   f"{safe_val(tmobile, 'praise_pct'):.1f}%",
        f"{comp} Praise":    f"{safe_val(comp_row, 'praise_pct'):.1f}%",
        "Verdict":           "T-Mobile leads" if nss_gap_c > 0 else "T-Mobile trails",
    })
if comp_data:
    st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# SECTION 8: EXECUTIVE INSIGHTS
# ─────────────────────────────────────────────
st.markdown("<h2>Executive Insights</h2>", unsafe_allow_html=True)

if insight_data:
    ei1, ei2 = st.columns([1, 1])

    with ei1:
        chart_label("Top Complaints")
        for item in insight_data.get("top_complaints", [])[:4]:
            st.markdown(
                f'<div class="insight-quote">'
                f'<strong style="color:{TEXT};font-style:normal">{item.get("topic","")}</strong>'
                f'<span style="color:{TEXT_MUTED};font-size:11px;font-style:normal;margin-left:8px">'
                f'{item.get("complaint_pct",0):.1f}% complaint rate</span>'
                f'<div style="margin-top:6px;font-size:12px">{item.get("context","")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        chart_label("Emerging Topics")
        for item in insight_data.get("emerging_topics", [])[:3]:
            brands_str = ", ".join(item.get("brands_affected", []))
            st.markdown(
                f'<div style="background:{SURFACE};border:1px solid {BORDER};border-left:3px solid {ACCENT};'
                f'border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px;font-size:13px">'
                f'<strong style="color:{TEXT}">{item.get("topic","")}</strong>'
                f'<span style="color:{TEXT_MUTED};font-size:10px;margin-left:8px;text-transform:uppercase;'
                f'letter-spacing:0.05em">[{brands_str}]</span>'
                f'<div style="color:{TEXT_MUTED};font-size:12px;margin-top:4px">{item.get("growth_note","")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with ei2:
        gaps = insight_data.get("sentiment_gaps", {})
        if gaps and gaps.get("narrative"):
            chart_label("Sentiment Narrative")
            st.markdown(
                f'<div class="insight-quote">'
                f'"{gaps.get("narrative","")}"'
                f'</div>',
                unsafe_allow_html=True,
            )

        recs = insight_data.get("strategic_recommendations", [])
        if recs:
            chart_label("Strategic Recommendations")
            for rec in recs:
                st.markdown(
                    f'<div style="background:{SURFACE};border:1px solid {BORDER};border-left:3px solid {GREEN};'
                    f'border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px;font-size:13px;color:{TEXT}">'
                    f'→ {rec}</div>',
                    unsafe_allow_html=True,
                )
else:
    st.info("No executive brief available for this run.")


# ─────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────
st.markdown(f"<hr style='border-color:{BORDER};margin:32px 0 16px'>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-size:11px;color:{TEXT_MUTED};text-align:center;padding-bottom:24px'>"
    f"Powered by Claude (claude-sonnet-4-6) &nbsp;·&nbsp; Procogia &nbsp;·&nbsp; "
    f"Inspired by Brandwatch, Talkwalker, Meltwater &nbsp;·&nbsp; Data refreshes every 5 min"
    f"</div>",
    unsafe_allow_html=True,
)
