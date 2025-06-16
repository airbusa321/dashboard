import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Spirit Network Strategy Dashboard", layout="wide")
st.title("🛫 Spirit Airlines Network Planning Dashboard")

file_path = "root_data.xlsx"

try:
    # Load and clean
    xlsx = pd.ExcelFile(file_path)
    if "NET_in" not in xlsx.sheet_names:
        st.error(f"'NET_in' sheet not found. Available sheets: {xlsx.sheet_names}")
        st.stop()

    df_raw = pd.read_excel(xlsx, sheet_name="NET_in")
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    # Rename columns to standard names used in logic
    df_raw.rename(columns={
        "Flight Number": "AF",
        "Departure Day": "Day of Week",
        "Departure Airport": "Departure Airport",
        "Arrival Airport": "Arrival Airport",
        "Hub (nested)": "Hub (nested)"
    }, inplace=True)

    # Count operating days per flight number
    flight_freq = df_raw.groupby("AF")["Day of Week"].nunique().reset_index()
    flight_freq.columns = ["AF", "Days Operated"]

    # Define columns to group by and sum
    id_fields = ["AF", "Departure Airport", "Arrival Airport", "Hub (nested)"]
    numeric_fields = [
        "ASM", "Constrained Segment Revenue", "Constrained Yield (cent, km)",
        "Constrained RASK (cent)", "Load Factor", "Spill Rate",
        "Unconstrained Segment Pax", "Constrained Segment Pax",
        "Constrained Local Revenue", "Constrained RPK",
        "Unconstrained Segment Revenue", "Unconstrained RPK"
    ]

    # Group by flight number
    df_grouped = df_raw.groupby(id_fields, as_index=False)[numeric_fields].sum()
    df = df_grouped.merge(flight_freq, on="AF", how="left")

    # Derived fields
    df["Route"] = df["Departure Airport"] + "-" + df["Arrival Airport"]
    df["NetworkType"] = df.apply(
        lambda row: row["Hub (nested)"].strip() if row["Hub (nested)"].strip() in ["FLL", "LAS", "DTW", "MCO"] else "P2P",
        axis=1
    )
    df["Elasticity"] = df.apply(
        lambda row: 1.2 if row.get("Unconstrained Segment Pax", 0) > row.get("Constrained Segment Pax", 0) * 1.1 else 1.0,
        axis=1
    )
    df["Usefulness"] = (
        ((df["Constrained RASK (cent)"] - df["Constrained RASK (cent)"].mean()) / df["Constrained RASK (cent)"].std()) *
        (df["Load Factor"] / df["Load Factor"].mean()) *
        (1 + 0.1 * df["Spill Rate"]) *
        df["Elasticity"]
    )
    df["TotalASM"] = df["ASM"]
    df["TotalRevenue"] = df["Constrained Segment Revenue"]
    df["RASM"] = df["TotalRevenue"] / df["TotalASM"] * 100
    df["WeightedYield"] = df["Constrained Yield (cent, km)"] * df["TotalASM"]

    # === Sidebar Inputs ===
    st.sidebar.header("✈️ Network Planning Inputs")
    hub_filter = st.sidebar.selectbox("Hub Focus", ["Full Network", "DTW", "MCO", "LAS", "FLL", "P2P"])
    target_asm = st.sidebar.number_input("🛫 Max Deployable ASM", 0, 100_000_000, 5_000_000)
    min_rasm = st.sidebar.number_input("💰 Min Acceptable RASM (¢)", 0.0, 50.0, 8.0)

    # === Apply Filters ===
    df_filtered = df.copy()
    if hub_filter != "Full Network":
        df_filtered = df_filtered[df_filtered["NetworkType"] == hub_filter]
    df_filtered = df_filtered[df_filtered["RASM"] >= min_rasm]

    df_sorted = df_filtered.sort_values("Usefulness", ascending=False).copy()
    df_sorted["CumulativeASM"] = df_sorted["TotalASM"].cumsum()
    selected = df_sorted[df_sorted["CumulativeASM"] <= target_asm].copy()

    # === Summary Metrics ===
    total_asm = df_sorted["TotalASM"].sum()
    total_rev = df_sorted["TotalRevenue"].sum()
    avg_rasm = total_rev / total_asm * 100 if total_asm > 0 else 0
    avg_yield = df_sorted["WeightedYield"].sum() / total_asm if total_asm > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total ASM", f"{total_asm:,.0f}")
    col2.metric("Avg RASM", f"{avg_rasm:.2f}¢")
    col3.metric("Avg Yield", f"{avg_yield:.2f}¢/km")

    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs(["Filtered Routes", "Top 15", "Hub Summary", "Details"])

    with tab1:
        st.subheader(f"📈 Filtered Routes for {hub_filter}")
        st.dataframe(df_sorted[[
            "AF", "Route", "NetworkType", "Days Operated", "TotalASM", "RASM",
            "Load Factor", "Spill Rate", "Elasticity", "Usefulness"
        ]], use_container_width=True)

    with tab2:
        st.subheader("🟢 Top 15 Routes by Usefulness")
        st.dataframe(selected.sort_values("Usefulness", ascending=False)[[
            "AF", "Route", "TotalASM", "RASM", "Usefulness"
        ]].head(15), use_container_width=True)

    with tab3:
        st.subheader("📍 Hub Network Summary")
        hub_summary = df_sorted.groupby("NetworkType").agg(
            TotalASM=("TotalASM", "sum"),
            AvgRASM=("RASM", "mean"),
            Routes=("Route", "count")
        ).reset_index()
        st.dataframe(hub_summary, use_container_width=True)

    with tab4:
        st.subheader("📋 Full Scenario Table")
        st.dataframe(df_sorted, use_container_width=True)

    st.markdown("---")
    st.subheader("📥 Download Filtered Routes")
    st.download_button("Download CSV", df_sorted.to_csv(index=False), f"{hub_filter.lower()}_routes.csv")

    with st.expander("📊 How Usefulness is Calculated"):
        st.markdown("""
        The **Usefulness** score ranks each flight by strategic contribution under constrained capacity.

        **Formula:**
        ```
        Usefulness =
            (RASK - Avg RASK) / Std RASK ×
            (Load Factor / Avg Load Factor) ×
            (1 + 0.1 × Spill Rate) ×
            Elasticity
        ```

        Your filters:
        - ✅ Capacity constraint: Max ASM
        - ✅ Profitability filter: Min RASM
        - ✅ Focus area: Selected hub

        This model prioritizes high-yield, high-spill, efficient flights that justify scarce aircraft time.
        """)

except Exception as e:
    st.error(f"Failed to load or process data from root_data.xlsx: {e}")
