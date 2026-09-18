import pandas as pd
import streamlit as st
import plotly.express as px
import folium
import streamlit_folium as st_folium

# --- Load data (widgets OUTSIDE the cached function) ---
@st.cache_data
def parse_data(uploaded_file):
    df = pd.read_csv(uploaded_file)
    df["INSPECTION DATE"] = pd.to_datetime(df["INSPECTION DATE"])
    return df

try:
    df = parse_data("data/inspections.csv")
except Exception:
    st.sidebar.info("Upload the inspections CSV to get started")
    uploaded = st.sidebar.file_uploader("Upload inspections.csv", type="csv")
    if uploaded is None:
        st.stop()
    df = parse_data(uploaded)   

df = load_data()

# --- Sidebar filters ---
st.sidebar.title("🍽️ NYC Restaurant Health Dashboard")

boroughs = sorted(df["BORO"].dropna().unique())
selected_boro = st.sidebar.multiselect("Borough", boroughs, default=boroughs)

date_min, date_max = df["INSPECTION DATE"].min().date(), df["INSPECTION DATE"].max().date()
date_range = st.sidebar.date_input(
    "Inspection date range",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=date_max,
)

cuisines = sorted(df["CUISINE DESCRIPTION"].dropna().unique())
selected_cuisine = st.sidebar.selectbox("Cuisine (optional)", ["All"] + cuisines)

# Apply filters
filtered = df[df["BORO"].isin(selected_boro)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    filtered = filtered[
        (filtered["INSPECTION DATE"] >= pd.Timestamp(date_range[0])) &
        (filtered["INSPECTION DATE"] <= pd.Timestamp(date_range[1]))
    ]
if selected_cuisine != "All":
    filtered = filtered[filtered["CUISINE DESCRIPTION"] == selected_cuisine]

# --- Main page ---
st.title("NYC Restaurant Health Dashboard")
st.caption(f"{len(filtered):,} inspections | {filtered['CAMIS'].nunique():,} unique restaurants")

# KPI row
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Inspections", f"{len(filtered):,}")
col2.metric("Unique Restaurants", f"{filtered['CAMIS'].nunique():,}")
col3.metric("Avg Score", f"{filtered['SCORE'].mean():.1f}" if filtered['SCORE'].notna().any() else "—")
col4.metric("Failing (<70)", f"{(filtered['SCORE'] < 70).sum():,}")

tab1, tab2, tab3 = st.tabs(["Score Trends", "Map", "At-Risk List"])

# --- Tab 1: Score trends ---
with tab1:
    st.subheader("Monthly Average Score by Borough")

    # FIX: clip to 2000+ so the chart isn't stretched by sparse old data
    trend = filtered[filtered["INSPECTION DATE"] >= "2000-01-01"].copy()
    monthly = (
        trend.groupby([pd.Grouper(key="INSPECTION DATE", freq="M"), "BORO"])["SCORE"]
        .mean()
        .reset_index()
    )
    fig = px.line(
        monthly,
        x="INSPECTION DATE",
        y="SCORE",
        color="BORO",
        title="Average Inspection Score Over Time (2000–present)",
        labels={"INSPECTION DATE": "", "SCORE": "Avg Score", "BORO": "Borough"},
    )
    fig.update_layout(yaxis_range=[0, 100])  # lock y-axis so jumps are visible
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Score Distribution")
    fig2 = px.histogram(
        filtered, x="SCORE", nbins=50,
        title="Distribution of Inspection Scores",
        color_discrete_sequence=["#4C72B0"],
    )
    fig2.add_vline(x=70, line_dash="dash", annotation_text="Pass threshold")
    st.plotly_chart(fig2, use_container_width=True)

# --- Tab 2: Map ---
with tab2:
    st.subheader("Failing Restaurants (Score < 70)")
    failing = filtered[filtered["SCORE"] < 70].dropna(subset=["Latitude", "Longitude"])
    if len(failing) > 0:
        m = folium.Map(location=[40.7128, -73.9560], zoom_start=11)
        for _, row in failing.sample(min(len(failing), 500)).iterrows():
            folium.CircleMarker(
                location=[row["Latitude"], row["Longitude"]],
                radius=4,
                color="red",
                fill=True,
                fill_opacity=0.6,
                popup=f"{row['DBA']} (Score: {row['SCORE']})"
            ).add_to(m)
        st_folium.folium_static(m, width=700, height=500)
        st.caption(f"Showing {min(len(failing), 500)} of {len(failing):,} failing restaurants")
    else:
        st.info("No failing restaurants in the selected filters.")

# --- Tab 3: At-risk list ---
with tab3:
    st.subheader("Restaurants with Declining Scores")
    recent = filtered.sort_values("INSPECTION DATE").groupby("CAMIS").tail(3)
    declining = recent.groupby("CAMIS")["SCORE"].apply(
         lambda s: (s.iloc[-1] < s.iloc[0]) if len(s) == 3 and s.notna().all() else False
    )   
    at_risk = declining[declining].index
    at_risk_df = filtered[filtered["CAMIS"].isin(at_risk)].sort_values("SCORE").head(100)
    display_cols = ["DBA", "BORO", "CUISINE DESCRIPTION", "SCORE", "GRADE", "INSPECTION DATE"]
    st.dataframe(at_risk_df[display_cols], use_container_width=True)
    st.download_button(
        "⬇️ Download as CSV",
        at_risk_df[display_cols].to_csv(index=False).encode(),
        file_name="at_risk_restaurants.csv",
        mime="text/csv"
    )   
