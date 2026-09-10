"""Target Hits page showing products currently at or below their target price."""

import streamlit as st
import pandas as pd

import db_setup
import queries

st.set_page_config(page_title="Target Hits", page_icon="🎯")

st.title("🎯 Target Price Hits")
st.markdown("Products that have reached or fallen below your specified target price.")

@st.cache_data(ttl=900)
def get_target_hits():
    """Fetch all products currently at or below their target price."""
    with db_setup.get_connection() as conn:
        hits = queries.get_products_at_or_below_target(conn)
        return [dict(row) for row in hits]

hits = get_target_hits()

if not hits:
    st.info("No products are currently at or below their target price.")
    st.balloons()  # A little celebration for checking, or just info.
else:
    df = pd.DataFrame(hits)
    
    # Format columns for display
    if "current_price" in df.columns:
        df["current_price"] = df.apply(lambda row: f"€{row['current_price']:.2f}", axis=1)
    if "target_price" in df.columns:
        df["target_price"] = df.apply(lambda row: f"€{row['target_price']:.2f}", axis=1)
    if "amount_below_target" in df.columns:
        df["amount_below_target"] = df.apply(lambda row: f"€{row['amount_below_target']:.2f}", axis=1)
        
    # Reorder or drop columns for a cleaner view if desired, but default is fine.
    # URL can be made clickable if we use st.column_config
    
    st.dataframe(
        df,
        column_config={
            "url": st.column_config.LinkColumn("Product Link"),
            "product_id": None, # Hide ID
        },
        use_container_width=True,
        hide_index=True
    )
