import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: ASG vs Spirit vs Base")
st.caption("*All dollar and ASM values shown in thousands")

HUBS = ["DTW", "LAS", "FLL", "MCO", "MSY", "MYR", "ACY", "LGA"]

@st.cache_data
def load_data():
    xls = pd.ExcelFile("root_data.xlsx")
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        df.columns = [str(c).strip() for c in df.columns]

        df.rename(columns={
            "Flight Number": "AF",
            "Departure Day": "Day of Week",
            "Dist mi": "Distance (mi)"
        }, inplace=True)

        df["ScenarioLabel"] = sheet
        if "Distance (mi)" not in df.columns:
            df["Distance (mi)"] = np.nan
        if "Hub (nested)" not in df.columns:
            df["Hub (nested)"] = "P2P"

        df["Distance (mi)"] = pd.to_numeric(df["Distance (mi)"], errors="coerce")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)

def preprocess(df):
    df = df.copy()
    df["AF"] = df["AF"].astype(str)
    df["Seats"] = df.get("Seats", 1)
    df["ASM"] = df.get("ASM", df["Seats"] * df["Distance (mi)"])
    df["Hub"] = df["Hub (nested)"].apply(lambda h: str(h).strip() if str(h).strip() in HUBS else "P2P")
    days_op = df.groupby(["ScenarioLabel", "AF"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "AF", "Days Operated"]
    df = df.merge(days_op, on=["ScenarioLabel", "AF"], how="left")
    df = df.drop_duplicates(subset=["ScenarioLabel", "AF"])
    df["Low Frequency"] = df["Days Operated"] <= 2
    return df

# Load and preprocess
df_raw = preprocess(load_data())

# Select hub
selected_hub = st.selectbox("Select Hub", ["System-wide"] + HUBS, index=0)

# Filter for hub
def filter_hub(df):
    if selected_hub == "System-wide":
        return df.copy()
    return df[df["Hub"] == selected_hub]

# Compare route sets
scenario_labels = df_raw["ScenarioLabel"].unique()
if len(scenario_labels) < 3:
    st.error("Expected at least three scenarios in root_data.xlsx")
else:
    base_label = scenario_labels[0]
    asg_label = scenario_labels[1]
    spirit_label = scenario_labels[2]

    df_base = filter_hub(df_raw[df_raw["ScenarioLabel"] == base_label])
    df_asg = filter_hub(df_raw[df_raw["ScenarioLabel"] == asg_label])
    df_spirit = filter_hub(df_raw[df_raw["ScenarioLabel"] == spirit_label])

    routes_base = set(df_base["AF"])
    routes_asg = set(df_asg["AF"])
    routes_spirit = set(df_spirit["AF"])

    only_asg = routes_asg - routes_spirit - routes_base
    only_spirit = routes_spirit - routes_asg - routes_base
    only_base = routes_base - routes_asg - routes_spirit

    wide_col1, wide_col2 = st.columns([3, 3])
    with wide_col1:
        st.subheader(f"✈️ Routes in {asg_label} but not in {spirit_label} or {base_label}")
        st.dataframe(df_asg[df_asg["AF"].isin(only_asg)][[
            "AF", "Departure Airport", "Arrival Airport", "Days Operated", "ASM", "RASM", "TRASM", "Usefulness", "RRS", "Cut", "Low Frequency"
        ]], use_container_width=True)

    with wide_col2:
        st.subheader(f"✈️ Routes in {spirit_label} but not in {asg_label} or {base_label}")
        st.dataframe(df_spirit[df_spirit["AF"].isin(only_spirit)][[
            "AF", "Departure Airport", "Arrival Airport", "Days Operated", "ASM", "RASM", "TRASM", "Usefulness", "RRS", "Cut", "Low Frequency"
        ]], use_container_width=True)

    st.subheader(f"✈️ Routes in {base_label} but not in {asg_label} or {spirit_label}")
    st.dataframe(df_base[df_base["AF"].isin(only_base)][[
        "AF", "Departure Airport", "Arrival Airport", "Days Operated", "ASM", "RASM", "TRASM", "Usefulness", "RRS", "Cut", "Low Frequency"
    ]], use_container_width=True)

    # Validation Metrics Summary
    st.markdown("""
    ### ℹ️ Usefulness Score & Route Resilience
    Metrics reflect:
    - **Stage-Length-Adjusted TRASM**
    - Adjusted for **Elasticity** and **Spill Rate**
    - Plus: **Route Resilience Score (RRS)**
    """)

    # Validation Summary Table
    st.subheader("🧮 System-Level Validation Summary")
    system_summary = df_raw.groupby("ScenarioLabel").agg({
        "ASM": lambda x: x.sum() / 1_000_000,
        "AF": "nunique",
        "Days Operated": "mean"
    }).reset_index().rename(columns={"ASM": "Total ASMs (M)", "AF": "Route Count", "Days Operated": "Avg Days Operated per Route"})
    st.dataframe(system_summary, use_container_width=True)
