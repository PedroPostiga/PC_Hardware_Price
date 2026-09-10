"""Build Configurator page to find optimal builds within a budget."""

import streamlit as st
import pandas as pd

import db_setup
import configurator

st.set_page_config(page_title="Build Configurator", page_icon="⚙️")

st.title("⚙️ Build Configurator")
st.markdown("Find the best possible build within your specified budget.")

# Initialize session state for the build result
if "build_result" not in st.session_state:
    st.session_state.build_result = None
if "build_budget" not in st.session_state:
    st.session_state.build_budget = None

budget_input = st.number_input("Budget (€)", min_value=1.0, value=1000.0, step=50.0)

if st.button("Find Best Build", type="primary"):
    with st.spinner("Calculating optimal build..."):
        with db_setup.get_connection() as conn:
            result = configurator.find_best_build(conn, budget_input)
            
            st.session_state.build_result = result
            st.session_state.build_budget = budget_input
            
            if not result:
                st.warning(f"No complete build fits within the €{budget_input:.2f} budget. Try increasing it.")

# Display the result if it exists
if st.session_state.build_result:
    res = st.session_state.build_result
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Budget", f"€{res['budget']:.2f}")
    col2.metric("Total Price", f"€{res['total']:.2f}")
    col3.metric("Headroom", f"€{res['headroom']:.2f}")
    
    st.subheader("Selected Components")
    # Convert components dict to a list of dicts for the dataframe
    components = res["components"]
    comp_list = []
    for cat, data in components.items():
        comp_list.append({
            "Category": cat,
            "Product": data["name"],
            "Price": f"€{data['price']:.2f}",
            "Last Seen": data["scraped_at"]
        })
    
    df = pd.DataFrame(comp_list)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.divider()
    st.subheader("Save this Build")
    with st.form("save_build_form"):
        build_name = st.text_input("Name your build (e.g., 'Dream PC 2024')")
        save_submitted = st.form_submit_button("Save Build")
        
        if save_submitted:
            if not build_name.strip():
                st.error("Please enter a valid build name.")
            else:
                try:
                    with db_setup.get_connection() as conn:
                        # Re-run configurator with save=True
                        # The budget is the same, so it will yield the same deterministic build
                        saved_result = configurator.find_best_build(
                            conn, 
                            st.session_state.build_budget, 
                            save=True, 
                            build_name=build_name.strip()
                        )
                    st.success(f"Build '{build_name}' saved successfully!")
                    st.cache_data.clear()  # Invalidate cached builds
                    # Optionally clear session state: st.session_state.build_result = None
                except Exception as e:
                    st.error(f"Failed to save build: {e}")
