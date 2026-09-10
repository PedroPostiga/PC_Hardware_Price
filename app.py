"""Main entry point for the PC Hardware Price Tracker Streamlit UI."""

import streamlit as st
import pandas as pd

import db_setup
import queries

st.set_page_config(
    page_title="PC Hardware Price Tracker",
    page_icon="💻",
    layout="wide",
)

st.title("💻 PC Hardware Price Tracker")
st.markdown("Welcome to the PC Hardware Price Tracker dashboard. Use the sidebar to navigate.")

@st.cache_data(ttl=900)
def get_dashboard_metrics():
    """Fetch high-level metrics for the dashboard."""
    with db_setup.get_connection() as conn:
        products_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        history_count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        builds_count = conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
        
        target_hits = queries.get_products_at_or_below_target(conn)
        
        return {
            "products_count": products_count,
            "history_count": history_count,
            "builds_count": builds_count,
            "target_hits": [dict(row) for row in target_hits],
        }

try:
    metrics = get_dashboard_metrics()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Products Tracked", metrics["products_count"])
    col2.metric("Price Observations", metrics["history_count"])
    col3.metric("Saved Builds", metrics["builds_count"])
    
    st.subheader("🎯 Target Price Hits")
    hits = metrics["target_hits"]
    if hits:
        df = pd.DataFrame(hits)
        # Format the current price
        if "current_price" in df.columns:
            df["current_price"] = df["current_price"].apply(lambda x: f"€{x:.2f}")
        if "target_price" in df.columns:
            df["target_price"] = df["target_price"].apply(lambda x: f"€{x:.2f}" if pd.notnull(x) else x)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No products are currently at or below their target price.")
        
except Exception as e:
    st.error(f"Error loading dashboard metrics: {e}")
