import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: ASG vs Spirit vs Base")
st.caption("*All dollar and ASM values shown in thousands")

HUBS = ["DTW", "LAS", "FLL", "MCO", "MSY", "MYR", "ACY", "LGA"]

@st.cache_data
def load_data():
    df = pd.read_excel("root_data.xlsx")
    df.columns = [str(c).strip() for c in df.columns]

    df.rename(columns={
        "Flight Number": "AF",
        "Departure Day": "Day of Week",
        "Dist mi": "Distance (mi)"
    }, inplace=True)

    if "Distance (mi)" not in df.columns:
        df["Distance (mi)"] = np.nan
    if "Hub (nested)" not in df.columns:
        df["Hub (nested)"] = "P2P"

    df["Distance (mi)"] = pd.to_numeric(df["Distance (mi)"], errors="coerce")
    return df

def preprocess(df):
    df = df.copy()
    df["AF"] = df["AF"].astype(str)
    df["RouteID"] = df["Departure Airport"].astype(str) + ":" + df["Arrival Airport"].astype(str)
    df["Seats"] = df.get("Seats", 1)
    df["ASM"] = df.get("ASM", df["Seats"] * df["Distance (mi)"])
    df["Hub"] = df["Hub (nested)"].apply(lambda h: str(h).strip() if str(h).strip() in HUBS else "P2P")
    days_op = df.groupby(["ScenarioLabel", "RouteID"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "RouteID", "Days Operated"]
    df = df.merge(days_op, on=["ScenarioLabel", "RouteID"], how="left")
    df = df.drop_duplicates(subset=["ScenarioLabel", "RouteID"])
    df["Low Frequency"] = df["Days Operated"] <= 2
    return df

# Load and preprocess
df_raw = preprocess(load_data())

# Define scenario labels from column values
base_label = "Base 0604"
asg_label = "Summer1 (sink or swim) + more new P2P markets for evaluation"
spirit_label = "Summer1 610 refinements"

# Select hub
selected_hub = st.selectbox("Select Hub", ["System-wide"] + HUBS, index=0)

# Filter for hub
def filter_hub(df):
    if selected_hub == "System-wide":
        return df.copy()
    return df[df["Hub"] == selected_hub]

# Compare route sets
df_base = filter_hub(df_raw[df_raw["ScenarioLabel"] == base_label])
df_asg = filter_hub(df_raw[df_raw["ScenarioLabel"] == asg_label])
df_spirit = filter_hub(df_raw[df_raw["ScenarioLabel"] == spirit_label])

routes_base = set(df_base["RouteID"])
routes_asg = set(df_asg["RouteID"])
routes_spirit = set(df_spirit["RouteID"])

only_asg = routes_asg - routes_spirit - routes_base
only_spirit = routes_spirit - routes_asg - routes_base
only_base = routes_base - routes_asg - routes_spirit

wide_col1, wide_col2 = st.columns([3, 3])
with wide_col1:
    st.subheader(f"✈️ Routes in {asg_label} but not in {spirit_label} or {base_label}")
    st.dataframe(df_asg[df_asg["RouteID"].isin(only_asg)][[
        "RouteID", "Departure Airport", "Arrival Airport", "Days Operated", "ASM", "Cut", "Low Frequency"
    ]], use_container_width=True)

with wide_col2:
    st.subheader(f"✈️ Routes in {spirit_label} but not in {asg_label} or {base_label}")
    st.dataframe(df_spirit[df_spirit["RouteID"].isin(only_spirit)][[
        "RouteID", "Departure Airport", "Arrival Airport", "Days Operated", "ASM", "Cut", "Low Frequency"
    ]], use_container_width=True)

st.subheader(f"✈️ Routes in {base_label} but not in {asg_label} or {spirit_label}")
st.dataframe(df_base[df_base["RouteID"].isin(only_base)][[
    "RouteID", "Departure Airport", "Arrival Airport", "Days Operated", "ASM", "Cut", "Low Frequency"
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
    "RouteID": "nunique",
    "Days Operated": "mean"
}).reset_index().rename(columns={"ASM": "Total ASMs (M)", "RouteID": "Route Count", "Days Operated": "Avg Days Operated per Route"})
st.dataframe(system_summary, use_container_width=True)
