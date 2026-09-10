"""Run Scrape page to manually fetch new prices on demand."""

import streamlit as st
import time
import random

import db_setup
import scraper

st.set_page_config(page_title="Run Scrape", page_icon="⚙️")

st.title("⚙️ Run Scrape Now")
st.markdown("Manually trigger a scrape for a subset of products. Please use this sparingly to avoid rate limiting.")

# Fetch how many products we actually have so we can cap the input sensibly
try:
    with db_setup.get_connection() as conn:
        total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
except Exception:
    total_products = 50  # Fallback

if total_products == 0:
    st.info("You don't have any products to scrape. Go to 'Add Product' first.")
else:
    # Cap the maximum scrape at 20 or total_products, whichever is smaller, to prevent abuse from UI
    # The user can run it multiple times if they really need to, but it enforces polite usage.
    max_cap = min(20, total_products)
    
    limit = st.number_input(
        "Number of products to scrape",
        min_value=1,
        max_value=max_cap,
        value=min(5, max_cap),
        help=f"Capped at {max_cap} to ensure polite scraping."
    )
    
    if st.button("Start Scraping", type="primary"):
        st.info("Scraping started. Please do not close or refresh this page until finished.")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        
        try:
            with db_setup.get_connection() as conn, scraper.make_session() as session:
                products_to_scrape = scraper.get_products_to_scrape(conn, limit)
                total = len(products_to_scrape)
                
                for idx, product in enumerate(products_to_scrape):
                    status_text.text(f"Scraping ({idx+1}/{total}): {product['name']}")
                    
                    try:
                        success = scraper.scrape_product(session, conn, product)
                        results.append({
                            "Product": product['name'],
                            "Status": "✅ Success" if success else "❌ Failed"
                        })
                    except Exception as e:
                        results.append({
                            "Product": product['name'],
                            "Status": f"❌ Error: {e}"
                        })
                        
                    # Update progress
                    progress = (idx + 1) / total
                    progress_bar.progress(progress)
                    
                    # Sleep if not the last item
                    if idx < total - 1:
                        delay = random.uniform(
                            scraper.MIN_REQUEST_DELAY_SECONDS, 
                            scraper.MAX_REQUEST_DELAY_SECONDS
                        )
                        status_text.text(f"Waiting {delay:.1f}s to be polite...")
                        time.sleep(delay)
                        
            status_text.text("Scraping completed!")
            st.success("Manual scrape finished.")
            st.cache_data.clear()  # Invalidate cached queries to show new prices
            
            # Show summary
            st.subheader("Run Summary")
            st.table(results)
            
            succeeded = sum(1 for r in results if "Success" in r["Status"])
            st.write(f"**Total:** {total} | **Succeeded:** {succeeded} | **Failed:** {total - succeeded}")
            
        except Exception as e:
            st.error(f"A critical error occurred during setup/scraping: {e}")
