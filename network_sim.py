import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Spirit Network Strategy Dashboard", layout="wide")
st.title("🛫 Spirit Airlines Network Planning Dashboard")
st.caption("*All dollar and ASM values shown in thousands")

file_path = "root_data.xlsx"

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
        "Constrained Segment Pax": "Constrained Segment Pax",
        "Constrained Segment Revenue": "Constrained Segment Revenue",
        "ScenarioLabel": "ScenarioLabel"
    }, inplace=True)

    df_raw["Distance (mi)"] = df_raw["Distance (km)"] / 1.60934

    scenario_options = df_raw["ScenarioLabel"].dropna().unique().tolist()
    selected_scenario = st.sidebar.selectbox("Scenario", scenario_options)
    df_raw = df_raw[df_raw["ScenarioLabel"] == selected_scenario]

    flight_freq = df_raw.groupby("AF")["Day of Week"].nunique().reset_index()
    flight_freq.columns = ["AF", "Days Operated"]

    id_fields = ["AF", "Departure Airport", "Arrival Airport", "Hub (nested)"]
    numeric_fields = [
        "Constrained Segment Revenue", "Constrained Yield (cent, km)", "Constrained RASK (cent)",
        "Distance (mi)", "Seats", "Constrained Segment Pax"
    ]

    df_grouped = df_raw.groupby(id_fields, as_index=False)[numeric_fields].sum()
    df = df_grouped.merge(flight_freq, on="AF", how="left")

    df["Route"] = df["Departure Airport"] + "-" + df["Arrival Airport"]
    df["NetworkType"] = df["Hub (nested)"].apply(lambda h: h.strip() if h.strip() in ["FLL", "LAS", "DTW", "MCO"] else "P2P")

    log_lengths = np.log(df["Distance (mi)"] + 1)
    raw_yield = df["Constrained Yield (cent, km)"] * 1.60934
    coeffs = np.polyfit(log_lengths, raw_yield, 1)
    df["Raw Yield (¢/mi)"] = raw_yield
    df["Normalized Yield (¢/mi)"] = coeffs[0] * log_lengths + coeffs[1]

    df["ASM"] = df["Seats"] * df["Distance (mi)"] * df["Days Operated"]
    df["RPM"] = df["Constrained Segment Pax"] * df["Distance (mi)"] * df["Days Operated"]
    df["Load Factor"] = df["RPM"] / df["ASM"] * 100
    df["RASM"] = df["Constrained Segment Revenue"] / df["ASM"] * 100
    df["RASK (¢/mi)"] = df["Constrained RASK (cent)"] * 1.60934

    df["Spill Rate"] = 1.0
    df["Elasticity"] = df.apply(
        lambda row: 1.2 if row["Constrained Segment Pax"] > 1.1 * row["Seats"] * row["Days Operated"] * 0.7 else 1.0,
        axis=1
    )

    mean_yield = df["Normalized Yield (¢/mi)"].mean()
    std_yield = df["Normalized Yield (¢/mi)"].std()
    mean_lf = df["Load Factor"].mean()
    mean_rasm = df["RASM"].mean()

    df["Raw Usefulness"] = (
        ((df["Normalized Yield (¢/mi)"] - mean_yield) / std_yield) *
        (df["Load Factor"] / mean_lf) *
        (df["RASM"] / mean_rasm) *
        (1 + 0.1 * df["Spill Rate"]) *
        df["Elasticity"]
    )

    min_score = df["Raw Usefulness"].min()
    df["Usefulness"] = df["Raw Usefulness"] - min_score if min_score < 0 else df["Raw Usefulness"]

    def compute_market_summary(df):
        result = []
        for name, group in df.groupby("NetworkType"):
            asm = group["ASM"].sum()
            revenue = group["Constrained Segment Revenue"].sum()
            sl = group["Distance (mi)"].mean()
            sla_trasm = np.average(group["Normalized Yield (¢/mi)"], weights=group["ASM"]) if asm > 0 else 0
            result.append({
                "NetworkType": name,
                "Revenue ($000)": revenue / 1000,
                "ASMs (000s)": asm / 1000,
                "SL (mi)": sl,
                "TRASM (¢/mi)": (revenue / asm) * 100 if asm > 0 else 0,
                "SLA_TRASM (¢/mi)": sla_trasm,
                "Seats": group["Seats"].sum(),
                "Deps": group["Days Operated"].sum()
            })
        all_up = df.copy()
        asm = all_up["ASM"].sum()
        revenue = all_up["Constrained Segment Revenue"].sum()
        sl = all_up["Distance (mi)"].mean()
        sla_trasm = np.average(all_up["Normalized Yield (¢/mi)"], weights=all_up["ASM"]) if asm > 0 else 0
        result.append({
            "NetworkType": "System Total",
            "Revenue ($000)": revenue / 1000,
            "ASMs (000s)": asm / 1000,
            "SL (mi)": sl,
            "TRASM (¢/mi)": (revenue / asm) * 100 if asm > 0 else 0,
            "SLA_TRASM (¢/mi)": sla_trasm,
            "Seats": all_up["Seats"].sum(),
            "Deps": all_up["Days Operated"].sum()
        })
        return pd.DataFrame(result)

    market_summary = compute_market_summary(df)

    st.sidebar.header("🛫 Strategic Inputs")
    hub_filter = st.sidebar.selectbox("Hub Focus", ["Full Network", "DTW", "MCO", "LAS", "FLL", "P2P"])
    target_asm = st.sidebar.number_input("🛬 Max Deployable ASM", 0, 10_000_000_000, 800_000_000)
    min_rasm = st.sidebar.number_input("💰 Min Acceptable RASM (¢/mi)", 0.0, 50.0, 8.0)

    df_filtered = df.copy()
    if hub_filter != "Full Network":
        df_filtered = df_filtered[df_filtered["NetworkType"] == hub_filter]
    df_filtered = df_filtered[df_filtered["RASM"] >= min_rasm]

    df_sorted = df_filtered.sort_values("Usefulness", ascending=False).copy()
    df_sorted["CumulativeASM"] = df_sorted["ASM"].cumsum()
    selected = df_sorted[df_sorted["CumulativeASM"] <= target_asm].copy()

    total_asm = df_filtered["ASM"].sum()
    total_rev = df_filtered["Constrained Segment Revenue"].sum()
    avg_rasm = total_rev / total_asm * 100 if total_asm > 0 else 0
    avg_yield = df_filtered["Raw Yield (¢/mi)"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total ASM", f"{total_asm / 1_000_000:,.1f}M")
    col2.metric("Avg RASM", f"{avg_rasm:.2f}¢")
    col3.metric("Avg Yield", f"{avg_yield:.2f}¢/mi")

    st.markdown("---")
    tab1, tab2 = st.tabs(["Route Table + Market Summary", "Top 15 by Usefulness"])

    with tab1:
        st.subheader(f"📈 Filtered Routes for {hub_filter} — {selected_scenario}")
        colA, colB = st.columns([3, 2])
        with colA:
            st.dataframe(df_sorted[[
                "AF", "Route", "NetworkType", "Days Operated", "ASM", "RASM", "Load Factor",
                "Raw Yield (¢/mi)", "Normalized Yield (¢/mi)", "Elasticity", "Usefulness"
            ]], use_container_width=True)
        with colB:
            st.subheader("📊 Market Summary")
            st.dataframe(market_summary, use_container_width=True)

    with tab2:
        st.subheader("🔹 Top 15 Routes")
        st.dataframe(selected.sort_values("Usefulness", ascending=False)[["AF", "Route", "ASM", "RASM", "Usefulness"]].head(15), use_container_width=True)

    st.markdown("---")
    st.download_button("Download CSV", df_sorted.to_csv(index=False), "filtered_routes.csv")

except Exception as e:
    st.error(f"Failed to load or process data from root_data.xlsx: {e}")
