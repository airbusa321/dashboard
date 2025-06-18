import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: Scenario Insights")
st.caption("*All values in miles (thousands). SLA adjustment uses stage length in miles → YIELD and RASK adjusted via log-linear method (β = -0.5, benchmark = 1000 mi) → then converted to ¢/mi. Usefulness scaled ×1000. ASMs in thousands.*")

HUBS = ["DTW", "LAS", "FLL", "MCO", "MSY", "MYR", "ACY", "LGA"]
KM_TO_MI = 0.621371

@st.cache_data
def load_data():
    df = pd.read_excel("root_routes.xlsx")
    df.columns = [str(c).strip() for c in df.columns]

    df.rename(columns={
        "Dist mi": "Distance (mi)",
        "Distance (km)": "Distance (km)",
        "ASM": "ASM (000s)"
    }, inplace=True)

    df["Hub (nested)"] = df["Hub (nested)"].astype(str).str.strip()
    df["Hub"] = df["Hub (nested)"].apply(lambda h: h if h in HUBS else "P2P")

    df["Distance (mi)"] = pd.to_numeric(df.get("Distance (mi)"), errors="coerce")
    df["Distance (km)"] = pd.to_numeric(df.get("Distance (km)"), errors="coerce")
    df["Seats"] = pd.to_numeric(df["Seats"], errors="coerce")
    df["ASM (000s)"] = pd.to_numeric(df.get("ASM (000s)"), errors="coerce") / 1000
    df["Constrained Yield (cent, km)"] = pd.to_numeric(df["Constrained Yield (cent, km)"], errors="coerce")
    df["Constrained RASK (cent)"] = pd.to_numeric(df["Constrained RASK (cent)"], errors="coerce")
    df["Load Factor"] = df["Load Factor"].astype(str).str.strip()
    df["Load Factor Numeric"] = pd.to_numeric(df["Load Factor"].str.replace("%", "", regex=False), errors="coerce")
    df["Constrained Connect Fare"] = pd.to_numeric(df["Constrained Connect Fare"], errors="coerce")
    df["Constrained Segment Pax"] = pd.to_numeric(df["Constrained Segment Pax"], errors="coerce")
    df["Constrained Local Fare"] = pd.to_numeric(df["Constrained Local Fare"], errors="coerce")
    df["Constrained Local Pax"] = pd.to_numeric(df["Constrained Local Pax"], errors="coerce")
    df["Spill Rate"] = pd.to_numeric(df["Spill Rate"], errors="coerce")

    df["RouteID"] = df["Departure Airport"].astype(str) + ":" + df["Arrival Airport"].astype(str)
    df["UniqueID"] = df["ScenarioLabel"] + "_" + df["RouteID"]

    df = df[~((df["Constrained Yield (cent, km)"] == 0) & (df["Constrained RASK (cent)"] == 0))]

    BENCHMARK_STAGE_LENGTH_MI = 1000
    YIELD_ELASTICITY = -0.5

    scaling_factor = (df["Distance (mi)"].clip(lower=1) / BENCHMARK_STAGE_LENGTH_MI) ** abs(YIELD_ELASTICITY)
    capped_factor = scaling_factor.clip(upper=scaling_factor.mean() + 1.5 * scaling_factor.std())

    df["SLA Adj Yield (mi)"] = df["Constrained Yield (cent, km)"] / KM_TO_MI * capped_factor
    df["SLA Adj RASM (mi)"] = df["Constrained RASK (cent)"] * capped_factor

    df["Connect Share"] = 1 - (df["Constrained Local Pax"] / df["Constrained Segment Pax"])
    df["Connect Share"] = df["Connect Share"].clip(lower=0, upper=1)

    df["Usefulness Score"] = 1000 * (
        df["SLA Adj RASM (mi)"] *
        (df["Load Factor Numeric"] / 100) *
        (1 - df["Spill Rate"]) *
        (1 - df["Connect Share"])
    )

    df["Connect Yield"] = df["Constrained Connect Fare"] / df["Constrained Segment Pax"]
    df["Connect vs O-D Yield Ratio"] = 100 * (df["Connect Yield"] / df["Constrained Local Fare"])

    return df.drop_duplicates(subset=["UniqueID"])

df_raw = load_data()

route_tab, validation_tab, overview_tab = st.tabs(["Scenario Comparison", "ASG vs Spirit Validation", "🧾 Summary: What Changed?"])

with overview_tab:
    if comparison_scenarios:
        st.markdown("### 📋 Detailed Summary of Network Changes")

        summary_details = []
        for summary in route_summaries:
            comp_scenario = summary["Scenario"]
            df_base = df_raw[df_raw["ScenarioLabel"] == base_scenario]
            df_comp = df_raw[df_raw["ScenarioLabel"] == comp_scenario]

            routes_base = set(df_base["RouteID"])
            routes_comp = set(df_comp["RouteID"])

            new_routes = routes_comp - routes_base
            cut_routes = routes_base - routes_comp
            continued_routes = routes_base & routes_comp

            df_base_cont = df_base[df_base["RouteID"].isin(continued_routes)]
            df_comp_cont = df_comp[df_comp["RouteID"].isin(continued_routes)]

            df_merged = df_base_cont[["RouteID", "Hub", "ASM (000s)", "Usefulness Score", "SLA Adj RASM (mi)"]].merge(
                df_comp_cont[["RouteID", "ASM (000s)", "Usefulness Score", "SLA Adj RASM (mi)"]],
                on="RouteID", suffixes=('_base', '_comp')
            )
            df_merged["Delta ASM"] = df_merged["ASM (000s)_comp"] - df_merged["ASM (000s)_base"]
            df_merged["Delta Usefulness"] = df_merged["Usefulness Score_comp"] - df_merged["Usefulness Score_base"]
            df_merged["Delta RASM"] = df_merged["SLA Adj RASM (mi)_comp"] - df_merged["SLA Adj RASM (mi)_base"]

            # Group by hub and summarize
            hub_changes = df_merged.groupby("Hub").agg({
                "Delta ASM": "sum",
                "Delta Usefulness": "sum",
                "Delta RASM": "mean",
                "RouteID": "count"
            }).rename(columns={"RouteID": "Changed Routes"}).reset_index()

            st.markdown(f"#### ✈️ {comp_scenario} vs {base_scenario}")
            st.markdown("This table summarizes route-level changes by hub, including changes in ASM, RASM, and route-level usefulness for retained routes:")
            st.dataframe(hub_changes.style.format({
                "Delta ASM": "{:.2f}",
                "Delta Usefulness": "{:.2f}",
                "Delta RASM": "{:.2f}"
            }), use_container_width=True)

            summary_details.append({
                "Scenario": comp_scenario,
                "New Routes": len(new_routes),
                "Cut Routes": len(cut_routes),
                "Base Routes": len(routes_base),
                "Comp Routes": len(routes_comp),
                "Net Route Change": len(routes_comp) - len(routes_base),
                "Avg Delta ASM (000s)": df_merged["Delta ASM"].mean(),
                "Avg Delta Usefulness": df_merged["Delta Usefulness"].mean(),
                "Avg Delta RASM (¢/mi)": df_merged["Delta RASM"].mean()
            })

        st.markdown("### 🗒️ Narrative Summary of Cuts by Hub")
        df_cut_routes = df_base[df_base["RouteID"].isin(cut_routes)]
        cut_by_hub = df_cut_routes.groupby("Hub").agg({"RouteID": "count"}).rename(columns={"RouteID": "Cut Routes"}).reset_index()

        narrative_lines = []
        for _, row in cut_by_hub.iterrows():
            hub = row["Hub"]
            count = row["Cut Routes"]
            if hub == "P2P":
                narrative_lines.append(f"- **P2P**: {count} point-to-point routes were cut, reflecting a retreat from lower-margin leisure city pairs.")
            else:
                narrative_lines.append(f"- **{hub}**: {count} routes removed, suggesting a tightening of bank structure or profitability discipline at this hub.")

        st.markdown("\n".join(narrative_lines))

        st.markdown("### 📊 Overall Summary Table")
        st.dataframe(pd.DataFrame(summary_details).style.format({
            "Avg Delta ASM (000s)": "{:.2f}",
            "Avg Delta Usefulness": "{:.2f}",
            "Avg Delta RASM (¢/mi)": "{:.2f}"
        }), use_container_width=True)
    else:
        st.info("Select a base and comparison scenario to view summary changes.")

with route_tab:
    available_scenarios = sorted(df_raw["ScenarioLabel"].dropna().unique())
    base_scenario = st.sidebar.selectbox("Select BASE Scenario", available_scenarios)
    comparison_scenarios = st.sidebar.multiselect(
        "Select COMPARISON Scenario(s)", [s for s in available_scenarios if s != base_scenario]
    )
        df_base_all = df_raw[df_raw["ScenarioLabel"] == base_scenario]
        route_summaries = []

        for comp in comparison_scenarios:
            # Existing logic ...
            merged["Change (pp)"] = merged["SLA Adj RASM (mi)_comp"] - merged["SLA Adj RASM (mi)_base"]

            # Add summary data
            route_summaries.append({
                "Scenario": comp,
                "New Routes": len(new_routes),
                "Cut Routes": len(cut_routes),
                "Total Routes in Base": len(routes_base),
                "Total Routes in Comp": len(routes_comp),
                "Avg RASM Delta (¢/mi)": merged["Change (pp)"].mean()
            })

            for hub in sorted(merged["Hub"].dropna().unique()):
                st.markdown(f"**Hub: {hub}**")
                st.dataframe(
                    merged[merged["Hub"] == hub][["RouteID", "Change (pp)"]]
                    .sort_values("Change (pp)", ascending=False)
                    .style.format({"Change (pp)": "{:.2f}"}),
                    use_container_width=True
                )
