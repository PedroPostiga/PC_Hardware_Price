"""Exports page to generate and download data from the price tracker."""

import streamlit as st
import os
from pathlib import Path

import db_setup
import export

st.set_page_config(page_title="Data Exports", page_icon="📥")

st.title("📥 Data Exports")
st.markdown("Generate and download CSV or JSON exports of your tracking data.")

export_type = st.radio(
    "Select what to export:",
    ["Price History", "Current Snapshot", "Saved Builds"]
)

format_type = st.radio(
    "Select format:",
    ["CSV", "JSON", "Both (CSV + JSON)"]
)

# Map UI choices to internal types
format_map = {
    "CSV": "csv",
    "JSON": "json",
    "Both (CSV + JSON)": "both"
}

if st.button("Generate Export", type="primary"):
    with st.spinner("Generating export files..."):
        try:
            with db_setup.get_connection() as conn:
                output_format = format_map[format_type]
                
                if export_type == "Price History":
                    files_created = export.export_price_history(conn, output_format)
                elif export_type == "Current Snapshot":
                    files_created = export.export_current_snapshot(conn, output_format)
                elif export_type == "Saved Builds":
                    files_created = export.export_saved_builds(conn, output_format)
                    
            if not files_created:
                st.warning("No data found to export for the selected category.")
            else:
                st.success("Export generated successfully!")
                
                st.markdown("### Download Links")
                for file_path in files_created:
                    path_obj = Path(file_path)
                    if path_obj.exists():
                        with open(path_obj, "rb") as f:
                            file_data = f.read()
                        
                        st.download_button(
                            label=f"Download {path_obj.name}",
                            data=file_data,
                            file_name=path_obj.name,
                            mime="text/csv" if path_obj.suffix == ".csv" else "application/json"
                        )
                    else:
                        st.error(f"File not found: {file_path}")
                        
        except Exception as e:
            st.error(f"Failed to generate export: {e}")
