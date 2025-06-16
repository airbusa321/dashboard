import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Spirit Network Strategy Dashboard", layout="wide")
st.title("🛫 Spirit Airlines Network Planning Dashboard")

file_path = "root_data.xlsx"

try:
    xlsx = pd.ExcelFile(file_path)
    if "NET_in" not in xlsx.sheet_names:
        st.error(f"'NET_in' sheet not found. Available sheets: {xlsx.sheet_names}")
        st.stop()

    df_raw = pd.read_excel(xlsx, sheet_name="NET_in")
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    # Rename critical columns
    df_raw.rename(columns={
        "Flight Number": "AF",
        "Departure Day": "Day of Week",
        "Departure Airport": "Departure Airport",
        "Arrival Airport": "Arrival Airport",
        "Hub (nested)": "Hub (nested)",
        "Distance (km)": "Distance (km)",
        "Constrained Segment Pax": "Constrained Segment Pax",
        "Constrained Segment Revenue": "Constrained Segment Revenue"
    }, inplace=True)

    # Convert distance from km to mi
    df_raw["Distance (mi)"] = df_raw["Distance (km)"] / 1.60934

    # Count days operated per flight
    flight_freq = df_raw.groupby("AF")["Day of Week"].nunique().reset_index()
    flight_freq.columns = ["AF", "Days Operated"]

    # Group and sum relevant columns
    id_fields = ["AF", "Departure Airport", "Arrival Airport", "Hub (nested)"]
    numeric_fields = [
        "Constrained Segment Revenue", "Constrained Yield (cent, km)", "Constrained RASK (cent)",
        "Distance (mi)", "Seats", "Constrained Segment Pax"
    ]

    df_grouped = df_raw.groupby(id_fields, as_index=False)[numeric_fields].sum()
    df = df_grouped.merge(flight_freq, on="AF", how="left")

    # Route & Network Type
    df["Route"] = df["Departure Airport"] + "-" + df["Arrival Airport"]
    df["NetworkType"] = df["Hub (nested)"].apply(lambda h: h.strip() if h.strip() in ["FLL", "LAS", "DTW", "MCO"] else "P2P")

    # Stage-Length Adjusted Normalized Yield (log-linear)
    log_lengths = np.log(df["Distance (mi)"])
    coeffs = np.polyfit(log_lengths, df["Constrained Yield (cent, km)"] * 1.60934, 1)  # convert to ¢/mi
    df["Raw Yield (¢/mi)"] = df["Constrained Yield (cent, km)"] * 1.60934
    df["Normalized Yield (¢/mi)"] = coeffs[0] * np.log(df["Distance (mi)"]) + coeffs[1]

    # ASM and RPM calculations
    df["ASM"] = df["Seats"] * df["Distance (mi)"] * df["Days Operated"]
    df["RPM"] = df["Constrained Segment Pax"] * df["Distance (mi)"] * df["Days Operated"]
    df["Load Factor"] = df["RPM"] / df["ASM"] * 100

    # RASM (¢/mi)
    df["RASM"] = df["Constrained Segment Revenue"] / df["ASM"] * 100

    # RASK (converted to ¢/mi)
    df["RASK (¢/mi)"] = df["Constrained RASK (cent)"] * 1.60934

    # Elasticity & Usefulness
    df["Elasticity"] = df.apply(
        lambda row: 1.2 if row["Constrained Segment Pax"] > 1.1 * row["Seats"] * row["Days Operated"] * 0.7 else 1.0,
        axis=1
    )
    df["Usefulness"] = (
        ((df["RASM"] - df["RASM"].mean()) / df["RASM"].std()) *
        (df["Load Factor"] / df["Load Factor"].mean()) *
        (1 + 0.1 * 1.0) *  # Placeholder Spill Rate = 1.0 if not available
        df["Elasticity"]
    )

    # Sidebar Inputs
    st.sidebar.header("🛫 Strategic Inputs")
    hub_filter = st.sidebar.selectbox("Hub Focus", ["Full Network", "DTW", "MCO", "LAS", "FLL", "P2P"])
    target_asm = st.sidebar.number_input("🛬 Max Deployable ASM", 0, 100_000_000, 5_000_000)
    min_rasm = st.sidebar.number_input("💰 Min Acceptable RASM (\u00a2/mi)", 0.0, 50.0, 8.0)

    # Filter logic
    df_filtered = df.copy()
    if hub_filter != "Full Network":
        df_filtered = df_filtered[df_filtered["NetworkType"] == hub_filter]
    df_filtered = df_filtered[df_filtered["RASM"] >= min_rasm]

    df_sorted = df_filtered.sort_values("Usefulness", ascending=False).copy()
    df_sorted["CumulativeASM"] = df_sorted["ASM"].cumsum()
    selected = df_sorted[df_sorted["CumulativeASM"] <= target_asm].copy()

    # Summary Metrics
    total_asm = df_sorted["ASM"].sum()
    total_rev = df_sorted["Constrained Segment Revenue"].sum()
    avg_rasm = total_rev / total_asm * 100 if total_asm > 0 else 0
    avg_yield = df_sorted["Raw Yield (¢/mi)"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total ASM", f"{total_asm:,.0f}")
    col2.metric("Avg RASM", f"{avg_rasm:.2f}¢")
    col3.metric("Avg Yield", f"{avg_yield:.2f}¢/mi")

    st.markdown("---")
    tab1, tab2 = st.tabs(["Filtered Routes", "Top 15 by Usefulness"])

    with tab1:
        st.subheader(f"📈 Filtered Routes for {hub_filter}")
        st.dataframe(df_sorted[[
            "AF", "Route", "NetworkType", "Days Operated", "ASM", "RASM", "Load Factor",
            "Raw Yield (¢/mi)", "Normalized Yield (¢/mi)", "Elasticity", "Usefulness"
        ]], use_container_width=True)

    with tab2:
        st.subheader("🔵 Top 15 Routes")
        st.dataframe(selected.sort_values("Usefulness", ascending=False)[["AF", "Route", "ASM", "RASM", "Usefulness"]].head(15), use_container_width=True)

    st.markdown("---")
    st.download_button("Download CSV", df_sorted.to_csv(index=False), "filtered_routes.csv")

except Exception as e:
    st.error(f"Failed to load or process data from root_data.xlsx: {e}")
