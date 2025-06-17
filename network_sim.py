import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Spirit Network Strategy Dashboard", layout="wide")
st.title("🛫 Spirit Airlines Network Planning Dashboard")
st.caption("*All dollar and ASM values shown in thousands")

file_path = "root_data.xlsx"
pavlina_path = "root_3.xlsx"

# Function to compute Route Resilience Score (RRS)
def compute_rrs(df, 
                cost_col='Costs1', 
                profit_col='Profit1', 
                asm_col='ASM',
                yield_col='Constrained Yield (cent, km)',
                lf_col='Load Factor',
                spill_col='Spill Rate',
                market_avg_fare=11.0):
    for col in [cost_col, profit_col, asm_col, yield_col, lf_col, spill_col]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['CASM (cent)'] = df[cost_col] / df[asm_col]
    df['BELF'] = df['CASM (cent)'] / df[yield_col].replace(0, np.nan)
    df['LF_decimal'] = df[lf_col] / 100
    df['LF_minus_BELF'] = df['LF_decimal'] - df['BELF']
    df['Spill_Adjusted'] = 1 - df[spill_col].replace(1, np.nan)
    df['Profit_per_ASM'] = df[profit_col] / (df[asm_col] * 1000)
    df['RRS_simplified'] = (df['LF_minus_BELF'] / df['Spill_Adjusted']) * df['Profit_per_ASM'] * 10000
    df['Fare_Premium'] = df[yield_col] / market_avg_fare
    df['RRS'] = df['RRS_simplified'] * df['Fare_Premium']
    return df

# ---- LOAD AND TRANSFORM DATA ----
try:
    df_raw = pd.read_excel(file_path, sheet_name="NET_in")
    df_raw.columns = [str(c).strip() for c in df_raw.columns]
    df_raw.rename(columns={"Flight Number": "AF", "Departure Day": "Day of Week"}, inplace=True)

    # Pavlina load
    try:
        df_pav = pd.read_excel(pavlina_path)
        df_pav.columns = [str(c).strip() for c in df_pav.columns]
        df_pav["Departure Airport"] = df_pav["O"].astype(str).str.strip()
        df_pav["Arrival Airport"] = df_pav["D"].astype(str).str.strip()
        df_pav["AF"] = df_pav["Departure Airport"] + df_pav["Arrival Airport"]
        df_pav["ScenarioLabel"] = "Pavlina Assumptions"
        df_pav["Distance (mi)"] = pd.to_numeric(df_pav["SL"], errors="coerce")
        df_pav["ASM"] = pd.to_numeric(df_pav["Added ASMs"], errors="coerce")
        df_pav["Unconstrained O&D Revenue"] = pd.to_numeric(df_pav["Added ASMs * TRASM"], errors="coerce")
        df_pav["Constrained Segment Revenue"] = 0
        df_pav["Constrained Segment Pax"] = 0
        df_pav["Seats"] = 1
        df_pav["Cut"] = 0
        df_pav["Day of Week"] = 1
        df_pav["Spill Rate"] = 1.0
        df_pav["Constrained Yield (cent, km)"] = 0
        df_pav["Hub (nested)"] = df_pav["O"].apply(lambda x: str(x).strip() if str(x).strip() in ["FLL", "LAS", "DTW", "MCO"] else "P2P")

        for col in df_raw.columns:
            if col not in df_pav.columns:
                df_pav[col] = np.nan
        df_pav = df_pav[df_raw.columns]
        df_raw = pd.concat([df_raw, df_pav], ignore_index=True)
    except Exception as e:
        st.warning(f"⚠️ Failed to load Pavlina assumptions: {e}")

    # Derived fields
    df_raw["AF"] = df_raw["AF"].astype(str)
    df_raw["ASM"] = df_raw["ASM"].combine_first(df_raw["Seats"] * df_raw["Distance (mi)"])
    df_raw["NetworkType"] = df_raw["Hub (nested)"].apply(lambda h: h.strip() if str(h).strip() in ["FLL", "LAS", "DTW", "MCO"] else "P2P")
    days_op = df_raw.groupby(["ScenarioLabel", "AF"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "AF", "Days Operated"]
    df_raw = df_raw.merge(days_op, on=["ScenarioLabel", "AF"], how="left")
    df_raw["RPM"] = df_raw["Constrained Segment Pax"] * df_raw["Distance (mi)"]
    df_raw["Load Factor"] = df_raw["RPM"] / df_raw["ASM"] * 100
    df_raw["RASM"] = df_raw["Constrained Segment Revenue"] / df_raw["ASM"] * 100
    df_raw["TRASM"] = df_raw["Unconstrained O&D Revenue"] / df_raw["ASM"] * 100

    # Usefulness
    valid_mask = df_raw["Distance (mi)"].notna() & df_raw["Distance (mi)"] > 0 & df_raw["TRASM"].notna()
    if valid_mask.sum() > 10:
        log_stage = np.log(df_raw.loc[valid_mask, "Distance (mi)"])
        trasm = df_raw.loc[valid_mask, "TRASM"]
        slope, intercept = np.polyfit(log_stage, trasm, 1)
        df_raw["Normalized TRASM"] = slope * np.log(df_raw["Distance (mi)"].fillna(1)) + intercept
    else:
        df_raw["Normalized TRASM"] = df_raw["TRASM"]
    
    df_raw["Elasticity"] = df_raw.apply(
        lambda row: 1.2 if row["Constrained Segment Pax"] > 1.1 * row["Seats"] * 0.7 else 1.0,
        axis=1
    )
    df_raw["Raw Usefulness"] = (
        (df_raw["TRASM"] - df_raw["Normalized TRASM"]) / df_raw["Normalized TRASM"]
    ) * df_raw["Elasticity"] * (1 + 0.1 * df_raw["Spill Rate"])
    df_raw["Usefulness"] = df_raw["Raw Usefulness"] - df_raw["Raw Usefulness"].min()

    # Final metrics
    df_raw = compute_rrs(df_raw)

    # ---- TABS ----
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Summary View", "🔍 Route Analysis", "📌 Scenario Comparison", "📈 Shared Route Differences"])

    # --- Summary View ---
    with tab1:
        scenario_options = df_raw["ScenarioLabel"].dropna().unique().tolist()
        selected_scenario = st.selectbox("Scenario", scenario_options, key="summary_scenario")
        df_filtered = df_raw[df_raw["ScenarioLabel"] == selected_scenario].copy()

        st.subheader(f"Summary by Hub – {selected_scenario}")
        hub_summary = df_filtered.groupby("NetworkType").apply(lambda g: pd.Series({
            "Weekly Departures": g["Days Operated"].sum(),
            "ASMs (M)": g["ASM"].sum() / 1_000_000
        })).reset_index().rename(columns={"NetworkType": "Hub"})
        st.dataframe(hub_summary, use_container_width=True)

    # --- Route-Level View ---
    with tab2:
        scenario_choice = st.selectbox("Scenario", scenario_options, key="route_scenario")
        hub_choice = st.selectbox("Hub", ["DTW", "LAS", "FLL", "MCO", "P2P"], key="route_hub")
        show_only_cut = st.checkbox("Show only cut routes")

        df_view = df_raw[(df_raw["ScenarioLabel"] == scenario_choice) & (df_raw["NetworkType"] == hub_choice)].copy()
        if show_only_cut:
            df_view = df_view[df_view["Cut"] == 1]

        df_view = df_view.drop_duplicates(subset=["ScenarioLabel", "AF"])
        df_view = df_view.sort_values("Usefulness", ascending=False)
        st.dataframe(df_view[[
            "AF", "Departure Airport", "Arrival Airport", "ASM", "RASM", "TRASM", "Load Factor",
            "Usefulness", "RRS", "Cut", "Days Operated"
        ]], use_container_width=True)

    # --- Scenario Comparison ---
    with tab3:
        st.header("Compare Routes Between Two Scenarios")
        scenario_a = st.selectbox("Scenario A", scenario_options, key="compare_a")
        scenario_b = st.selectbox("Scenario B", scenario_options, key="compare_b")

        df_a = df_raw[df_raw["ScenarioLabel"] == scenario_a]
        df_b = df_raw[df_raw["ScenarioLabel"] == scenario_b]
        af_a = set(df_a["AF"])
        af_b = set(df_b["AF"])

        st.subheader(f"Routes in {scenario_a} but not in {scenario_b}")
        st.dataframe(df_a[df_a["AF"].isin(af_a - af_b)], use_container_width=True)

        st.subheader(f"Routes in {scenario_b} but not in {scenario_a}")
        st.dataframe(df_b[df_b["AF"].isin(af_b - af_a)], use_container_width=True)

    # --- Shared Route Differences ---
    with tab4:
        shared = af_a & af_b
        df_a_shared = df_a[df_a["AF"].isin(shared)].set_index("AF")
        df_b_shared = df_b[df_b["AF"].isin(shared)].set_index("AF")
        df_compare = df_a_shared.join(df_b_shared, lsuffix="_A", rsuffix="_B", how="inner")

        df_compare["Usefulness_Diff"] = df_compare["Usefulness_A"] - df_compare["Usefulness_B"]
        df_compare["TRASM_Diff"] = df_compare["TRASM_A"] - df_compare["TRASM_B"]
        df_compare["RRS_Diff"] = df_compare["RRS_A"] - df_compare["RRS_B"]
        df_compare = df_compare.reset_index()
        st.dataframe(df_compare[[
            "AF", "Departure Airport_A", "Arrival Airport_A", "Usefulness_A", "Usefulness_B", "Usefulness_Diff",
            "TRASM_A", "TRASM_B", "TRASM_Diff", "RRS_A", "RRS_B", "RRS_Diff"
        ]], use_container_width=True)

except Exception as e:
    st.error(f"Failed to load or process data: {e}")
