import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: Scenario Insights")
st.caption("*All yield and RASM values converted to cents per **mile**, stage-length adjusted via log")

HUBS = ["DTW", "LAS", "FLL", "MCO", "MSY", "MYR", "ACY", "LGA"]
KM_TO_MI = 1.60934

@st.cache_data
def load_data():
    df = pd.read_excel("root_routes.xlsx")
    df.columns = [str(c).strip() for c in df.columns]

    df.rename(columns={
        "Flight Number": "AF",
        "Departure Day": "Day of Week",
        "Dist mi": "Distance (mi)"
    }, inplace=True)

    # Hub logic
    df["Hub (nested)"] = df["Hub (nested)"].astype(str).str.strip()
    df["Hub"] = df["Hub (nested)"].apply(lambda h: h if h in HUBS else "P2P")

    # Core metrics
    df["Distance (mi)"] = pd.to_numeric(df.get("Distance (mi)"), errors="coerce")
    df["Seats"] = pd.to_numeric(df.get("Seats", 1), errors="coerce")
    df["ASM"] = pd.to_numeric(df.get("ASM", df["Seats"] * df["Distance (mi)"]), errors="coerce")

    # Revenue data
    df["Constrained Yield (cent, km)"] = pd.to_numeric(df.get("Constrained Yield (cent, km)"), errors="coerce")
    df["Constrained RASK (cent)"] = pd.to_numeric(df.get("Constrained RASK (cent)"), errors="coerce")
    df["Load Factor"] = pd.to_numeric(df["Load Factor"].astype(str).str.replace("%", ""), errors="coerce")
    df["Constrained Connect Fare"] = pd.to_numeric(df.get("Constrained Connect Fare"), errors="coerce")
    df["Constrained Segment Pax"] = pd.to_numeric(df.get("Constrained Segment Pax"), errors="coerce")
    df["Constrained Local Fare"] = pd.to_numeric(df.get("Constrained Local Fare"), errors="coerce")

    # Route ID
    df["RouteID"] = df["Departure Airport"].astype(str) + ":" + df["Arrival Airport"].astype(str)

    # Frequency logic
    df["Day of Week"] = pd.to_numeric(df["Day of Week"], errors="coerce")
    days_op = df.groupby(["ScenarioLabel", "RouteID"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "RouteID", "Days Operated"]
    df = df.merge(days_op, on=["ScenarioLabel", "RouteID"], how="left")
    df["Low Frequency"] = df["Days Operated"] <= 2

    # SLA stage length base (prevent log(0) errors)
    df["Stage Length"] = df["Distance (mi)"].clip(lower=1)

    # Convert and SLA-adjust
    df["Yield (¢/mi)"] = df["Constrained Yield (cent, km)"] * KM_TO_MI
    df["RASM (¢/mi)"] = df["Constrained RASK (cent)"] * KM_TO_MI
    df["SLA Adj Yield (mi)"] = df["Yield (¢/mi)"] / np.log(df["Stage Length"])
    df["SLA RASM (mi)"] = df["RASM (¢/mi)"] / np.log(df["Stage Length"])

    # Connecting traffic proxy
    df["Connect Yield"] = df["Constrained Connect Fare"] / df["Constrained Segment Pax"]
    df["Connect vs O-D Yield Ratio"] = df["Connect Yield"] / df["Constrained Local Fare"]

    return df

# Load data
df_raw = load_data()

# Sidebar logic
available_scenarios = sorted(df_raw["ScenarioLabel"].dropna().unique())
base_scenario = st.sidebar.selectbox("Select BASE Scenario", available_scenarios)
comparison_scenarios = st.sidebar.multiselect(
    "Select COMPARISON Scenario(s)", [s for s in available_scenarios if s != base_scenario]
)

if comparison_scenarios:
    df_base = df_raw[df_raw["ScenarioLabel"] == base_scenario]
    routes_base = set(df_base["RouteID"])

    for comp in comparison_scenarios:
        df_comp = df_raw[df_raw["ScenarioLabel"] == comp]
        routes_comp = set(df_comp["RouteID"])
        unique_routes = routes_comp - routes_base
        subset = df_comp[df_comp["RouteID"].isin(unique_routes)].drop_duplicates(subset=["RouteID"])

        st.subheader(f"✈️ Routes in {comp} but NOT in {base_scenario}")
        st.dataframe(subset[[
            "RouteID",
            "ASM",
            "SLA Adj Yield (mi)",
            "Load Factor",
            "SLA RASM (mi)",
            "Stage Length",
            "Cut",
            "Connect vs O-D Yield Ratio"
        ]].rename(columns={
            "Load Factor": "LF",
            "Connect vs O-D Yield Ratio": "Connecting Yield / O-D Yield"
        }), use_container_width=True)

else:
    st.info("Select at least one comparison scenario to begin analysis.")
