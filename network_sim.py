import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: Scenario Insights")
st.caption("*All values in cent/km. SLA adjustment via ln(stage length). Usefulness scaled ×1000.")

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
    df["Constrained Local Pax"] = pd.to_numeric(df.get("Constrained Local Pax"), errors="coerce")
    df["Spill Rate"] = pd.to_numeric(df.get("Spill Rate"), errors="coerce")

    df["RouteID"] = df["Departure Airport"].astype(str) + ":" + df["Arrival Airport"].astype(str)

    df["Day of Week"] = pd.to_numeric(df["Day of Week"], errors="coerce")
    days_op = df.groupby(["ScenarioLabel", "RouteID"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "RouteID", "Days Operated"]
    df = df.merge(days_op, on=["ScenarioLabel", "RouteID"], how="left")
    df["Low Frequency"] = df["Days Operated"] <= 2

    # SLA Adjustments
    df["Stage Length (adj)"] = df["Distance (mi)"].clip(lower=1)
    df["SLA Adj Yield (km)"] = df["Constrained Yield (cent, km)"] / np.log(df["Stage Length (adj)"])
    df["SLA Adj RASM (km)"] = df["Constrained RASK (cent)"] / np.log(df["Stage Length (adj)"])

    # Connect Share based on pax
    df["Connect Share"] = 1 - (df["Constrained Local Pax"] / df["Constrained Segment Pax"])
    df["Connect Share"] = df["Connect Share"].clip(lower=0, upper=1)

    # Usefulness Score (×1000 scale)
    df["Usefulness Score"] = 1000 * (
        df["SLA Adj RASM (km)"] *
        (df["Load Factor"] / 100) *
        (1 - df["Spill Rate"]) *
        (1 - df["Connect Share"])
    )

    # Connect vs O-D Yield ×100
    df["Connect Yield"] = df["Constrained Connect Fare"] / df["Constrained Segment Pax"]
    df["Connect vs O-D Yield Ratio"] = 100 * (df["Connect Yield"] / df["Constrained Local Fare"])

    return df

df_raw = load_data()

# Sidebar Controls
available_scenarios = sorted(df_raw["ScenarioLabel"].dropna().unique())
base_scenario = st.sidebar.selectbox("Select BASE Scenario", available_scenarios)
comparison_scenarios = st.sidebar.multiselect(
    "Select COMPARISON Scenario(s)", [s for s in available_scenarios if s != base_scenario]
)

hub_options = ["System-wide"] + HUBS + ["P2P"]
selected_hub = st.sidebar.selectbox("Filter by Hub", hub_options)

def clean_label(label):
    if "(" in label:
        return label.split("(")[0].strip()
    return label.strip()

def filter_by_hub(df):
    if selected_hub == "System-wide":
        return df
    return df[df["Hub"] == selected_hub]

# Route Comparisons
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
            "SLA Adj Yield (km)",
            "Constrained RASK (cent)",
            "SLA Adj RASM (km)",
            "Load Factor",
            "Distance (mi)",
            "Cut",
            "Connect vs O-D Yield Ratio",
            "Usefulness Score"
        ]].rename(columns={
            "Load Factor": "LF",
            "Connect vs O-D Yield Ratio": "Connecting Yield / O-D Yield"
        }), use_container_width=True)

else:
    st.info("Select at least one comparison scenario to begin analysis.")

# ASM Summary
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
