import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Spirit Network Strategy Dashboard", layout="wide")
st.title("🛫 Spirit Airlines Network Planning Dashboard")
st.caption("*All dollar and ASM values shown in thousands")

file_path = "root_data.xlsx"
pavlina_path = "root_3.xlsx"

def compute_rrs(df, 
                cost_col='Costs1', 
                profit_col='Profit1', 
                asm_col='ASM',
                yield_col='Constrained Yield (cent, km)',
                lf_col='Load Factor',
                spill_col='Spill Rate',
                market_avg_fare=None):

    for col in [cost_col, profit_col, asm_col, yield_col, lf_col, spill_col]:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['CASM (cent)'] = df[cost_col] / df[asm_col]
    df['BELF'] = df['CASM (cent)'] / df[yield_col]
    df['LF_minus_BELF'] = df[lf_col] / 100 - df['BELF']
    df['Spill_Adjusted'] = 1 - df[spill_col].replace(1, np.nan)
    df['Profit_per_ASM'] = df[profit_col] / (df[asm_col] * 1000)
    df['RRS_simplified'] = (df['LF_minus_BELF'] / df['Spill_Adjusted']) * df['Profit_per_ASM']

    if market_avg_fare:
        df['Fare_Premium'] = df[yield_col] / market_avg_fare
        df['RRS'] = df['RRS_simplified'] * df['Fare_Premium']
    else:
        df['RRS'] = df['RRS_simplified']

    return df

try:
    xlsx = pd.ExcelFile(file_path)
    if "NET_in" not in xlsx.sheet_names:
        st.error(f"'NET_in' sheet not found. Available sheets: {xlsx.sheet_names}")
        st.stop()

    df_raw = pd.read_excel(xlsx, sheet_name="NET_in")
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    df_raw.rename(columns={
        "Flight Number": "AF",
        "Departure Day": "Day of Week",
        "Departure Airport": "Departure Airport",
        "Arrival Airport": "Arrival Airport",
        "Hub (nested)": "Hub (nested)",
        "Distance (km)": "Distance (km)",
        "Dist mi": "Distance (mi)",
        "Constrained Segment Pax": "Constrained Segment Pax",
        "Constrained Segment Revenue": "Constrained Segment Revenue",
        "Unconstrained O&D Revenue": "Unconstrained O&D Revenue",
        "ScenarioLabel": "ScenarioLabel",
        "Cut": "Cut"
    }, inplace=True)

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
        df_pav["Hub (nested)"] = "P2P"
        df_pav["Spill Rate"] = 1.0
        df_pav["Constrained Yield (cent, km)"] = 0

        for col in df_raw.columns:
            if col not in df_pav.columns:
                df_pav[col] = np.nan
        df_pav = df_pav[df_raw.columns]
        df_raw = pd.concat([df_raw, df_pav], ignore_index=True)

    except Exception as e:
        st.warning(f"⚠️ Failed to load or process Pavlina file (root_3.xlsx): {e}")

    df_raw["AF"] = df_raw["AF"].astype(str)
    df_raw["ASM"] = df_raw["ASM"].combine_first(df_raw["Seats"] * df_raw["Distance (mi)"])
    df_raw["NetworkType"] = df_raw["Hub (nested)"].apply(lambda h: h.strip() if str(h).strip() in ["FLL", "LAS", "DTW", "MCO"] else "P2P")
    days_op = df_raw.groupby(["ScenarioLabel", "AF"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "AF", "Days Operated"]
    df_raw = df_raw.merge(days_op, on=["ScenarioLabel", "AF"], how="left")
    df_raw["RouteID"] = df_raw["ScenarioLabel"] + ":" + df_raw["AF"]
    df_raw["Raw Yield (¢/mi)"] = df_raw["Constrained Yield (cent, km)"] * 1.60934
    log_lengths = np.log(df_raw["Distance (mi)"] + 1)
    coeffs = np.polyfit(log_lengths.fillna(0), df_raw["Raw Yield (¢/mi)"].fillna(0), 1)
    df_raw["Normalized Yield (¢/mi)"] = coeffs[0] * log_lengths + coeffs[1]
    df_raw["RPM"] = df_raw["Constrained Segment Pax"] * df_raw["Distance (mi)"]
    df_raw["Load Factor"] = df_raw["RPM"] / df_raw["ASM"] * 100
    df_raw["RASM"] = df_raw["Constrained Segment Revenue"] / df_raw["ASM"] * 100
    df_raw["TRASM"] = df_raw["Unconstrained O&D Revenue"] / df_raw["ASM"] * 100

    df_raw["Elasticity"] = df_raw.apply(
        lambda row: 1.2 if row["Constrained Segment Pax"] > 1.1 * row["Seats"] * 0.7 else 1.0,
        axis=1
    )

    mean_yield = df_raw["Normalized Yield (¢/mi)"].mean()
    std_yield = df_raw["Normalized Yield (¢/mi)"].std()
    mean_lf = df_raw["Load Factor"].mean()
    mean_rasm = df_raw["RASM"].mean()
    mean_trasm = df_raw["TRASM"].mean()

    df_raw["Raw Usefulness"] = (
        ((df_raw["Normalized Yield (¢/mi)"] - mean_yield) / std_yield +
         df_raw["Load Factor"] / mean_lf +
         df_raw["RASM"] / mean_rasm +
         df_raw["TRASM"] / mean_trasm) / 4
    ) * df_raw["Elasticity"] * (1 + 0.1 * df_raw["Spill Rate"])

    min_score = df_raw["Raw Usefulness"].min()
    df_raw["Usefulness"] = df_raw["Raw Usefulness"] - min_score if min_score < 0 else df_raw["Raw Usefulness"]

    # 🧠 Add Route Resilience Score
    df_raw = compute_rrs(df_raw, market_avg_fare=11.0)  # or None if unknown

    # 📊 Display
    st.markdown("### ℹ️ Usefulness Score & Route Resilience")
    st.markdown("""This dashboard combines demand elasticity, pricing power, and financial margin
    to assess route viability and resilience. The Route Resilience Score (RRS) models each route’s ability to absorb competitive shocks.""")

    tab1, tab2 = st.tabs(["📊 Summary View", "🔍 Route Analysis"])

    with tab1:
        scenario_options = df_raw["ScenarioLabel"].dropna().unique().tolist()
        selected_scenario = st.selectbox("Scenario", scenario_options, key="summary_scenario")
        df_filtered = df_raw[df_raw["ScenarioLabel"] == selected_scenario].copy()

        st.subheader(f"📊 Summary by Hub — {selected_scenario}")
        hub_summary = df_filtered.groupby("NetworkType").apply(lambda g: pd.Series({
            "Weekly Departures": g.shape[0],
            "ASMs (M)": g["ASM"].sum() / 1_000_000
        })).reset_index().rename(columns={"NetworkType": "Hub"})
        st.dataframe(hub_summary, use_container_width=True)

        st.subheader("📊 System-Level Summary")
        system_summary = df_raw.groupby("ScenarioLabel").apply(lambda g: pd.Series({
            "Weekly Departures": g.shape[0],
            "ASMs (M)": g["ASM"].sum() / 1_000_000
        })).reset_index().rename(columns={"ScenarioLabel": "Scenario"})
        st.dataframe(system_summary, use_container_width=True)

    with tab2:
        st.header("✈️ Route-Level Hub Analysis")
        scenario_choice = st.selectbox("Select Scenario", df_raw["ScenarioLabel"].unique(), key="route_scenario")
        hub_choice = st.selectbox("Select Hub", ["DTW", "LAS", "FLL", "MCO", "P2P"], key="route_hub")
        show_only_cut = st.checkbox("Show only cut routes")

        df_view = df_raw[(df_raw["ScenarioLabel"] == scenario_choice) & (df_raw["NetworkType"] == hub_choice)].copy()
        if show_only_cut:
            df_view = df_view[df_view["Cut"] == 1]

        df_view = df_view.drop_duplicates(subset=["ScenarioLabel", "AF"])
        df_view = df_view.sort_values("Usefulness", ascending=False)

        st.dataframe(df_view[[ 
            "AF", "Departure Airport", "Arrival Airport", "ASM", "RASM", "TRASM", "Load Factor",
            "Raw Yield (¢/mi)", "Normalized Yield (¢/mi)",
            "Usefulness", "RRS", "Cut", "Days Operated"
        ]], use_container_width=True)

except Exception as e:
    st.error(f"Failed to load or process data: {e}")
