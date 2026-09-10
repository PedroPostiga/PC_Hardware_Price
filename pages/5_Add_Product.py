"""Add Product page for tracking new PC components."""

import streamlit as st

import add_product

st.set_page_config(page_title="Add Product", page_icon="➕")

st.title("➕ Add Product")
st.markdown("Track a new PC component from PCComponentes.")

with st.form("add_product_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        name = st.text_input("Product Name", help="A descriptive name for the product.")
        category = st.text_input("Category", help="e.g., CPU, GPU, RAM, Motherboard")
        
    with col2:
        retailer = st.text_input("Retailer", value="PC Componentes", disabled=True)
        # Note: We keep retailer text input disabled as scraper only supports PCComponentes currently
        url = st.text_input("Product URL", help="Must be a valid pccomponentes.pt URL.")
        
    target_price_enabled = st.checkbox("Set a Target Price")
    
    if target_price_enabled:
        target_price = st.number_input("Target Price (€)", min_value=0.0, step=1.0)
    else:
        target_price = None
        
    submit = st.form_submit_button("Add Product")
    
    if submit:
        if not name.strip() or not category.strip() or not url.strip():
            st.error("Name, Category, and URL are required.")
        else:
            try:
                # Add product wrapper expects string retailer, even though it's disabled in UI it might not pass.
                # So we hardcode "PCComponentes" just to be safe.
                added = add_product.add_product(
                    name=name,
                    category=category,
                    retailer="PC Componentes",
                    url=url,
                    target_price=target_price
                )
                
                if added:
                    st.success(f"Successfully added {name}!")
                    st.cache_data.clear()  # Invalidate cached queries to show new product immediately
                else:
                    st.info(f"{name} is already being tracked (URL already exists).")
                    
            except ValueError as e:
                st.error(f"Error adding product: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")
