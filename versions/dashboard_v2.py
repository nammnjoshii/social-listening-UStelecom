"""Streamlit Executive Dashboard — U.S. Telecom Social Listening.

Launch:
    streamlit run app/dashboard.py

Reads from SQLite at the path set in DB_PATH (.env).
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
ACCENT      = "#1FBBCC"   # Procogia teal
GREEN       = "#95C100"   # Procogia green
SLATE       = "#374151"   # neutral dark

# Per-brand colors (client gets Procogia teal)
BRAND_COLORS = {
    "T-Mobile US":   ACCENT,   # #1FBBCC
    "Verizon":       SLATE,    # #374151
    "AT&T Mobility": GREEN,    # #95C100
}

# Pastel sequence for multi-series (intent, emotion)
PASTEL = ["#BFD7FF", "#BFEFE8", "#D8C7FF", "#FFD7C2", "#FFF1B8"]

# ─────────────────────────────────────────────
# Global CSS — Apple-style minimalist
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
  /* ── Reset & base ── */
  html, body, [data-testid="stAppViewContainer"] {{
      background: {BG};
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      color: {TEXT};
  }}

  /* ── Sidebar ── */
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

  /* ── Hide default Streamlit chrome ── */
  #MainMenu, footer, header {{ visibility: hidden; }}

  /* ── Page title ── */
  h1 {{
      font-size: 22px !important;
      font-weight: 600 !important;
      letter-spacing: -0.5px;
      color: {TEXT} !important;
      margin-bottom: 2px !important;
  }}

  /* ── Section subheaders ── */
  h2, h3 {{
      font-size: 13px !important;
      font-weight: 600 !important;
      letter-spacing: 0.06em !important;
      text-transform: uppercase !important;
      color: {TEXT_MUTED} !important;
      margin-top: 28px !important;
      margin-bottom: 10px !important;
  }}

  /* ── Divider ── */
  hr {{
      border: none;
      border-top: 1px solid {BORDER};
      margin: 18px 0;
  }}

  /* ── KPI cards ── */
  .kpi-card {{
      background: {SURFACE};
      border: 1px solid {BORDER};
      border-radius: 12px;
      padding: 20px 24px 18px;
      min-height: 96px;
  }}
  .kpi-label {{
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.07em;
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
      font-size: 12px;
      font-weight: 500;
      color: {TEXT_MUTED};
      margin-top: 5px;
  }}
  .kpi-delta.pos {{ color: {ACCENT}; }}
  .kpi-delta.neg {{ color: #EF4444; }}

  /* ── Chart containers ── */
  .chart-card {{
      background: {SURFACE};
      border: 1px solid {BORDER};
      border-radius: 12px;
      padding: 20px 16px 8px;
  }}

  /* ── Dataframes ── */
  [data-testid="stDataFrame"] {{
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid {BORDER};
  }}

  /* ── Info / warning boxes ── */
  .stAlert {{
      border-radius: 8px;
      font-size: 13px;
  }}

  /* ── Tabs ── */
  .stTabs [data-baseweb="tab-list"] {{
      background: {BG};
      border-bottom: 1px solid {BORDER};
      gap: 0;
  }}
  .stTabs [data-baseweb="tab"] {{
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: {TEXT_MUTED};
      padding: 8px 18px;
      border-bottom: 2px solid transparent;
  }}
  .stTabs [aria-selected="true"] {{
      color: {ACCENT};
      border-bottom: 2px solid {ACCENT};
  }}

  /* ── Selectbox ── */
  [data-testid="stSelectbox"] > div > div {{
      border-radius: 8px;
      border-color: {BORDER};
      font-size: 13px;
  }}

  /* ── Caption ── */
  .stCaption {{
      color: {TEXT_MUTED};
      font-size: 11px;
  }}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Plotly base layout (applied to every chart)
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


def _chart(fig: go.Figure, **layout_overrides):
    """Apply Procogia theme and render chart."""
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
      <div style="font-size:11px;color:{TEXT_MUTED};letter-spacing:0.06em;text-transform:uppercase;margin-top:2px">Telecom Social Listening</div>
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
    st.markdown(f"<div style='font-size:11px;color:{TEXT_MUTED}'>Taxonomy v1.0.0 · Schema v1.0.0</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:11px;color:{TEXT_MUTED};margin-top:4px'>Refreshes every 5 min</div>", unsafe_allow_html=True)


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


metrics_df  = load_metrics(selected_run)
trends_df   = load_trends(selected_run)
topics_df   = load_topics(selected_run)
insight_data = load_insight(selected_run)
run_meta    = load_run_meta(selected_run)

if metrics_df.empty:
    st.warning("No metrics found for this run.")
    st.stop()


def safe_val(df: pd.DataFrame, col: str, default=0):
    return df[col].iloc[0] if not df.empty and col in df.columns else default


tmobile = metrics_df[metrics_df["brand"] == "T-Mobile US"]
verizon = metrics_df[metrics_df["brand"] == "Verizon"]
att     = metrics_df[metrics_df["brand"] == "AT&T Mobility"]


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
period_start = run_meta.get("period_start", "")[:10]
period_end   = run_meta.get("period_end", "")[:10]
post_count   = run_meta.get("post_count", "—")

st.markdown(f"<h1>Telecom Social Listening</h1>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-size:13px;color:{TEXT_MUTED};margin-bottom:4px'>"
    f"Client: <strong style='color:{TEXT}'>T-Mobile US</strong> &nbsp;·&nbsp; "
    f"Competitors: Verizon, AT&T Mobility &nbsp;·&nbsp; "
    f"{period_start} – {period_end} &nbsp;·&nbsp; {post_count:,} posts analysed</div>"
    if isinstance(post_count, int) else
    f"<div style='font-size:13px;color:{TEXT_MUTED};margin-bottom:4px'>"
    f"Client: <strong style='color:{TEXT}'>T-Mobile US</strong> &nbsp;·&nbsp; "
    f"Competitors: Verizon, AT&T Mobility</div>",
    unsafe_allow_html=True,
)
st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0 24px'>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# KPI row — T-Mobile spotlight
# ─────────────────────────────────────────────
st.markdown("<h3>T-Mobile Performance</h3>", unsafe_allow_html=True)
k1, k2, k3, k4, k5 = st.columns(5)

nss_tm  = safe_val(tmobile, "net_sentiment_score")
nss_vz  = safe_val(verizon, "net_sentiment_score")
nss_att = safe_val(att, "net_sentiment_score")
nss_gap = nss_tm - nss_vz

with k1:
    kpi("Conversation Share",
        f"{safe_val(tmobile, 'conversation_share_pct'):.1f}%")
with k2:
    kpi("Net Sentiment Score",
        f"{nss_tm:+.1f}",
        delta=f"{nss_gap:+.1f} vs Verizon",
        delta_positive=nss_gap > 0)
with k3:
    kpi("Complaint Rate",
        f"{safe_val(tmobile, 'complaint_pct'):.1f}%",
        delta=f"{safe_val(tmobile,'complaint_pct') - safe_val(verizon,'complaint_pct'):+.1f}pp vs Verizon",
        delta_positive=safe_val(tmobile,'complaint_pct') < safe_val(verizon,'complaint_pct'))
with k4:
    kpi("Frustration",
        f"{safe_val(tmobile, 'frustration_pct'):.1f}%")
with k5:
    kpi("Satisfaction",
        f"{safe_val(tmobile, 'satisfaction_pct'):.1f}%",
        delta_positive=True if safe_val(tmobile,'satisfaction_pct') > 0 else None)

st.markdown("<br>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Row 1: Conversation Share + NSS
# ─────────────────────────────────────────────
st.markdown("<h3>Brand Overview</h3>", unsafe_allow_html=True)
r1a, r1b = st.columns(2)

with r1a:
    fig = px.pie(
        metrics_df,
        names="brand",
        values="total_posts",
        color="brand",
        color_discrete_map=BRAND_COLORS,
        hole=0.52,
    )
    fig.update_traces(
        textinfo="label+percent",
        textfont=dict(size=12, color=TEXT),
        marker=dict(line=dict(color=SURFACE, width=3)),
    )
    fig.update_layout(showlegend=False, **_layout())
    st.markdown("<div class='chart-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:11px;font-weight:600;letter-spacing:0.07em;text-transform:uppercase;color:{TEXT_MUTED};margin-bottom:4px'>Conversation Share</div>", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

with r1b:
    nss_df = metrics_df[["brand", "net_sentiment_score"]].copy()
    fig = go.Figure(go.Bar(
        x=nss_df["brand"],
        y=nss_df["net_sentiment_score"],
        marker_color=[BRAND_COLORS.get(b, SLATE) for b in nss_df["brand"]],
        marker_line_width=0,
        text=nss_df["net_sentiment_score"].apply(lambda x: f"{x:+.1f}"),
        textposition="outside",
        textfont=dict(size=12, color=TEXT),
    ))
    fig.add_hline(y=0, line_dash="dot", line_color=BORDER, line_width=1)
    st.markdown("<div class='chart-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:11px;font-weight:600;letter-spacing:0.07em;text-transform:uppercase;color:{TEXT_MUTED};margin-bottom:4px'>Net Sentiment Score</div>", unsafe_allow_html=True)
    _chart(fig, yaxis_title="NSS (Positive% − Negative%)", xaxis_title="")
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Row 2: 7-Day Sentiment Trend
# ─────────────────────────────────────────────
st.markdown("<h3>7-Day Sentiment Trend</h3>", unsafe_allow_html=True)
if not trends_df.empty:
    fig = px.line(
        trends_df,
        x="trend_date", y="net_sentiment_score",
        color="brand", color_discrete_map=BRAND_COLORS,
        markers=True,
        labels={"net_sentiment_score": "NSS", "trend_date": "", "brand": ""},
    )
    fig.add_hline(y=0, line_dash="dot", line_color=BORDER, line_width=1)
    fig.update_traces(line=dict(width=2), marker=dict(size=6))
    _chart(fig)
else:
    st.info("No trend data available.")


# ─────────────────────────────────────────────
# Row 3: Intent + Emotion Heatmap
# ─────────────────────────────────────────────
st.markdown("<h3>Intent & Emotion Distribution</h3>", unsafe_allow_html=True)
r3a, r3b = st.columns(2)

with r3a:
    intent_df = metrics_df[["brand", "complaint_pct", "inquiry_pct", "praise_pct", "recommendation_pct"]].melt(
        id_vars="brand", var_name="intent", value_name="pct"
    )
    intent_df["intent"] = intent_df["intent"].str.replace("_pct", "").str.capitalize()
    fig = px.bar(
        intent_df,
        x="brand", y="pct", color="intent",
        barmode="group",
        color_discrete_sequence=PASTEL,
        labels={"pct": "% Posts", "brand": "", "intent": ""},
    )
    fig.update_traces(marker_line_width=0)
    st.markdown("<div class='chart-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:11px;font-weight:600;letter-spacing:0.07em;text-transform:uppercase;color:{TEXT_MUTED};margin-bottom:4px'>Intent Distribution</div>", unsafe_allow_html=True)
    _chart(fig)
    st.markdown("</div>", unsafe_allow_html=True)

with r3b:
    emotion_cols  = ["frustration_pct", "satisfaction_pct", "confusion_pct", "excitement_pct"]
    emotion_labels = ["Frustration", "Satisfaction", "Confusion", "Excitement"]
    heat_data = metrics_df.set_index("brand")[emotion_cols].rename(
        columns=dict(zip(emotion_cols, emotion_labels))
    )
    fig = px.imshow(
        heat_data,
        color_continuous_scale=[[0, "#F0FDF4"], [0.5, ACCENT + "55"], [1, ACCENT]],
        text_auto=".1f",
        aspect="auto",
        labels={"color": "%"},
    )
    fig.update_coloraxes(showscale=False)
    fig.update_traces(textfont=dict(size=12, color=TEXT))
    st.markdown("<div class='chart-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:11px;font-weight:600;letter-spacing:0.07em;text-transform:uppercase;color:{TEXT_MUTED};margin-bottom:4px'>Emotion Heatmap</div>", unsafe_allow_html=True)
    _chart(fig)
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Row 3b: 7-Day Emotion Trend
# ─────────────────────────────────────────────
st.markdown("<h3>7-Day Emotion Trend — Frustration vs Satisfaction</h3>", unsafe_allow_html=True)
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
    st.info("No trend data available.")


# ─────────────────────────────────────────────
# Row 4: 7-Day Complaint Trend
# ─────────────────────────────────────────────
st.markdown("<h3>7-Day Complaint Trend</h3>", unsafe_allow_html=True)
if not trends_df.empty:
    fig = px.area(
        trends_df,
        x="trend_date", y="complaint_pct",
        color="brand", color_discrete_map=BRAND_COLORS,
        labels={"complaint_pct": "Complaint %", "trend_date": "", "brand": ""},
        line_group="brand",
    )
    fig.update_traces(line=dict(width=1.5))
    _chart(fig)


# ─────────────────────────────────────────────
# Row 4b: 7-Day Conversation Volume Trend
# ─────────────────────────────────────────────
st.markdown("<h3>7-Day Conversation Volume</h3>", unsafe_allow_html=True)
if not trends_df.empty:
    fig = px.line(
        trends_df,
        x="trend_date", y="post_count",
        color="brand", color_discrete_map=BRAND_COLORS,
        markers=True,
        labels={"post_count": "Posts", "trend_date": "", "brand": ""},
    )
    fig.update_traces(line=dict(width=2), marker=dict(size=6))
    _chart(fig)
else:
    st.info("No trend data available.")


# ─────────────────────────────────────────────
# Row 5: Top Topics per Brand
# ─────────────────────────────────────────────
st.markdown("<h3>Top Topics by Brand</h3>", unsafe_allow_html=True)
if not topics_df.empty:
    brand_tabs = st.tabs(["T-Mobile US", "Verizon", "AT&T Mobility"])
    for tab, brand_name in zip(brand_tabs, ["T-Mobile US", "Verizon", "AT&T Mobility"]):
        with tab:
            bdf = topics_df[topics_df["brand"] == brand_name].head(10).copy()
            if bdf.empty:
                st.info(f"No topic data for {brand_name}")
                continue
            display = bdf[["rank", "pillar", "topic", "post_count", "topic_share_pct", "is_emerging"]].copy()
            display.columns = ["#", "Pillar", "Topic", "Posts", "Share %", "New"]
            display["New"] = display["New"].map({True: "🆕", False: "", 1: "🆕", 0: ""})
            display["Share %"] = display["Share %"].apply(lambda x: f"{x:.1f}%")
            st.dataframe(display, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# Row 5b: Taxonomy Breakdown by Pillar & Category
# ─────────────────────────────────────────────
st.markdown("<h3>Topic Volume by Pillar & Category</h3>", unsafe_allow_html=True)
if not topics_df.empty:
    pillar_df = topics_df.groupby(["brand", "pillar"], as_index=False)["post_count"].sum()
    fig = px.bar(
        pillar_df,
        x="pillar", y="post_count",
        color="brand", barmode="group",
        color_discrete_map=BRAND_COLORS,
        labels={"post_count": "Posts", "pillar": "", "brand": ""},
    )
    fig.update_traces(marker_line_width=0)
    _chart(fig, xaxis_tickangle=-15)

    pillars = sorted(pillar_df["pillar"].unique().tolist())
    sel = st.selectbox("Drill down by Pillar", pillars, key="pillar_select")
    cat_df = (
        topics_df[topics_df["pillar"] == sel]
        .groupby(["brand", "category"], as_index=False)["post_count"].sum()
    )
    fig2 = px.bar(
        cat_df,
        x="category", y="post_count",
        color="brand", barmode="group",
        color_discrete_map=BRAND_COLORS,
        labels={"post_count": "Posts", "category": "", "brand": ""},
    )
    fig2.update_traces(marker_line_width=0)
    _chart(fig2)


# ─────────────────────────────────────────────
# Row 6: Competitive Gap Table
# ─────────────────────────────────────────────
st.markdown("<h3>Competitive Gap — T-Mobile vs Competitors</h3>", unsafe_allow_html=True)
comp_data = []
for comp in ["Verizon", "AT&T Mobility"]:
    comp_row = metrics_df[metrics_df["brand"] == comp]
    if comp_row.empty:
        continue
    nss_gap_c    = safe_val(tmobile, "net_sentiment_score") - safe_val(comp_row, "net_sentiment_score")
    complaint_gap = safe_val(tmobile, "complaint_pct") - safe_val(comp_row, "complaint_pct")
    comp_data.append({
        "Competitor":      comp,
        "T-Mobile NSS":    f"{safe_val(tmobile, 'net_sentiment_score'):+.1f}",
        f"{comp} NSS":     f"{safe_val(comp_row, 'net_sentiment_score'):+.1f}",
        "NSS Gap":         f"{nss_gap_c:+.1f}",
        "Complaint Gap":   f"{complaint_gap:+.1f}pp",
        "Verdict":         "✅ T-Mobile leads" if nss_gap_c > 0 else "⚠️ T-Mobile trails",
    })
if comp_data:
    st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# Row 7: Executive Brief
# ─────────────────────────────────────────────
st.markdown(f"<hr style='border-color:{BORDER};margin:28px 0 20px'>", unsafe_allow_html=True)
st.markdown("<h3>Executive Brief</h3>", unsafe_allow_html=True)

if insight_data:
    eb1, eb2 = st.columns(2)
    with eb1:
        st.markdown(f"<div style='font-size:12px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:{TEXT_MUTED};margin-bottom:10px'>Top T-Mobile Complaints</div>", unsafe_allow_html=True)
        for item in insight_data.get("top_complaints", [])[:3]:
            st.markdown(
                f"<div style='background:{SURFACE};border:1px solid {BORDER};border-radius:8px;"
                f"padding:10px 14px;margin-bottom:8px;font-size:13px'>"
                f"<strong style='color:{TEXT}'>{item.get('topic','')}</strong>"
                f"<span style='color:{TEXT_MUTED};font-size:11px;margin-left:8px'>{item.get('complaint_pct',0):.1f}%</span>"
                f"<div style='color:{TEXT_MUTED};font-size:12px;margin-top:4px'>{item.get('context','')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown(f"<div style='font-size:12px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:{TEXT_MUTED};margin:16px 0 10px'>Emerging Topics</div>", unsafe_allow_html=True)
        for item in insight_data.get("emerging_topics", [])[:3]:
            brands_str = ", ".join(item.get("brands_affected", []))
            st.markdown(
                f"<div style='background:{SURFACE};border:1px solid {BORDER};border-left:3px solid {ACCENT};"
                f"border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:13px'>"
                f"<strong style='color:{TEXT}'>{item.get('topic','')}</strong>"
                f"<span style='color:{TEXT_MUTED};font-size:11px;margin-left:8px'>[{brands_str}]</span>"
                f"<div style='color:{TEXT_MUTED};font-size:12px;margin-top:4px'>{item.get('growth_note','')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with eb2:
        gaps = insight_data.get("sentiment_gaps", {})
        if gaps:
            st.markdown(f"<div style='font-size:12px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:{TEXT_MUTED};margin-bottom:10px'>Sentiment Narrative</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div style='background:{BG};border:1px solid {BORDER};border-radius:8px;"
                f"padding:14px 16px;font-size:13px;color:{TEXT};line-height:1.6'>"
                f"{gaps.get('narrative','')}</div>",
                unsafe_allow_html=True,
            )

        st.markdown(f"<div style='font-size:12px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:{TEXT_MUTED};margin:16px 0 10px'>Strategic Recommendations</div>", unsafe_allow_html=True)
        for rec in insight_data.get("strategic_recommendations", []):
            st.markdown(
                f"<div style='background:{SURFACE};border:1px solid {BORDER};border-left:3px solid {GREEN};"
                f"border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:13px;color:{TEXT}'>"
                f"→ {rec}</div>",
                unsafe_allow_html=True,
            )
else:
    st.info("No executive brief available for this run.")

st.markdown(
    f"<div style='font-size:11px;color:{TEXT_MUTED};text-align:center;margin-top:32px;padding-bottom:24px'>"
    f"Powered by Claude (claude-sonnet-4-6) &nbsp;·&nbsp; Procogia &nbsp;·&nbsp; Data refreshes every 5 minutes"
    f"</div>",
    unsafe_allow_html=True,
)
