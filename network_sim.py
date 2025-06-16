import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Spirit Network Strategy Dashboard", layout="wide")
st.title("🛫 Spirit Airlines Network Planning Dashboard")

# Load Excel file from current directory (for GitHub/Streamlit Cloud)
file_path = "root_data.xlsx"

try:
df = pd.read_excel(file_path, sheet_name="Base")
df.columns = [str(c).strip() for c in df.columns]

# Ensure relevant columns are numeric
numeric_cols = [
"ASM", "Constrained Segment Revenue", "Constrained Yield (cent, km)",
"Constrained RASK (cent)", "Load Factor", "Spill Rate",
"Unconstrained Segment Pax", "Constrained Segment Pax",
"Constrained Local Revenue", "Constrained RPK",
"Unconstrained Segment Revenue", "Unconstrained RPK"
]
for col in numeric_cols:
if col in df.columns:
df[col] = pd.to_numeric(df[col], errors='coerce')

# Derived route and hub type
df["Route"] = df["Departure Airport"] + "-" + df["Arrival Airport"]
df["NetworkType"] = df.apply(lambda row: row["Hub (nested)"].strip() if row["Hub (nested)"].strip() in ["FLL", "LAS", "DTW", "MCO"] else "P2P", axis=1)

# Elasticity factor based on spill
df["Elasticity"] = df.apply(
lambda row: 1.2 if row.get("Unconstrained Segment Pax", 0) > row.get("Constrained Segment Pax", 0) * 1.1 else 1.0,
axis=1
)

# Usefulness score based on Belobaba-style multidimensional optimization
df["Usefulness"] = (
((df["Constrained RASK (cent)"] - df["Constrained RASK (cent)"].mean()) / df["Constrained RASK (cent)"].std()) *
(df["Load Factor"] / df["Load Factor"].mean()) *
(1 + 0.1 * df["Spill Rate"]) *
df["Elasticity"]
)

# Revenue and performance ratios
df["TotalASM"] = df["ASM"]
df["TotalRevenue"] = df["Constrained Segment Revenue"]
df["RASM"] = df["TotalRevenue"] / df["TotalASM"] * 100
df["WeightedYield"] = df["Constrained Yield (cent, km)"] * df["TotalASM"]

# Sidebar Controls
st.sidebar.header("🎯 Strategic Inputs")
target_asm = st.sidebar.number_input("Target ASM", 0, 100_000_000, 5_000_000)
target_rasm = st.sidebar.number_input("Target RASM (¢)", 0.0, 50.0, 9.0)
target_yield = st.sidebar.number_input("Target Yield (¢/km)", 0.0, 50.0, 12.0)

# Filter top routes by usefulness within ASM constraint
df_sorted = df.sort_values("Usefulness", ascending=False).copy()
df_sorted["CumulativeASM"] = df_sorted["TotalASM"].cumsum()
selected = df_sorted[df_sorted["CumulativeASM"] <= target_asm].copy()

# Summary Metrics
total_asm = selected["TotalASM"].sum()
total_rev = selected["TotalRevenue"].sum()
avg_rasm = total_rev / total_asm * 100 if total_asm > 0 else 0
avg_yield = selected["WeightedYield"].sum() / total_asm if total_asm > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("Total ASM", f"{total_asm:,.0f}")
col2.metric("Avg RASM", f"{avg_rasm:.2f}¢")
col3.metric("Avg Yield", f"{avg_yield:.2f}¢/km")

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(["Top Routes", "Routes to Cut", "Hub Summary", "Details"])

with tab1:
st.subheader("🟢 Top 15 Routes by Usefulness")
st.dataframe(selected.sort_values("Usefulness", ascending=False)[["Route", "Hub (nested)", "TotalASM", "RASM", "Usefulness"]].head(15), use_container_width=True)

with tab2:
st.subheader("🔴 Bottom 15 Routes (Cut Candidates)")
to_cut = df_sorted[~df_sorted["Route"].isin(selected["Route"])]
st.dataframe(to_cut.sort_values("Usefulness", ascending=True)[["Route", "Hub (nested)", "TotalASM", "RASM", "Usefulness"]].head(15), use_container_width=True)

with tab3:
st.subheader("📍 Hub Network Summary")
hub_summary = selected.groupby("NetworkType").agg(
TotalASM=("TotalASM", "sum"),
AvgRASM=("RASM", "mean"),
Routes=("Route", "count")
).reset_index()
st.dataframe(hub_summary, use_container_width=True)

with tab4:
st.subheader("📋 Full Scenario Table")
st.dataframe(df_sorted, use_container_width=True)

st.markdown("---")
st.subheader("📥 Download Selected Routes")
st.download_button("Download CSV", selected.to_csv(index=False), "selected_routes.csv")

except Exception as e:
st.error("Failed to load data from root_data.xlsx: {}".format(e))
