import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: Scenario Insights")
st.caption("*All values in miles (thousands). SLA adjustment uses stage length in km → RASK adjusted via log-linear method (β = -0.5, benchmark = 950 km) → then converted to RASM in ¢/mi. Usefulness scaled ×1000. ASMs in thousands.")

HUBS = ["DTW", "LAS", "FLL", "MCO", "MSY", "MYR", "ACY", "LGA"]
KM_TO_MI = 0.621371

@st.cache_data
def load_data():
    df = pd.read_excel("root_routes.xlsx")
    df.columns = [str(c).strip() for c in df.columns]

    df.rename(columns={
        "Flight Number": "Flight Number",
        "Departure Day": "Day of Week",
        "Dist mi": "Distance (mi)",
        "Distance (km)": "Distance (km)"
    }, inplace=True)

    df["Hub (nested)"] = df["Hub (nested)"].astype(str).str.strip()
    df["Hub"] = df["Hub (nested)"].apply(lambda h: h if h in HUBS else "P2P")

    df["Distance (mi)"] = pd.to_numeric(df.get("Distance (mi)"), errors="coerce")
    df["Distance (km)"] = pd.to_numeric(df.get("Distance (km)"), errors="coerce")
    df["Seats"] = pd.to_numeric(df.get("Seats", 1), errors="coerce")
    df["ASM"] = pd.to_numeric(df.get("ASM", df["Seats"] * df["Distance (mi)"]), errors="coerce") / 1000  # ASM in thousands
    df["Constrained Yield (cent, km)"] = pd.to_numeric(df.get("Constrained Yield (cent, km)"), errors="coerce")
    df["Constrained RASK (cent)"] = pd.to_numeric(df.get("Constrained RASK (cent)"), errors="coerce")
    df["Load Factor"] = pd.to_numeric(df["Load Factor"].astype(str).str.replace("%", ""), errors="coerce")
    df["Constrained Connect Fare"] = pd.to_numeric(df.get("Constrained Connect Fare"), errors="coerce")
    df["Constrained Segment Pax"] = pd.to_numeric(df.get("Constrained Segment Pax"), errors="coerce")
    df["Constrained Local Fare"] = pd.to_numeric(df.get("Constrained Local Fare"), errors="coerce")
    df["Constrained Local Pax"] = pd.to_numeric(df.get("Constrained Local Pax"), errors="coerce")
    df["Spill Rate"] = pd.to_numeric(df.get("Spill Rate"), errors="coerce")

    df["RouteID"] = df["Departure Airport"].astype(str) + ":" + df["Arrival Airport"].astype(str)
    df["Flight Number"] = df["Flight Number"].astype(str).str.strip()
    df["UniqueID"] = df["ScenarioLabel"] + "_" + df["RouteID"] + "_" + df["Flight Number"]

    df = df[~((df["Constrained Yield (cent, km)"] == 0) & (df["Constrained RASK (cent)"] == 0))]

    # --- Stage-Length Adjustment Parameters ---
    BENCHMARK_STAGE_LENGTH_KM = 950
    YIELD_ELASTICITY = -0.5

    # --- SLA RASK Adjustment (log-linear method) ---
    df["SLA Adj RASK (cent, km)"] = df["Constrained RASK (cent)"] * (
        (BENCHMARK_STAGE_LENGTH_KM / df["Distance (km)"].clip(lower=1)) ** abs(YIELD_ELASTICITY)
    )
    df["SLA Adj RASM (mi)"] = df["SLA Adj RASK (cent, km)"] / KM_TO_MI

    # --- SLA Yield Adjustment (optional, to match structure) ---
    df["SLA Adj Yield (mi)"] = df["Constrained Yield (cent, km)"] * (
        (BENCHMARK_STAGE_LENGTH_KM / df["Distance (km)"].clip(lower=1)) ** abs(YIELD_ELASTICITY)
    ) / KM_TO_MI

    # --- Connect Share & Usefulness Score ---
    df["Connect Share"] = 1 - (df["Constrained Local Pax"] / df["Constrained Segment Pax"])
    df["Connect Share"] = df["Connect Share"].clip(lower=0, upper=1)

    df["Usefulness Score"] = 1000 * (
        df["SLA Adj RASM (mi)"] *
        (df["Load Factor"] / 100) *
        (1 - df["Spill Rate"]) *
        (1 - df["Connect Share"])
    )

    df["Connect Yield"] = df["Constrained Connect Fare"] / df["Constrained Segment Pax"]
    df["Connect vs O-D Yield Ratio"] = 100 * (df["Connect Yield"] / df["Constrained Local Fare"])

    return df.drop_duplicates(subset=["UniqueID"])

df_raw = load_data()

available_scenarios = sorted(df_raw["ScenarioLabel"].dropna().unique())
base_scenario = st.sidebar.selectbox("Select BASE Scenario", available_scenarios)
comparison_scenarios = st.sidebar.multiselect(
    "Select COMPARISON Scenario(s)", [s for s in available_scenarios if s != base_scenario]
)

hub_options = ["System-wide"] + HUBS + ["P2P"]
selected_hub = st.sidebar.selectbox("Filter by Hub", hub_options)

def filter_by_hub(df):
    if selected_hub == "System-wide":
        return df
    return df[df["Hub"] == selected_hub]

def clean_label(label):
    return label.split("(")[0].strip() if "(" in label else label.strip()

if comparison_scenarios:
    df_base = filter_by_hub(df_raw[df_raw["ScenarioLabel"] == base_scenario])
    routes_base = set(df_base["RouteID"])

    for comp in comparison_scenarios:
        df_comp = filter_by_hub(df_raw[df_raw["ScenarioLabel"] == comp])
        routes_comp = set(df_comp["RouteID"])

        clean_base = clean_label(base_scenario)
        clean_comp = clean_label(comp)

        new_routes = routes_comp - routes_base
        cut_routes = routes_base - routes_comp
        continued_routes = routes_base & routes_comp

        st.markdown(f"### 🟢 **New Routes in `{clean_comp}` (vs `{clean_base}`)**")
        st.dataframe(
            df_comp[df_comp["RouteID"].isin(new_routes)][[
                "RouteID", "ASM", "SLA Adj Yield (mi)", "SLA Adj RASM (mi)", "Load Factor", "Distance (mi)", "Usefulness Score"
            ]].style.format({
                "ASM": "{:.2f}",
                "SLA Adj Yield (mi)": "{:.2f}",
                "SLA Adj RASM (mi)": "{:.2f}",
                "Load Factor": "{:.1f}%",
                "Distance (mi)": "{:.1f}",
                "Usefulness Score": "{:.2f}"
            }),
            use_container_width=True
        )

        st.markdown(f"### 🔴 **Cut Routes (were in `{clean_base}`, not in `{clean_comp}`)**")
        st.dataframe(
            df_base[df_base["RouteID"].isin(cut_routes)][[
                "RouteID", "ASM", "SLA Adj Yield (mi)", "SLA Adj RASM (mi)", "Load Factor", "Distance (mi)", "Usefulness Score"
            ]].style.format({
                "ASM": "{:.2f}",
                "SLA Adj Yield (mi)": "{:.2f}",
                "SLA Adj RASM (mi)": "{:.2f}",
                "Load Factor": "{:.1f}%",
                "Distance (mi)": "{:.1f}",
                "Usefulness Score": "{:.2f}"
            }),
            use_container_width=True
        )

        st.markdown(f"### 📉 **Market SLA RASM Delta (`{clean_comp}` vs `{clean_base}`)**")
        merged = df_base[df_base["RouteID"].isin(continued_routes)][["RouteID", "SLA Adj RASM (mi)"]].merge(
            df_comp[["RouteID", "SLA Adj RASM (mi)"]], on="RouteID", suffixes=("_base", "_comp")
        )
        merged["Change (pp)"] = merged["SLA Adj RASM (mi)_comp"] - merged["SLA Adj RASM (mi)_base"]

        st.dataframe(
            merged.sort_values("Change (pp)", ascending=False).style.format({
                "SLA Adj RASM (mi)_base": "{:.2f}",
                "SLA Adj RASM (mi)_comp": "{:.2f}",
                "Change (pp)": "{:.2f}"
            }),
            use_container_width=True
        )
else:
    st.info("Select at least one comparison scenario to begin analysis.")

st.markdown("### 🏙️ SLA RASM by Hub and Scenario")
sla_summary = df_raw.groupby(["ScenarioLabel", "Hub"])["SLA Adj RASM (mi)"].mean().reset_index()
st.dataframe(sla_summary.style.format({"SLA Adj RASM (mi)": "{:.2f}"}), use_container_width=True)
