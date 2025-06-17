import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: Scenario Insights")
st.caption("*All yield and RASK values shown in cent/km as provided — no conversion or normalization applied")

HUBS = ["DTW", "LAS", "FLL", "MCO", "MSY", "MYR", "ACY", "LGA"]

@st.cache_data
def load_data():
    df = pd.read_excel("root_routes.xlsx")
    df.columns = [str(c).strip() for c in df.columns]

    df.rename(columns={
        "Flight Number": "AF",
        "Departure Day": "Day of Week",
        "Dist mi": "Distance (mi)"
    }, inplace=True)

    df["Hub (nested)"] = df["Hub (nested)"].astype(str).str.strip()
    df["Hub"] = df["Hub (nested)"].apply(lambda h: h if h in HUBS else "P2P")

    df["Distance (mi)"] = pd.to_numeric(df.get("Distance (mi)"), errors="coerce")
    df["Seats"] = pd.to_numeric(df.get("Seats", 1), errors="coerce")
    df["ASM"] = pd.to_numeric(df.get("ASM", df["Seats"] * df["Distance (mi)"]), errors="coerce")
    df["Constrained Yield (cent, km)"] = pd.to_numeric(df.get("Constrained Yield (cent, km)"), errors="coerce")
    df["Constrained RASK (cent)"] = pd.to_numeric(df.get("Constrained RASK (cent)"), errors="coerce")
    df["Load Factor"] = pd.to_numeric(df["Load Factor"].astype(str).str.replace("%", ""), errors="coerce")
    df["Constrained Connect Fare"] = pd.to_numeric(df.get("Constrained Connect Fare"), errors="coerce")
    df["Constrained Segment Pax"] = pd.to_numeric(df.get("Constrained Segment Pax"), errors="coerce")
    df["Constrained Local Fare"] = pd.to_numeric(df.get("Constrained Local Fare"), errors="coerce")

    df["RouteID"] = df["Departure Airport"].astype(str) + ":" + df["Arrival Airport"].astype(str)

    df["Day of Week"] = pd.to_numeric(df["Day of Week"], errors="coerce")
    days_op = df.groupby(["ScenarioLabel", "RouteID"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "RouteID", "Days Operated"]
    df = df.merge(days_op, on=["ScenarioLabel", "RouteID"], how="left")
    df["Low Frequency"] = df["Days Operated"] <= 2

    df["Connect Yield"] = df["Constrained Connect Fare"] / df["Constrained Segment Pax"]
    df["Connect vs O-D Yield Ratio"] = df["Connect Yield"] / df["Constrained Local Fare"]

    return df

df_raw = load_data()

# Sidebar controls
available_scenarios = sorted(df_raw["ScenarioLabel"].dropna().unique())
base_scenario = st.sidebar.selectbox("Select BASE Scenario", available_scenarios)
comparison_scenarios = st.sidebar.multiselect(
    "Select COMPARISON Scenario(s)", [s for s in available_scenarios if s != base_scenario]
)

hub_options = ["System-wide"] + HUBS + ["P2P"]
selected_hub = st.sidebar.selectbox("Filter by Hub", hub_options)

# Helper: clean label for display
def clean_label(label):
    if "(" in label:
        return label.split("(")[0].strip()
    if ":" in label:
        return label.split(":")[0].strip()
    return label.strip()

# Hub filtering function
def filter_by_hub(df):
    if selected_hub == "System-wide":
        return df
    return df[df["Hub"] == selected_hub]

# Core comparison logic
if comparison_scenarios:
    df_base = filter_by_hub(df_raw[df_raw["ScenarioLabel"] == base_scenario])
    routes_base = set(df_base["RouteID"])
    clean_base = clean_label(base_scenario)

    for comp in comparison_scenarios:
        df_comp = filter_by_hub(df_raw[df_raw["ScenarioLabel"] == comp])
        routes_comp = set(df_comp["RouteID"])
        clean_comp = clean_label(comp)

        unique_routes = routes_comp - routes_base
        subset = df_comp[df_comp["RouteID"].isin(unique_routes)].drop_duplicates(subset=["RouteID"])

        st.markdown(f"### ✈️ **New Routes:** `{clean_comp}` vs `{clean_base}`")
        st.dataframe(subset[[
            "RouteID",
            "ASM",
            "Constrained Yield (cent, km)",
            "Load Factor",
            "Constrained RASK (cent)",
            "Distance (mi)",
            "Cut",
            "Connect vs O-D Yield Ratio"
        ]].rename(columns={
            "Load Factor": "LF",
            "Connect vs O-D Yield Ratio": "Connecting Yield / O-D Yield"
        }), use_container_width=True)

else:
    st.info("Select at least one comparison scenario to begin analysis.")

# ASM Totals
st.markdown("### 📊 **ASM Totals by Scenario**")
asm_summary = (
    df_raw.groupby("ScenarioLabel")["ASM"]
    .sum()
    .div(1_000_000)
    .reset_index()
    .rename(columns={"ASM": "Total ASM (M)"})
    .sort_values("Total ASM (M)", ascending=False)
)
st.dataframe(asm_summary, use_container_width=True)
