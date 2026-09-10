"""Saved Builds page to view previously saved builds and their current prices."""

import streamlit as st
import pandas as pd

import db_setup
import queries

st.set_page_config(page_title="Saved Builds", page_icon="💾")

st.title("💾 Saved Builds")
st.markdown("Review your saved builds and check their current market total.")

@st.cache_data(ttl=900)
def get_saved_builds():
    """Fetch all saved builds."""
    with db_setup.get_connection() as conn:
        builds = conn.execute("SELECT id, name, budget, created_at FROM builds ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in builds]

@st.cache_data(ttl=900)
def get_build_details(build_name: str):
    """Fetch components and latest prices for a build."""
    with db_setup.get_connection() as conn:
        items = queries.get_build_with_current_total(conn, build_name)
        return [dict(row) for row in items]

builds = get_saved_builds()

if not builds:
    st.info("You haven't saved any builds yet. Go to the 'Build Configurator' to create one.")
else:
    # Prepare selectbox options
    build_options = {b["name"]: f"{b['name']} (Budget: €{b['budget']:.2f})" for b in builds}
    selected_build_name = st.selectbox(
        "Select a Saved Build",
        options=list(build_options.keys()),
        format_func=lambda x: build_options[x]
    )
    
    if selected_build_name:
        items = get_build_details(selected_build_name)
        
        if not items:
            st.error("No components found for this build. It may have been corrupted or deleted.")
        else:
            # The total is repeated on every row, so we just take it from the first
            current_total = items[0]["build_current_total"]
            
            # Find the original budget for comparison
            original_budget = next(b["budget"] for b in builds if b["name"] == selected_build_name)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Original Budget", f"€{original_budget:.2f}")
            
            # Calculate delta if applicable (positive delta is bad for prices, so we might want to inverse it)
            delta = original_budget - current_total 
            # If delta > 0, it's cheaper than budget. If delta < 0, it's over budget.
            
            col2.metric("Current Total", f"€{current_total:.2f}", delta=f"€{delta:.2f} headroom")
            
            st.subheader("Components")
            
            df = pd.DataFrame(items)
            # Clean up columns for display
            df = df.rename(columns={
                "name": "Product",
                "category": "Category",
                "price": "Current Price",
                "currency": "Currency",
                "scraped_at": "Last Updated"
            })
            
            # Format price
            df["Current Price"] = df["Current Price"].apply(lambda x: f"€{x:.2f}" if pd.notnull(x) else "Unknown")
            
            # Drop the repeated total column from the component view
            if "build_current_total" in df.columns:
                df = df.drop(columns=["build_current_total"])
                
            st.dataframe(df, use_container_width=True, hide_index=True)
