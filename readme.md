# Bagholder Oracle

A responsive, interactive stock portfolio tracker and dashboard built with Python, Flask, and yfinance. 
Displays current holdings, calculates performance metrics, shows historical trends (simplified)

## V1 - V2 - V3 _(includes a daily meme from WallStreetBets_) 
<img src="https://github.com/noanchovies/bagholder-oracle/blob/master/readme-images/V1.png" alt="V1" style="width:32%;"/> <img src="https://github.com/noanchovies/bagholder-oracle/blob/master/readme-images/V2.png" alt="V2" style="width:30%;"/><img src="https://github.com/noanchovies/bagholder-oracle/blob/master/readme-images/V3.png" alt="V3" style="width:60%;"/>

## Technology Stack

* **Backend:** Python 3, Flask
* **Data Fetching:** pandas, yfinance
* **Frontend:** HTML, Tailwind CSS, JavaScript
* **Charting:** Chart.js, chartjs-adapter-date-fns
* **Icons:** lucide-static
## Features

* **Table Interactivity:**
    * Client-side sorting by Ticker, Current Price, and Gain/Loss %.
    * "Toggle Details" button to show/hide Quantity, Avg. Purchase Price, Cost Basis columns.
    * "Hide FAANG RSU" button to show/hide specific RSU tickers (defaults to hidden).
    * "Public Mode" button to hide all absolute monetary and quantity values, showing only Ticker and Gain/Loss %.

* **Portfolio Overview:** Displays holdings read from a local CSV file.
* **Performance Metrics:** Calculates and shows:
    * Average Purchase Price (derived)
    * Cost Basis
    * Current Price (fetched via `yfinance`)
    * Current Value
    * Absolute Gain / Loss
    * Percentage Gain / Loss

* **Dashboard Widgets:**
    * Summary cards for Total Current Value (with Cost Basis note) and Total Gain/Loss.
    * Conditionally displayed breakdown cards for RSU vs Non-RSU Gain/Loss.
    * Historical charts (Value & Gain/Loss) with timeframe selectors (1M, 6M, YTD, 1Y, 2Y, 5Y, Max). **Note:** Uses simplified historical data based on current holdings.
    * "Meme of the Day" widget fetching from `meme-api.com` (r/wallstreetbets).

* **UI Persistence:** Toggle button states (Details, RSU, Public Mode) are saved in the browser's `localStorage`.
* **Styling:** Uses Tailwind CSS (via CDN) and Lucide icons.


## Setup and Running (Local CSV Mode)

1.  **Prerequisites:**
    * Python 3.x installed.
    * `pip` (Python package installer).
    * Git (optional, for cloning).

2.  **Clone the Repository (Optional):**
    ```bash
    git clone [https://github.com/noanchovies/bagholder-oracle.git](https://github.com/noanchovies/bagholder-oracle.git)
    cd bagholder-oracle
    ```
    Or just use the files in your existing project directory.

3.  **Create Virtual Environment:**
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS / Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Ensure `requirements.txt` includes Flask, pandas, yfinance).*

5.  **Create `portfolio.csv`:**
    * Create a file named `portfolio.csv` in the project's root directory.
    * It **must** have the columns: `Ticker`, `Quantity`, `CostBasis`.
    * `Ticker`: The stock ticker symbol recognized by Yahoo Finance (e.g., `MSFT`, `VWCE.DE`).
    * `Quantity`: The number of shares held (can be float or integer).
    * `CostBasis`: The **total** cost basis for the entire quantity held (use standard numbers, e.g., `102100` for 102,100 EUR, `500050.75` for $500050.75). Do **not** use thousands separators.
    * **Example `portfolio.csv`:**
        ```csv
        Ticker,Quantity,CostBasis
        VWCE.DE,xxxx,xxxxxxx
        VUAA.DE,xxxx,xxxxxxx
        MSFT,xxxx,xxxxxxx
        META,xxxx,xxxxxxx
        GOOG,xxxx,xxxxxxx
        ```
    * **Note:** This file is listed in `.gitignore` and should not be committed to version control.

6.  **Configure RSUs (Optional):**
    * Edit `app.py`.
    * Modify the `RSU_TICKERS` list near the top to include the tickers you want treated as RSUs (e.g., `RSU_TICKERS = ['META', 'GOOG']`).

7.  **Run the Application:**
    ```bash
    python app.py
    ```

8.  **Access:** Open your web browser and go to `http://127.0.0.1:5001` (or `http://<your-local-ip>:5001` to access from another device on your network).

## Caveats

* **Mixed Currencies:** The total values and gain/loss figures currently sum up values directly without performing currency conversion. If your portfolio contains holdings in different currencies, these totals are **not financially precise** and are only indicative. The primary currency label shown is based on the most frequent currency among the holdings with a positive value.
* **Simplified Historical Charts:** The historical charts show the performance trend of your *current* holdings based on their past prices relative to your *current* cost basis. They **do not** represent your actual historical portfolio performance, as they don't account for past buys, sells, or changes in cost basis over time.

## Deployment Notes (Future)

This project was previously explored for deployment using Docker, PostgreSQL, and Render. The necessary files (`Dockerfile`, `seed_db.py`, database integration in `app.py`) may exist in the Git history if you wish to revisit cloud deployment later. The primary challenge is managing the portfolio data source (using a database instead of CSV is recommended for deployed environments) and handling secrets like the `DATABASE_URL`.

