"""Streamlit Executive Dashboard — U.S. Telecom Social Listening.

Launch:
    python3 -m streamlit run app/dashboard.py
"""
from __future__ import annotations

import json
import os
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
ACCENT      = "#1FBBCC"
GREEN       = "#95C100"
SLATE       = "#374151"
RED         = "#EF4444"

BRAND_COLORS = {
    "T-Mobile US":   ACCENT,
    "Verizon":       SLATE,
    "AT&T Mobility": GREEN,
}
PASTEL = ["#BFD7FF", "#BFEFE8", "#D8C7FF", "#FFD7C2", "#FFF1B8"]
PLATFORM_COLORS = {
    "Reddit":    "#FF4500",
    "Instagram": "#C13584",
    "AppReview": "#007AFF",
    "YouTube":   "#FF0000",
    "X":         "#000000",
    "Twitter":   "#1DA1F2",
}

# ─────────────────────────────────────────────
# Global CSS
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
  html, body, [data-testid="stAppViewContainer"] {{
      background: {BG};
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      color: {TEXT};
  }}
  .block-container {{
      padding-top: 1rem !important;
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
  hr {{ border: none; border-top: 1px solid {BORDER}; margin: 20px 0; }}
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
# Helpers
# ─────────────────────────────────────────────
def _layout(**overrides) -> dict:
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                  color=TEXT, size=12),
        margin=dict(t=16, b=16, l=8, r=8),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
                    font=dict(size=11, color=TEXT_MUTED)),
        xaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=11, color=TEXT_MUTED),
                   title_font=dict(size=11, color=TEXT_MUTED),
                   linecolor=BORDER, tickcolor=BORDER),
        yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=11, color=TEXT_MUTED),
                   title_font=dict(size=11, color=TEXT_MUTED),
                   linecolor="rgba(0,0,0,0)"),
    )
    base.update(overrides)
    return base


def _chart(fig: go.Figure, height: int = 280, **layout_overrides):
    fig.update_layout(height=height, **_layout(**layout_overrides))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def kpi(label: str, value: str, delta: str = "", delta_positive: bool | None = None):
    css = ""
    if delta_positive is True:
        css = "pos"
    elif delta_positive is False:
        css = "neg"
    delta_html = f'<div class="kpi-delta {css}">{delta}</div>' if delta else ""
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {delta_html}
    </div>
    """, unsafe_allow_html=True)


def chart_label(text: str):
    st.markdown(f'<div class="chart-label">{text}</div>', unsafe_allow_html=True)


def safe_val(df: pd.DataFrame, col: str, default=0):
    return df[col].iloc[0] if not df.empty and col in df.columns else default


# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────
def _get_conn():
    db_path = os.environ.get("DB_PATH", "data/telecom.db")
    return sqlite3.connect(db_path, check_same_thread=False)


@st.cache_data(ttl=300)
def _query(sql: str, params=None) -> pd.DataFrame:
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
    run_labels  = {r: f"{r[:8]}… ({t[:10]})" for r, t in zip(run_df["run_id"], run_df["completed_at"].astype(str))}
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
# Data loaders
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
def load_platform_data(run_id: str, cutoff: str | None = None) -> pd.DataFrame:
    if cutoff:
        return _query(
            "SELECT platform, brand, COUNT(*) as post_count FROM posts "
            "WHERE pipeline_run_id = ? AND DATE(timestamp) >= ? "
            "GROUP BY platform, brand ORDER BY platform, brand",
            (run_id, cutoff),
        )
    return _query(
        "SELECT platform, brand, COUNT(*) as post_count FROM posts "
        "WHERE pipeline_run_id = ? GROUP BY platform, brand ORDER BY platform, brand",
        (run_id,),
    )

@st.cache_data(ttl=300)
def load_sentiment_by_brand(run_id: str, cutoff: str | None = None) -> pd.DataFrame:
    if cutoff:
        return _query(
            "SELECT brand, sentiment, COUNT(*) as post_count FROM posts "
            "WHERE pipeline_run_id = ? AND DATE(timestamp) >= ? GROUP BY brand, sentiment",
            (run_id, cutoff),
        )
    return _query(
        "SELECT brand, sentiment, COUNT(*) as post_count FROM posts "
        "WHERE pipeline_run_id = ? GROUP BY brand, sentiment",
        (run_id,),
    )

@st.cache_data(ttl=300)
def load_taxonomy_trend(run_id: str) -> pd.DataFrame:
    """Posts grouped by date × brand × pillar × category for trend charts."""
    return _query(
        "SELECT DATE(timestamp) as date, brand, pillar, category, theme, COUNT(*) as post_count "
        "FROM posts WHERE pipeline_run_id = ? AND timestamp IS NOT NULL "
        "GROUP BY DATE(timestamp), brand, pillar, category, theme",
        (run_id,),
    )


@st.cache_data(ttl=300)
def load_filtered_brand_metrics(run_id: str, cutoff: str | None = None) -> pd.DataFrame:
    """Compute brand-level metrics from posts table, optionally filtered by date cutoff."""
    base = (
        "FROM posts "
        "WHERE pipeline_run_id = ? "
        "AND classification_status IN ('success', 'flagged')"
    )
    params: list = [run_id]
    if cutoff:
        base += " AND DATE(timestamp) >= ?"
        params.append(cutoff)
    sql = f"""
        SELECT
            brand,
            COUNT(*) AS total_posts,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS conversation_share_pct,
            ROUND(100.0 * SUM(CASE WHEN sentiment='Positive' THEN 1 ELSE 0 END) / COUNT(*), 1) AS positive_pct,
            ROUND(100.0 * SUM(CASE WHEN sentiment='Neutral'  THEN 1 ELSE 0 END) / COUNT(*), 1) AS neutral_pct,
            ROUND(100.0 * SUM(CASE WHEN sentiment='Negative' THEN 1 ELSE 0 END) / COUNT(*), 1) AS negative_pct,
            ROUND(
                100.0 * SUM(CASE WHEN sentiment='Positive' THEN 1 ELSE 0 END) / COUNT(*) -
                100.0 * SUM(CASE WHEN sentiment='Negative' THEN 1 ELSE 0 END) / COUNT(*), 1
            ) AS net_sentiment_score,
            ROUND(100.0 * SUM(CASE WHEN intent='Complaint'      THEN 1 ELSE 0 END) / COUNT(*), 1) AS complaint_pct,
            ROUND(100.0 * SUM(CASE WHEN intent='Inquiry'        THEN 1 ELSE 0 END) / COUNT(*), 1) AS inquiry_pct,
            ROUND(100.0 * SUM(CASE WHEN intent='Praise'         THEN 1 ELSE 0 END) / COUNT(*), 1) AS praise_pct,
            ROUND(100.0 * SUM(CASE WHEN intent='Recommendation' THEN 1 ELSE 0 END) / COUNT(*), 1) AS recommendation_pct,
            ROUND(100.0 * SUM(CASE WHEN emotion='Frustration'   THEN 1 ELSE 0 END) / COUNT(*), 1) AS frustration_pct,
            ROUND(100.0 * SUM(CASE WHEN emotion='Satisfaction'  THEN 1 ELSE 0 END) / COUNT(*), 1) AS satisfaction_pct,
            ROUND(100.0 * SUM(CASE WHEN emotion='Confusion'     THEN 1 ELSE 0 END) / COUNT(*), 1) AS confusion_pct,
            ROUND(100.0 * SUM(CASE WHEN emotion='Excitement'    THEN 1 ELSE 0 END) / COUNT(*), 1) AS excitement_pct
        {base}
        GROUP BY brand
        ORDER BY brand
    """
    return _query(sql, tuple(params))


@st.cache_data(ttl=300)
def load_filtered_topics(run_id: str, cutoff: str | None = None) -> pd.DataFrame:
    """Compute topic breakdown from posts table, optionally filtered by date cutoff."""
    base = (
        "FROM posts "
        "WHERE pipeline_run_id = ? "
        "AND classification_status IN ('success', 'flagged') "
        "AND pillar != 'Uncategorized'"
    )
    params: list = [run_id]
    if cutoff:
        base += " AND DATE(timestamp) >= ?"
        params.append(cutoff)
    sql = f"""
        SELECT
            brand, pillar, category, theme, topic,
            COUNT(*) AS post_count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY brand), 2) AS topic_share_pct,
            0 AS is_emerging,
            ROW_NUMBER() OVER (PARTITION BY brand ORDER BY COUNT(*) DESC) AS rank
        {base}
        GROUP BY brand, pillar, category, theme, topic
        ORDER BY brand, post_count DESC
    """
    return _query(sql, tuple(params))


# ─────────────────────────────────────────────
# Load run_meta early — needed for header dates
# ─────────────────────────────────────────────
run_meta     = load_run_meta(selected_run)
period_start = run_meta.get("period_start", "")[:10]
period_end   = run_meta.get("period_end", "")[:10]


# ─────────────────────────────────────────────
# HEADER  +  inline time period filter
# (must appear before all other data loads so
#  cutoff_date is known when queries run)
# ─────────────────────────────────────────────
PERIOD_OPTIONS = {
    "Last 7 Days":  7,
    "Last 15 Days": 15,
    "Last 30 Days": 30,
    "Last 60 Days": 60,
    "Max":          None,
}

head_col, filter_col = st.columns([5, 1])
with head_col:
    st.markdown("<h1>Telecom Social Listening Dashboard</h1>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:13px;color:{TEXT_MUTED};margin-bottom:4px'>"
        f"Client: <strong style='color:{ACCENT}'>T-Mobile US</strong>"
        f"&nbsp;·&nbsp; Competitors: Verizon, AT&T Mobility"
        f"&nbsp;·&nbsp; {period_start} – {period_end}"
        f"</div>",
        unsafe_allow_html=True,
    )
with filter_col:
    st.markdown(
        f"<div style='font-size:10px;font-weight:600;letter-spacing:0.08em;"
        f"text-transform:uppercase;color:{TEXT_MUTED};margin-bottom:4px'>Time Period</div>",
        unsafe_allow_html=True,
    )
    selected_period = st.selectbox(
        "Time Period",
        list(PERIOD_OPTIONS.keys()),
        index=4,
        label_visibility="collapsed",
        key="time_period",
    )

# Compute cutoff date from selection
_period_days = PERIOD_OPTIONS[selected_period]
_period_end_dt = pd.to_datetime(period_end) if period_end else pd.Timestamp.now()
cutoff_date: str | None = (
    (_period_end_dt - pd.Timedelta(days=_period_days)).strftime("%Y-%m-%d")
    if _period_days else None
)

# ─────────────────────────────────────────────
# Load all data — queries use cutoff_date
# ─────────────────────────────────────────────
metrics_df   = load_filtered_brand_metrics(selected_run, cutoff_date)
trends_df    = load_trends(selected_run)
topics_df    = load_filtered_topics(selected_run, cutoff_date)
insight_data = load_insight(selected_run)
tax_trend_df = load_taxonomy_trend(selected_run)
platform_df  = load_platform_data(selected_run, cutoff_date)
sentiment_raw = load_sentiment_by_brand(selected_run, cutoff_date)

if metrics_df.empty:
    st.warning("No metrics found for this run.")
    st.stop()

tmobile = metrics_df[metrics_df["brand"] == "T-Mobile US"]
verizon = metrics_df[metrics_df["brand"] == "Verizon"]
att     = metrics_df[metrics_df["brand"] == "AT&T Mobility"]

post_count = int(metrics_df["total_posts"].sum())
nss_tm  = safe_val(tmobile, "net_sentiment_score")
nss_vz  = safe_val(verizon, "net_sentiment_score")
nss_att = safe_val(att, "net_sentiment_score")

# Filter in-memory trend frames by cutoff
if cutoff_date and not trends_df.empty:
    _cutoff_ts = pd.to_datetime(cutoff_date)
    trends_filt = trends_df[pd.to_datetime(trends_df["trend_date"]) >= _cutoff_ts].copy()
else:
    trends_filt = trends_df.copy()

if cutoff_date and not tax_trend_df.empty:
    _cutoff_ts = pd.to_datetime(cutoff_date)
    tax_trend_filt = tax_trend_df[pd.to_datetime(tax_trend_df["date"]) >= _cutoff_ts].copy()
else:
    tax_trend_filt = tax_trend_df.copy()

st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0 20px'>", unsafe_allow_html=True)

total_posts   = int(metrics_df["total_posts"].sum())
tm_share      = safe_val(tmobile, "conversation_share_pct")
tm_nss        = safe_val(tmobile, "net_sentiment_score")
tm_complaint  = safe_val(tmobile, "complaint_pct")
nss_gap_vz    = nss_tm - nss_vz

# ─────────────────────────────────────────────
# 7-TAB LAYOUT
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "T-Mobile US — At a Glance",
    "Brand Sentiment",
    "Categories & Platforms",
    "Trend Analysis",
    "Taxonomy Breakdown",
    "Topics & Competitive Intel",
    "Executive Insights",
])


# ── TAB 1: T-MOBILE US — AT A GLANCE ─────────────────────────────────────────
with tab1:
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi("Total Posts (All Brands)", f"{total_posts:,}")
    with k2:
        kpi(
            "T-Mobile Conversation Share",
            f"{tm_share:.0f}%",
            delta=f"{tm_share - safe_val(verizon,'conversation_share_pct'):+.1f}pp vs Verizon",
            delta_positive=tm_share >= safe_val(verizon, "conversation_share_pct"),
        )
    with k3:
        kpi(
            "T-Mobile NSS",
            f"{tm_nss:+.1f}",
            delta=f"{nss_gap_vz:+.1f} pts vs Verizon",
            delta_positive=nss_gap_vz > 0,
        )
    with k4:
        complaint_gap = tm_complaint - safe_val(verizon, "complaint_pct")
        kpi(
            "T-Mobile Complaint Rate",
            f"{tm_complaint:.1f}%",
            delta=f"{complaint_gap:+.1f}pp vs Verizon",
            delta_positive=complaint_gap < 0,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Competitive Intelligence ───────────────────────────────────────────
    chart_label("Competitive Intelligence")
    comp_data_glance = []
    for comp in ["Verizon", "AT&T Mobility"]:
        comp_row = metrics_df[metrics_df["brand"] == comp]
        if comp_row.empty:
            continue
        nss_gap_c     = safe_val(tmobile, "net_sentiment_score") - safe_val(comp_row, "net_sentiment_score")
        complaint_gap = safe_val(tmobile, "complaint_pct") - safe_val(comp_row, "complaint_pct")
        comp_data_glance.append({
            "Competitor":       comp,
            "T-Mobile NSS":     f"{safe_val(tmobile,'net_sentiment_score'):+.1f}",
            f"{comp} NSS":      f"{safe_val(comp_row,'net_sentiment_score'):+.1f}",
            "NSS Gap":          f"{nss_gap_c:+.1f}",
            "Complaint Gap":    f"{complaint_gap:+.1f}pp",
            "T-Mobile Praise":  f"{safe_val(tmobile,'praise_pct'):.1f}%",
            f"{comp} Praise":   f"{safe_val(comp_row,'praise_pct'):.1f}%",
            "Verdict":          "T-Mobile leads" if nss_gap_c > 0 else "T-Mobile trails",
        })
    if comp_data_glance:
        st.dataframe(pd.DataFrame(comp_data_glance), use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Strategic Recommendations ─────────────────────────────────────────
    if insight_data:
        recs = insight_data.get("strategic_recommendations", [])
        if recs:
            chart_label("Strategic Recommendations")
            labels = ["IMMEDIATE", "SHORT-TERM", "STRATEGIC"]
            colors = [RED, ACCENT, GREEN]
            for i, rec in enumerate(recs[:3]):
                label = labels[i] if i < len(labels) else f"{i+1}."
                color = colors[i] if i < len(colors) else SLATE
                st.markdown(
                    f'<div style="background:{SURFACE};border:1px solid {BORDER};border-left:4px solid {color};'
                    f'border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px;font-size:13px;color:{TEXT}">'
                    f'<span style="font-size:9px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;'
                    f'color:{color};display:block;margin-bottom:4px">{label}</span>'
                    f'{rec}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("No executive brief available for this run.")


# ── TAB 2: BRAND SENTIMENT ────────────────────────────────────────────────────
with tab2:
    c1a, c1b = st.columns(2)
    with c1a:
        chart_label("Share of Voice")
        fig = px.pie(
            metrics_df, names="brand", values="total_posts",
            color="brand", color_discrete_map=BRAND_COLORS, hole=0.56,
        )
        fig.update_traces(
            textinfo="label+percent",
            textfont=dict(size=12, color=TEXT),
            marker=dict(line=dict(color=SURFACE, width=3)),
        )
        for trace in fig.data:
            new_colors = []
            for brand in trace.labels if hasattr(trace, "labels") and trace.labels is not None else []:
                new_colors.append("#FFFFFF" if brand == "Verizon" else TEXT)
            if new_colors:
                trace.textfont = dict(size=12, color=new_colors)
        fig.update_layout(showlegend=False, height=300, **_layout(margin=dict(t=10, b=10, l=8, r=8)))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with c1b:
        chart_label("Net Sentiment Score by Brand")
        nss_df = metrics_df[["brand", "net_sentiment_score"]].copy()
        fig = go.Figure(go.Bar(
            x=nss_df["brand"],
            y=nss_df["net_sentiment_score"],
            marker_color=[BRAND_COLORS.get(b, SLATE) for b in nss_df["brand"]],
            marker_line_width=0,
            text=nss_df["net_sentiment_score"].apply(lambda x: f"{x:+.1f}"),
            textposition="outside",
            textfont=dict(size=13, color=TEXT),
        ))
        fig.add_hline(y=0, line_dash="dot", line_color=BORDER, line_width=1)
        _chart(fig, height=300, yaxis_title="NSS (Positive% − Negative%)", xaxis_title="")

    s1, s2 = st.columns([2, 1])
    with s1:
        chart_label(f"Net Sentiment Trend — {selected_period}")
        if not trends_filt.empty:
            fig = px.line(
                trends_filt, x="trend_date", y="net_sentiment_score",
                color="brand", color_discrete_map=BRAND_COLORS, markers=True,
                labels={"net_sentiment_score": "NSS", "trend_date": "", "brand": ""},
            )
            fig.add_hline(y=0, line_dash="dot", line_color=BORDER, line_width=1)
            fig.update_traces(line=dict(width=2.5), marker=dict(size=7))
            _chart(fig, height=280)
        else:
            st.info("No trend data available.")

    with s2:
        chart_label("Sentiment Distribution by Brand")
        if not sentiment_raw.empty:
            fig = px.bar(
                sentiment_raw, x="brand", y="post_count", color="sentiment",
                color_discrete_map={"Positive": GREEN, "Neutral": TEXT_MUTED, "Negative": RED},
                barmode="stack",
                labels={"post_count": "Posts", "brand": "", "sentiment": ""},
            )
            fig.update_traces(marker_line_width=0)
            _chart(fig, height=280)
        else:
            sdf = metrics_df[["brand", "positive_pct", "neutral_pct", "negative_pct"]].melt(
                id_vars="brand", var_name="sentiment", value_name="pct"
            )
            sdf["sentiment"] = sdf["sentiment"].str.replace("_pct", "").str.capitalize()
            fig = px.bar(
                sdf, x="brand", y="pct", color="sentiment", barmode="stack",
                color_discrete_map={"Positive": GREEN, "Neutral": TEXT_MUTED, "Negative": RED},
                labels={"pct": "% Posts", "brand": "", "sentiment": ""},
            )
            fig.update_traces(marker_line_width=0)
            _chart(fig, height=280)


# ── TAB 3: CATEGORIES & PLATFORMS ────────────────────────────────────────────
with tab3:
    i1, i2 = st.columns([1, 1])
    with i1:
        chart_label("Top Categories by Conversation Volume")
        if not topics_df.empty:
            top_cats = (
                topics_df[topics_df["category"] != "Uncategorized"]
                .groupby("category", as_index=False)["post_count"].sum()
                .sort_values("post_count", ascending=False)
                .head(8)
                .reset_index(drop=True)
            )
            fig = go.Figure(go.Bar(
                y=top_cats["category"],
                x=top_cats["post_count"],
                orientation="h",
                marker_color=ACCENT,
                marker_line_width=0,
                text=top_cats["post_count"],
                textposition="outside",
                textfont=dict(size=12, color=TEXT),
            ))
            _chart(fig, height=300, xaxis_title="Posts",
                   margin=dict(t=10, b=10, l=150, r=50),
                   yaxis=dict(showgrid=False, zeroline=False, autorange="reversed",
                              tickfont=dict(size=11, color=TEXT),
                              linecolor="rgba(0,0,0,0)"))
        else:
            st.info("No category data available.")

    with i2:
        chart_label("Platform Breakdown by Brand")
        if not platform_df.empty:
            fig = px.bar(
                platform_df, x="platform", y="post_count",
                color="brand", barmode="group",
                color_discrete_map=BRAND_COLORS,
                labels={"post_count": "Posts", "platform": "", "brand": ""},
            )
            fig.update_traces(marker_line_width=0)
            _chart(fig, height=300, margin=dict(t=10, b=10, l=8, r=8))
        else:
            st.info("No platform data.")

    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
    chart_label("Common Categories by Brand")
    brand_tabs = st.tabs(["T-Mobile US", "Verizon", "AT&T Mobility"])
    for tab_b, brand_name, brand_color in zip(
        brand_tabs,
        ["T-Mobile US", "Verizon", "AT&T Mobility"],
        [ACCENT, SLATE, GREEN],
    ):
        with tab_b:
            bdf = topics_df[
                (topics_df["brand"] == brand_name) &
                (topics_df["category"] != "Uncategorized")
            ].copy()
            if bdf.empty:
                st.info(f"No category data for {brand_name}")
                continue
            cat_df = bdf.groupby("category", as_index=False)["post_count"].sum()
            cat_df = cat_df.sort_values("post_count", ascending=False)
            brand_total = cat_df["post_count"].sum()
            cat_df["pct"] = (cat_df["post_count"] / brand_total * 100).round(1)
            n_cats = len(cat_df)
            fig = px.treemap(
                cat_df,
                path=[px.Constant(f"n = {brand_total:,}"), "category"],
                values="post_count",
                color="post_count",
                color_continuous_scale=[[0, "#F0F9FA"], [1, brand_color]],
                custom_data=["post_count", "pct"],
            )
            fig.update_traces(
                texttemplate=(
                    ["%{label}"]
                    + ["<b>%{label}</b><br>%{customdata[0]} posts<br>%{customdata[1]:.1f}%"] * n_cats
                ),
                textfont=dict(
                    size=13,
                    family="-apple-system, BlinkMacSystemFont, sans-serif",
                    color=["white"] + [TEXT] * n_cats,
                ),
                marker=dict(line=dict(width=1, color=SURFACE)),
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "%{customdata[0]} posts · %{customdata[1]:.1f}%<extra></extra>"
                ),
            )
            fig.update_coloraxes(showscale=False)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=10, b=10, l=4, r=4), height=260)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── TAB 4: TREND ANALYSIS ─────────────────────────────────────────────────────
with tab4:
    t1, t2 = st.columns(2)
    with t1:
        chart_label("Conversation Volume Trend")
        if not trends_filt.empty:
            fig = px.line(
                trends_filt, x="trend_date", y="post_count",
                color="brand", color_discrete_map=BRAND_COLORS, markers=True,
                labels={"post_count": "Posts", "trend_date": "", "brand": ""},
            )
            fig.update_traces(line=dict(width=2.5), marker=dict(size=7))
            _chart(fig, height=280)
        else:
            st.info("No trend data.")

    with t2:
        chart_label("Complaint Trend")
        if not trends_filt.empty:
            fig = px.area(
                trends_filt, x="trend_date", y="complaint_pct",
                color="brand", color_discrete_map=BRAND_COLORS,
                labels={"complaint_pct": "Complaint %", "trend_date": "", "brand": ""},
                line_group="brand",
            )
            fig.update_traces(line=dict(width=1.5))
            _chart(fig, height=280)
        else:
            st.info("No trend data.")

    t3, t4 = st.columns(2)
    with t3:
        chart_label("Frustration vs Satisfaction Trend")
        if not trends_filt.empty:
            emotion_trend_df = trends_filt.melt(
                id_vars=["trend_date", "brand"],
                value_vars=["frustration_pct", "satisfaction_pct"],
                var_name="emotion", value_name="pct",
            )
            emotion_trend_df["emotion"] = emotion_trend_df["emotion"].str.replace("_pct", "").str.capitalize()
            fig = px.line(
                emotion_trend_df, x="trend_date", y="pct",
                color="brand", line_dash="emotion", color_discrete_map=BRAND_COLORS,
                markers=True,
                labels={"pct": "% Posts", "trend_date": "", "brand": "", "emotion": ""},
            )
            fig.update_traces(line=dict(width=2), marker=dict(size=6))
            _chart(fig, height=280)
        else:
            st.info("No trend data.")

    with t4:
        chart_label("Intent Distribution by Brand")
        intent_df = metrics_df[
            ["brand", "complaint_pct", "inquiry_pct", "praise_pct", "recommendation_pct"]
        ].melt(id_vars="brand", var_name="intent", value_name="pct")
        intent_df["intent"] = intent_df["intent"].str.replace("_pct", "").str.capitalize()
        fig = px.bar(
            intent_df, x="brand", y="pct", color="intent",
            barmode="group", color_discrete_sequence=PASTEL,
            labels={"pct": "% Posts", "brand": "", "intent": ""},
        )
        fig.update_traces(marker_line_width=0)
        _chart(fig, height=280)


# ── TAB 5: TAXONOMY BREAKDOWN ─────────────────────────────────────────────────
with tab5:
    if not topics_df.empty:
        p1, p2 = st.columns(2)
        with p1:
            chart_label("Pillar Volume — Comparison by Brand")
            pillar_brand = topics_df[topics_df["pillar"] != "Uncategorized"].groupby(
                ["brand", "pillar"], as_index=False
            )["post_count"].sum()
            fig = px.bar(
                pillar_brand, x="pillar", y="post_count",
                color="brand", barmode="group",
                color_discrete_map=BRAND_COLORS,
                labels={"post_count": "Posts", "pillar": "", "brand": ""},
            )
            fig.update_traces(marker_line_width=0)
            _chart(fig, height=300, xaxis_tickangle=-20)

        with p2:
            chart_label("Pillar Trend Over Time")
            if not tax_trend_filt.empty:
                pillar_trend = (
                    tax_trend_filt[tax_trend_filt["pillar"] != "Uncategorized"]
                    .groupby(["date", "pillar"], as_index=False)["post_count"].sum()
                )
                top_pillars = (
                    pillar_trend.groupby("pillar")["post_count"].sum()
                    .nlargest(5).index.tolist()
                )
                pillar_trend = pillar_trend[pillar_trend["pillar"].isin(top_pillars)]
                fig = px.line(
                    pillar_trend, x="date", y="post_count", color="pillar",
                    markers=True,
                    labels={"post_count": "Posts", "date": "", "pillar": ""},
                )
                fig.update_traces(line=dict(width=2), marker=dict(size=6))
                _chart(fig, height=300)
            else:
                st.info("No trend data.")

        st.markdown("<br>", unsafe_allow_html=True)
        chart_label("Emotion Heatmap by Brand")
        emotion_cols   = ["frustration_pct", "confusion_pct", "satisfaction_pct", "excitement_pct"]
        emotion_labels = ["Frustration", "Confusion", "Satisfaction", "Excitement"]
        emotion_targets = {
            "Frustration":  ("↓ target ≤ 20%",  "lower is better"),
            "Satisfaction": ("↑ target ≥ 30%",  "higher is better"),
            "Confusion":    ("↓ target ≤ 15%",  "lower is better"),
            "Excitement":   ("↑ target ≥ 20%",  "higher is better"),
        }
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
        for i, em in enumerate(emotion_labels):
            target_text, _ = emotion_targets[em]
            fig.add_annotation(
                x=i, y=-0.18,
                xref="x", yref="paper",
                text=f"<b>{target_text}</b>",
                showarrow=False,
                font=dict(size=10, color=TEXT_MUTED,
                          family="-apple-system, BlinkMacSystemFont, sans-serif"),
                align="center",
            )
        fig.update_layout(
            **_layout(
                margin=dict(t=16, b=64, l=8, r=8),
                yaxis=dict(showgrid=False, zeroline=False,
                           tickfont=dict(size=11, color=TEXT_MUTED),
                           linecolor="rgba(0,0,0,0)", gridcolor=BORDER),
            )
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No taxonomy data available.")


# ── TAB 6: TOPICS & COMPETITIVE INTEL ────────────────────────────────────────
with tab6:
    if not topics_df.empty:
        chart_label("Top Topics per Brand")
        brand_tab_topics = st.tabs(["T-Mobile US", "Verizon", "AT&T Mobility"])
        for tab_t, brand_name in zip(brand_tab_topics, ["T-Mobile US", "Verizon", "AT&T Mobility"]):
            with tab_t:
                bdf = topics_df[topics_df["brand"] == brand_name].head(8).copy()
                if bdf.empty:
                    st.info(f"No data for {brand_name}")
                    continue
                display = bdf[["rank", "pillar", "category", "topic", "post_count", "topic_share_pct", "is_emerging"]].copy()
                display.columns = ["#", "Pillar", "Category", "Topic", "Posts", "Share%", "New"]
                display["New"] = display["New"].map({True: "★", False: "", 1: "★", 0: ""})
                display["Share%"] = display["Share%"].apply(lambda x: f"{x:.1f}%")
                st.dataframe(display, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown(
        f"<div style='font-size:14px;font-weight:600;color:{TEXT};margin-bottom:10px'>Competitive Intelligence</div>",
        unsafe_allow_html=True,
    )
    comp_data = []
    for comp in ["Verizon", "AT&T Mobility"]:
        comp_row = metrics_df[metrics_df["brand"] == comp]
        if comp_row.empty:
            continue
        nss_gap_c     = safe_val(tmobile, "net_sentiment_score") - safe_val(comp_row, "net_sentiment_score")
        complaint_gap = safe_val(tmobile, "complaint_pct") - safe_val(comp_row, "complaint_pct")
        comp_data.append({
            "Competitor":       comp,
            "T-Mobile NSS":     f"{safe_val(tmobile,'net_sentiment_score'):+.1f}",
            f"{comp} NSS":      f"{safe_val(comp_row,'net_sentiment_score'):+.1f}",
            "NSS Gap":          f"{nss_gap_c:+.1f}",
            "Complaint Gap":    f"{complaint_gap:+.1f}pp",
            "T-Mobile Praise":  f"{safe_val(tmobile,'praise_pct'):.1f}%",
            f"{comp} Praise":   f"{safe_val(comp_row,'praise_pct'):.1f}%",
            "Verdict":          "T-Mobile leads" if nss_gap_c > 0 else "T-Mobile trails",
        })
    if comp_data:
        st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)


# ── TAB 7: EXECUTIVE INSIGHTS ─────────────────────────────────────────────────
with tab7:
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
                    f'<div class="insight-quote">"{gaps.get("narrative","")}"</div>',
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
    f"Data refreshes every 5 min"
    f"</div>",
    unsafe_allow_html=True,
)
