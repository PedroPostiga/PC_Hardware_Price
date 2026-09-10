"""Product Browser page for viewing product details and price history."""

import streamlit as st
import pandas as pd

import db_setup
import queries

st.set_page_config(page_title="Product Browser", page_icon="🔍")

st.title("🔍 Product Browser")

@st.cache_data(ttl=900)
def get_products_list():
    """Fetch all products for the dropdown."""
    with db_setup.get_connection() as conn:
        products = conn.execute("SELECT id, name, category, retailer FROM products ORDER BY name").fetchall()
        return [dict(row) for row in products]

@st.cache_data(ttl=900)
def get_product_metrics(product_id: int):
    """Fetch all necessary metrics and history for a given product."""
    with db_setup.get_connection() as conn:
        history = queries.get_price_history(conn, product_id)
        latest = queries.get_latest_price(conn, product_id)
        avg_30d = queries.get_average_price(conn, product_id, days=30)
        pct_change_30d = queries.get_percent_change(conn, product_id, days=30)
        all_time = queries.get_all_time_price_range(conn, product_id)
        
        return {
            "history": [dict(row) for row in history],
            "latest": dict(latest) if latest else None,
            "avg_30d": dict(avg_30d) if avg_30d else None,
            "pct_change_30d": dict(pct_change_30d) if pct_change_30d else None,
            "all_time": dict(all_time) if all_time else None,
        }

products = get_products_list()

if not products:
    st.info("No products available. Go to 'Add Product' to start tracking.")
else:
    # Create a nice format for the selectbox
    product_options = {p["id"]: f"{p['name']} ({p['retailer']})" for p in products}
    selected_id = st.selectbox(
        "Select a Product",
        options=list(product_options.keys()),
        format_func=lambda x: product_options[x]
    )
    
    if selected_id:
        data = get_product_metrics(selected_id)
        
        if not data["history"]:
            st.warning("No price history available for this product yet.")
        else:
            # Layout the metrics
            col1, col2, col3, col4 = st.columns(4)
            
            # Latest price
            if data["latest"]:
                latest_price = data["latest"]["price"]
                currency = data["latest"]["currency"]
                
                # Percent change (if available)
                delta = None
                if data["pct_change_30d"]:
                    pct = data["pct_change_30d"]["percent_change"]
                    delta = f"{pct:.2f}% (30d)"
                    
                col1.metric("Current Price", f"{latest_price:.2f} {currency}", delta=delta, delta_color="inverse")
            
            # 30-day Average
            if data["avg_30d"]:
                avg_price = data["avg_30d"]["average_price"]
                col2.metric("30-Day Average", f"{avg_price:.2f} {currency}")
            else:
                col2.metric("30-Day Average", "N/A")
                
            # All-time High/Low
            if data["all_time"]:
                min_price = data["all_time"]["min_price"]
                max_price = data["all_time"]["max_price"]
                col3.metric("All-Time Low", f"{min_price:.2f} {currency}")
                col4.metric("All-Time High", f"{max_price:.2f} {currency}")
            else:
                col3.metric("All-Time Low", "N/A")
                col4.metric("All-Time High", "N/A")
                
            st.markdown("---")
            st.subheader("Price History Chart")
            
            # Prepare data for chart
            df = pd.DataFrame(data["history"])
            # Convert scraped_at to datetime for better plotting
            df["scraped_at"] = pd.to_datetime(df["scraped_at"])
            df.set_index("scraped_at", inplace=True)
            
            st.line_chart(df["price"], y_label="Price")
            
            # Display history table
            with st.expander("View Raw History Data"):
                st.dataframe(df.reset_index().sort_values("scraped_at", ascending=False), use_container_width=True)
