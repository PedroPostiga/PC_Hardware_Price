# 💻 PC Hardware Price Tracker

A comprehensive, locally-hosted python application to track, analyze, and optimize PC component prices from PCComponentes.

This tool acts as your personal price-watching assistant, featuring polite automated scraping, target price notifications, an algorithmic build configurator, and a full Streamlit dashboard to monitor the market.

## ✨ Features

* **Polite Automated Scraping**: Runs daily on a schedule to fetch the latest prices using randomized delays to avoid rate limits.
* **Target Price Notifications**: Set target prices for your desired components and get notified when the price drops at or below your target.
* **Algorithmic Build Configurator**: Input a budget, and the app uses a dynamic programming knapsack algorithm to calculate the absolute best complete PC build you can buy right now without going over budget.
* **Streamlit Dashboard**: A rich, interactive, multi-page UI to browse products, view historical price charts, manage your target hits, run manual scrapes, and view saved builds.
* **Robust Data Storage**: Backed by a local SQLite database that stores a full history of all price fluctuations over time.
* **Data Exports**: Easily export your price history, current snapshots, or saved builds to JSON or CSV for external analysis.

## 🛠️ Technology Stack

* **Language**: Python 3.11+
* **Database**: SQLite3
* **Scraping**: `requests`, `BeautifulSoup4`
* **Data & Visualization**: `pandas`, `matplotlib`, `streamlit`
* **Scheduling**: `schedule`

## 🚀 Getting Started

### 1. Prerequisites & Installation

Ensure you have Python 3.11+ installed. Create a virtual environment and install the required dependencies:

```bash
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install requests beautifulsoup4 pandas matplotlib streamlit schedule
```

### 2. Initialize the Database

Run the database setup script to create the necessary tables and schema:

```bash
python db_setup.py
```

*(Optional)* If you want to test the app with dummy data before adding real links, you can run the seed script:
```bash
python seed_fake_data.py
```

### 3. Start the Application

The project consists of two main execution contexts that can run concurrently:

**The Streamlit Dashboard (UI)**:
Launch the interactive dashboard to add products, view charts, and configure builds.
```bash
python -m streamlit run app.py
```

**The Automated Scheduler (Background)**:
Leave this running in a terminal to automatically scrape prices daily and log target hits.
```bash
python run_scheduler.py
```

## 📖 App Structure (Pages)

1. **Dashboard**: High-level metrics on tracked products and recent price drops.
2. **Product Browser**: Interactive charts showing the price history and all-time highs/lows for specific components.
3. **Target Hits**: A clean table of products that have reached your set target price.
4. **Build Configurator**: Tell the app your budget, and it will compute the best possible build you can afford today based on the latest scraped prices.
5. **Saved Builds**: Keep track of builds you've generated and watch how their total price fluctuates over time.
6. **Add Product**: Add new PCComponentes URLs to your tracking database.
7. **Run Scrape Now**: Manually trigger a polite, rate-limited scrape of your products.
8. **Data Exports**: Export your SQLite data to CSV or JSON formats.

## ⚠️ Disclaimer

This project is intended for personal, educational use. The scraper is intentionally designed to be polite, implementing mandatory delays (`time.sleep`) between requests to respect the retailer's servers.
