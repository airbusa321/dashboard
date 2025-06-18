import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Route Comparison Dashboard", layout="wide")
st.title("✈️ Route Comparison: Scenario Insights")
st.caption("*All values in miles (thousands). SLA adjustment via ln(stage length). Usefulness scaled ×1000. ASMs in thousands.")

HUBS = ["DTW", "LAS", "FLL", "MCO", "MSY", "MYR", "ACY", "LGA"]
KM_TO_MI = 0.621371

@st.cache_data
def load_data():
    df = pd.read_excel("root_routes.xlsx")
    df.columns = [str(c).strip() for c in df.columns]

    df.rename(columns={
        "Flight Number": "AF",
        "Departure Day": "Day of Week",
        "Dist mi": "Distance (mi)"
    }, inplace=True)

    df["Hub (nested)"] = df["Hub (nested)"].astype(str).str.strip()
    df["Hub"] = df["Hub (nested)"].apply(lambda h: h if h in HUBS else "P2P")

    df["Distance (mi)"] = pd.to_numeric(df.get("Distance (mi)"), errors="coerce")
    df["Seats"] = pd.to_numeric(df.get("Seats", 1), errors="coerce")
    df["ASM"] = pd.to_numeric(df.get("ASM", df["Seats"] * df["Distance (mi)"]), errors="coerce") / 1000  # ASM in thousands
    df["Constrained Yield (cent, km)"] = pd.to_numeric(df.get("Constrained Yield (cent, km)"), errors="coerce")
    df["Constrained RASK (cent)"] = pd.to_numeric(df.get("Constrained RASK (cent)"), errors="coerce")
    df["Load Factor"] = pd.to_numeric(df["Load Factor"].astype(str).str.replace("%", ""), errors="coerce")
    df["Constrained Connect Fare"] = pd.to_numeric(df.get("Constrained Connect Fare"), errors="coerce")
    df["Constrained Segment Pax"] = pd.to_numeric(df.get("Constrained Segment Pax"), errors="coerce")
    df["Constrained Local Fare"] = pd.to_numeric(df.get("Constrained Local Fare"), errors="coerce")
    df["Constrained Local Pax"] = pd.to_numeric(df.get("Constrained Local Pax"), errors="coerce")
    df["Spill Rate"] = pd.to_numeric(df.get("Spill Rate"), errors="coerce")

    df["RouteID"] = df["Departure Airport"].astype(str) + ":" + df["Arrival Airport"].astype(str)

    df["Day of Week"] = pd.to_numeric(df["Day of Week"], errors="coerce")
    days_op = df.groupby(["ScenarioLabel", "RouteID"])["Day of Week"].nunique().clip(upper=7).reset_index()
    days_op.columns = ["ScenarioLabel", "RouteID", "Days Operated"]
    df = df.merge(days_op, on=["ScenarioLabel", "RouteID"], how="left")
    df["Low Frequency"] = df["Days Operated"] <= 2

    df = df[~((df["Constrained Yield (cent, km)"] == 0) & (df["Constrained RASK (cent)"] == 0))]

    # SLA Adjustments
    df["Stage Length (adj)"] = df["Distance (mi)"].clip(lower=1)
    df["SLA Adj Yield (mi)"] = (df["Constrained Yield (cent, km)"] * KM_TO_MI * 10) / np.log(df["Stage Length (adj)"])
    df["SLA Adj RASM (mi)"] = (df["Constrained RASK (cent)"]) / np.log(df["Stage Length (adj)"])

    df["Connect Share"] = 1 - (df["Constrained Local Pax"] / df["Constrained Segment Pax"])
    df["Connect Share"] = df["Connect Share"].clip(lower=0, upper=1)

    df["Usefulness Score"] = 1000 * (
        df["SLA Adj RASM (mi)"] *
        (df["Load Factor"] / 100) *
        (1 - df["Spill Rate"]) *
        (1 - df["Connect Share"])
    )

    df["Connect Yield"] = df["Constrained Connect Fare"] / df["Constrained Segment Pax"]
    df["Connect vs O-D Yield Ratio"] = 100 * (df["Connect Yield"] / df["Constrained Local Fare"])

    df = df.groupby(["ScenarioLabel", "RouteID", "Hub", "Distance (mi)"]).agg({
        "ASM": "sum",
        "SLA Adj Yield (mi)": "mean",
        "SLA Adj RASM (mi)": "mean",
        "Load Factor": "mean",
        "Usefulness Score": "mean"
    }).reset_index()

    df["Distance (mi)"] = df["Distance (mi)"] / 1000  # Miles in thousands
    df["Load Factor"] = df["Load Factor"]  # Still in %, will be formatted as such later

    return df

df_raw = load_data()

# 📊 Market SLA RASM Summary
st.markdown("### 🏙️ SLA RASM by Hub and Scenario")
sla_summary = df_raw.groupby(["ScenarioLabel", "Hub"])["SLA Adj RASM (mi)"].mean().reset_index()
st.dataframe(sla_summary.style.format({"SLA Adj RASM (mi)": "{:.2f}"}), use_container_width=True)

# rest of code remains unchanged from last version, displays remain
# format dicts below in st.dataframe().style.format need to use:
# {"ASM": "{:.2f}", "Distance (mi)": "{:.1f}", "Load Factor": "{:.1f}%" ...} etc.
