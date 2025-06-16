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
        "Dist mi": "Distance (mi)",
        "Constrained Segment Pax": "Constrained Segment Pax",
        "Constrained Segment Revenue": "Constrained Segment Revenue",
        "ScenarioLabel": "ScenarioLabel"
    }, inplace=True)

    df_raw["Distance (mi)"] = df_raw["Distance (mi)"]
    df_raw["ASM"] = df_raw["Seats"] * df_raw["Distance (mi)"]
    df_raw["AF"] = df_raw["AF"].astype(str)

    st.subheader("📊 Corrected System-Level Summary")
    system_summary = df_raw.groupby("ScenarioLabel").apply(lambda g: pd.Series({
        "Weekly Departures": g.shape[0],
        "ASMs (M)": g["ASM"].sum() / 1_000_000
    })).reset_index()

    system_summary = system_summary[system_summary["ScenarioLabel"].str.contains("Base 0604|Summer1 0610", na=False)]
    system_summary = system_summary.rename(columns={"ScenarioLabel": "Scenario"})

    st.dataframe(system_summary, use_container_width=True)

except Exception as e:
    st.error(f"Failed to load or process data from root_data.xlsx: {e}")
