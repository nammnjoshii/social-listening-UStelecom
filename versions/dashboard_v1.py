"""Streamlit Executive Dashboard — U.S. Telecom Social Listening.

Launch:
    streamlit run app/dashboard.py

Reads from PostgreSQL using the connection string in DB_CONNECTION env var.
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
    page_title="T-Mobile Social Listening | Executive Dashboard",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

BRAND_COLORS = {
    "T-Mobile US": "#E20074",    # Magenta
    "Verizon": "#CD040B",        # Red
    "AT&T Mobility": "#00A8E0",  # Blue
}

# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────
def _get_conn():
    db_path = os.environ.get("DB_PATH", "data/telecom.db")
    return sqlite3.connect(db_path, check_same_thread=False)


@st.cache_data(ttl=300)
def _query(sql: str, params=None) -> pd.DataFrame:
    # Convert %s placeholders to ? for SQLite
    sql = sql.replace("%s", "?")
    conn = _get_conn()
    return pd.read_sql(sql, conn, params=params)


def latest_run_id() -> str:
    df = _query("SELECT run_id FROM pipeline_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1")
    return df["run_id"].iloc[0] if not df.empty else ""


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/T-Mobile_logo.svg/200px-T-Mobile_logo.svg.png", width=150)
    st.title("Social Listening")
    st.caption("T-Mobile US | Verizon | AT&T Mobility")
    st.divider()

    run_df = _query("SELECT run_id, completed_at FROM pipeline_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 10")
    if run_df.empty:
        st.warning("No completed pipeline runs found.")
        st.stop()

    run_options = run_df["run_id"].tolist()
    run_labels = {r: f"{r[:8]}… ({t})" for r, t in zip(run_df["run_id"], run_df["completed_at"].astype(str))}
    selected_run = st.selectbox("Pipeline Run", run_options, format_func=lambda x: run_labels.get(x, x))

    st.divider()
    st.caption(f"Taxonomy: v1.0.0 | Schema: v1.0.0")

# ─────────────────────────────────────────────
# Load data for selected run
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_metrics(run_id: str) -> pd.DataFrame:
    return _query("SELECT * FROM brand_metrics WHERE pipeline_run_id = %s ORDER BY brand", (run_id,))


@st.cache_data(ttl=300)
def load_trends(run_id: str) -> pd.DataFrame:
    return _query("SELECT * FROM daily_trends WHERE pipeline_run_id = %s ORDER BY trend_date, brand", (run_id,))


@st.cache_data(ttl=300)
def load_topics(run_id: str) -> pd.DataFrame:
    return _query("SELECT * FROM top_topics WHERE pipeline_run_id = %s ORDER BY brand, rank", (run_id,))


@st.cache_data(ttl=300)
def load_insight(run_id: str) -> dict:
    df = _query("SELECT insight_json FROM executive_insights WHERE pipeline_run_id = %s", (run_id,))
    if df.empty:
        return {}
    raw = df["insight_json"].iloc[0]
    return json.loads(raw) if isinstance(raw, str) else raw


metrics_df = load_metrics(selected_run)
trends_df = load_trends(selected_run)
topics_df = load_topics(selected_run)
insight_data = load_insight(selected_run)

if metrics_df.empty:
    st.warning("No metrics found for this run. The pipeline may still be running.")
    st.stop()

# ─────────────────────────────────────────────
# Header KPIs
# ─────────────────────────────────────────────
st.title("📡 Telecom Social Listening — Executive Dashboard")
st.caption(f"Client: **T-Mobile US** | Competitors: Verizon, AT&T Mobility | Run: `{selected_run[:12]}…`")
st.divider()

tmobile = metrics_df[metrics_df["brand"] == "T-Mobile US"]
verizon = metrics_df[metrics_df["brand"] == "Verizon"]
att = metrics_df[metrics_df["brand"] == "AT&T Mobility"]


def safe_val(df: pd.DataFrame, col: str, default=0):
    return df[col].iloc[0] if not df.empty and col in df.columns else default


col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("T-Mobile Conv Share", f"{safe_val(tmobile, 'conversation_share_pct'):.1f}%")
with col2:
    nss = safe_val(tmobile, "net_sentiment_score")
    nss_vz = safe_val(verizon, "net_sentiment_score")
    st.metric("T-Mobile NSS", f"{nss:+.1f}", delta=f"{nss - nss_vz:+.1f} vs Verizon")
with col3:
    st.metric("T-Mobile Complaint %", f"{safe_val(tmobile, 'complaint_pct'):.1f}%")
with col4:
    st.metric("T-Mobile Frustration %", f"{safe_val(tmobile, 'frustration_pct'):.1f}%")
with col5:
    st.metric("T-Mobile Satisfaction %", f"{safe_val(tmobile, 'satisfaction_pct'):.1f}%")

st.divider()

# ─────────────────────────────────────────────
# Row 1: Conversation Share + Sentiment Distribution
# ─────────────────────────────────────────────
r1_col1, r1_col2 = st.columns(2)

with r1_col1:
    st.subheader("Conversation Share")
    fig_share = px.pie(
        metrics_df,
        names="brand",
        values="total_posts",
        color="brand",
        color_discrete_map=BRAND_COLORS,
        hole=0.4,
    )
    fig_share.update_traces(textinfo="label+percent")
    fig_share.update_layout(showlegend=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig_share, use_container_width=True)

with r1_col2:
    st.subheader("Net Sentiment Score by Brand")
    nss_df = metrics_df[["brand", "net_sentiment_score"]].copy()
    nss_df["color"] = nss_df["net_sentiment_score"].apply(
        lambda x: BRAND_COLORS.get("T-Mobile US") if x > 0 else "#999"
    )
    fig_nss = go.Figure(go.Bar(
        x=nss_df["brand"],
        y=nss_df["net_sentiment_score"],
        marker_color=[BRAND_COLORS.get(b, "#999") for b in nss_df["brand"]],
        text=nss_df["net_sentiment_score"].apply(lambda x: f"{x:+.1f}"),
        textposition="outside",
    ))
    fig_nss.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_nss.update_layout(
        yaxis_title="NSS (Positive% − Negative%)",
        margin=dict(t=10, b=10),
        xaxis_title="",
    )
    st.plotly_chart(fig_nss, use_container_width=True)

# ─────────────────────────────────────────────
# Row 2: 7-Day Sentiment Trend
# ─────────────────────────────────────────────
st.subheader("7-Day Net Sentiment Score Trend")
if not trends_df.empty:
    fig_trend = px.line(
        trends_df,
        x="trend_date",
        y="net_sentiment_score",
        color="brand",
        color_discrete_map=BRAND_COLORS,
        markers=True,
        labels={"net_sentiment_score": "NSS", "trend_date": "Date", "brand": "Brand"},
    )
    fig_trend.add_hline(y=0, line_dash="dash", line_color="lightgray")
    fig_trend.update_layout(margin=dict(t=10, b=10), legend_title="Brand")
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("No trend data available for this run.")

# ─────────────────────────────────────────────
# Row 3: Intent + Emotion
# ─────────────────────────────────────────────
r3_col1, r3_col2 = st.columns(2)

with r3_col1:
    st.subheader("Intent Distribution")
    intent_cols = ["complaint_pct", "inquiry_pct", "praise_pct", "recommendation_pct"]
    intent_labels = ["Complaint", "Inquiry", "Praise", "Recommendation"]
    intent_df = metrics_df[["brand"] + intent_cols].melt(
        id_vars="brand", var_name="intent", value_name="pct"
    )
    intent_df["intent"] = intent_df["intent"].str.replace("_pct", "").str.capitalize()
    fig_intent = px.bar(
        intent_df,
        x="brand",
        y="pct",
        color="intent",
        barmode="group",
        labels={"pct": "% Posts", "brand": "", "intent": "Intent"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_intent.update_layout(margin=dict(t=10, b=10))
    st.plotly_chart(fig_intent, use_container_width=True)

with r3_col2:
    st.subheader("Emotion Heatmap")
    emotion_cols = ["frustration_pct", "satisfaction_pct", "confusion_pct", "excitement_pct"]
    emotion_labels = ["Frustration", "Satisfaction", "Confusion", "Excitement"]
    heat_data = metrics_df.set_index("brand")[emotion_cols].rename(
        columns=dict(zip(emotion_cols, emotion_labels))
    )
    fig_heat = px.imshow(
        heat_data,
        color_continuous_scale="RdYlGn_r",
        text_auto=".1f",
        aspect="auto",
        labels={"color": "%"},
    )
    fig_heat.update_layout(margin=dict(t=10, b=10))
    st.plotly_chart(fig_heat, use_container_width=True)

# ─────────────────────────────────────────────
# Row 3b: 7-Day Emotion Trend
# ─────────────────────────────────────────────
st.subheader("7-Day Emotion Trend — Frustration vs Satisfaction")
if not trends_df.empty:
    emotion_trend_df = trends_df.melt(
        id_vars=["trend_date", "brand"],
        value_vars=["frustration_pct", "satisfaction_pct"],
        var_name="emotion",
        value_name="pct",
    )
    emotion_trend_df["emotion"] = emotion_trend_df["emotion"].str.replace("_pct", "").str.capitalize()
    fig_emotion_trend = px.line(
        emotion_trend_df,
        x="trend_date",
        y="pct",
        color="brand",
        line_dash="emotion",
        color_discrete_map=BRAND_COLORS,
        markers=True,
        labels={"pct": "% Posts", "trend_date": "Date", "brand": "Brand", "emotion": "Emotion"},
    )
    fig_emotion_trend.update_layout(margin=dict(t=10, b=10), legend_title="Brand / Emotion")
    st.plotly_chart(fig_emotion_trend, use_container_width=True)
else:
    st.info("No trend data available for this run.")

# ─────────────────────────────────────────────
# Row 4: 7-Day Complaint Trend
# ─────────────────────────────────────────────
st.subheader("7-Day Complaint Trend")
if not trends_df.empty:
    fig_complaint = px.area(
        trends_df,
        x="trend_date",
        y="complaint_pct",
        color="brand",
        color_discrete_map=BRAND_COLORS,
        labels={"complaint_pct": "Complaint %", "trend_date": "Date"},
        line_group="brand",
    )
    fig_complaint.update_layout(margin=dict(t=10, b=10))
    st.plotly_chart(fig_complaint, use_container_width=True)

# ─────────────────────────────────────────────
# Row 4b: 7-Day Conversation Volume Trend
# ─────────────────────────────────────────────
st.subheader("7-Day Conversation Volume Trend")
if not trends_df.empty:
    fig_volume = px.line(
        trends_df,
        x="trend_date",
        y="post_count",
        color="brand",
        color_discrete_map=BRAND_COLORS,
        markers=True,
        labels={"post_count": "Post Count", "trend_date": "Date", "brand": "Brand"},
    )
    fig_volume.update_layout(margin=dict(t=10, b=10), legend_title="Brand")
    st.plotly_chart(fig_volume, use_container_width=True)
else:
    st.info("No trend data available for this run.")

# ─────────────────────────────────────────────
# Row 5: Top Topics per Brand
# ─────────────────────────────────────────────
st.subheader("Top Topics by Brand")
if not topics_df.empty:
    brand_tabs = st.tabs(["T-Mobile US", "Verizon", "AT&T Mobility"])
    for tab, brand_name in zip(brand_tabs, ["T-Mobile US", "Verizon", "AT&T Mobility"]):
        with tab:
            bdf = topics_df[topics_df["brand"] == brand_name].head(10)
            if bdf.empty:
                st.info(f"No topic data for {brand_name}")
                continue
            display = bdf[["rank", "pillar", "topic", "post_count", "topic_share_pct", "is_emerging"]].copy()
            display.columns = ["Rank", "Pillar", "Topic", "Posts", "Share %", "Emerging"]
            display["Emerging"] = display["Emerging"].map({True: "🆕", False: ""})
            st.dataframe(display, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
# Row 5b: Taxonomy Breakdown by Pillar & Category
# ─────────────────────────────────────────────
st.subheader("Topic Volume by Pillar & Category")
if not topics_df.empty:
    pillar_df = topics_df.groupby(["brand", "pillar"], as_index=False)["post_count"].sum()
    fig_pillar = px.bar(
        pillar_df,
        x="pillar",
        y="post_count",
        color="brand",
        barmode="group",
        color_discrete_map=BRAND_COLORS,
        labels={"post_count": "Post Count", "pillar": "Pillar", "brand": "Brand"},
    )
    fig_pillar.update_layout(
        margin=dict(t=10, b=10),
        xaxis_tickangle=-20,
        legend_title="Brand",
    )
    st.plotly_chart(fig_pillar, use_container_width=True)

    pillars = sorted(pillar_df["pillar"].unique().tolist())
    selected_pillar = st.selectbox("Drill down by Pillar", pillars, key="pillar_select")
    cat_df = (
        topics_df[topics_df["pillar"] == selected_pillar]
        .groupby(["brand", "category"], as_index=False)["post_count"].sum()
    )
    fig_cat = px.bar(
        cat_df,
        x="category",
        y="post_count",
        color="brand",
        barmode="group",
        color_discrete_map=BRAND_COLORS,
        labels={"post_count": "Post Count", "category": "Category", "brand": "Brand"},
        title=f"Category Breakdown — {selected_pillar}",
    )
    fig_cat.update_layout(margin=dict(t=30, b=10), legend_title="Brand")
    st.plotly_chart(fig_cat, use_container_width=True)

# ─────────────────────────────────────────────
# Row 6: Competitive Gap Table
# ─────────────────────────────────────────────
st.subheader("Competitive Gap Summary — T-Mobile US")
comp_data = []
for comp in ["Verizon", "AT&T Mobility"]:
    comp_row = metrics_df[metrics_df["brand"] == comp]
    if comp_row.empty:
        continue
    nss_gap = safe_val(tmobile, "net_sentiment_score") - safe_val(comp_row, "net_sentiment_score")
    complaint_gap = safe_val(tmobile, "complaint_pct") - safe_val(comp_row, "complaint_pct")
    comp_data.append({
        "Competitor": comp,
        "T-Mobile NSS": safe_val(tmobile, "net_sentiment_score"),
        f"{comp} NSS": safe_val(comp_row, "net_sentiment_score"),
        "NSS Gap": f"{nss_gap:+.1f}",
        "Complaint Gap": f"{complaint_gap:+.1f}%",
        "Verdict": "✅ T-Mobile leads" if nss_gap > 0 else "⚠️ T-Mobile trails",
    })

if comp_data:
    st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
# Row 7: Executive Brief
# ─────────────────────────────────────────────
st.divider()
st.subheader("📋 Executive Brief (Claude-Generated)")
if insight_data:
    eb_col1, eb_col2 = st.columns(2)

    with eb_col1:
        st.markdown("**Top T-Mobile Complaints**")
        for item in insight_data.get("top_complaints", [])[:3]:
            st.markdown(f"- **{item.get('topic', '')}** ({item.get('complaint_pct', 0):.1f}%) — {item.get('context', '')}")

        st.markdown("**Emerging Topics**")
        for item in insight_data.get("emerging_topics", [])[:3]:
            brands = ", ".join(item.get("brands_affected", []))
            st.markdown(f"- **{item.get('topic', '')}** [{brands}] — {item.get('growth_note', '')}")

    with eb_col2:
        gaps = insight_data.get("sentiment_gaps", {})
        if gaps:
            st.markdown("**Sentiment Gap Narrative**")
            st.info(gaps.get("narrative", ""))

        st.markdown("**Strategic Recommendations**")
        for rec in insight_data.get("strategic_recommendations", []):
            st.success(f"→ {rec}")
else:
    st.info("No executive brief available for this run. Check pipeline logs.")

st.caption("Powered by Claude (claude-sonnet-4-6) | Data refreshes every 5 minutes")
