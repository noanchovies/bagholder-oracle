# app.py
import pandas as pd
import yfinance as yf
from flask import Flask, render_template, request
import os
import logging
import sys
from datetime import datetime, timedelta
import json

# --- Configuration ---
PORTFOLIO_CSV = 'portfolio.csv'
RSU_TICKERS = ['META']

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Helper Functions ---
def load_portfolio_from_csv(csv_path):
    # (Function remains the same)
    required_columns = ['Ticker', 'Quantity', 'CostBasis']
    try:
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0: logging.warning(f"'{csv_path}' not found or empty."); return pd.DataFrame(columns=required_columns)
        portfolio_df = pd.read_csv(csv_path)
        if not all(col in portfolio_df.columns for col in required_columns): missing = [col for col in required_columns if col not in portfolio_df.columns]; raise ValueError(f"CSV missing columns: {missing}")
        portfolio_df['Ticker'] = portfolio_df['Ticker'].astype(str).str.strip()
        portfolio_df['Quantity'] = pd.to_numeric(portfolio_df['Quantity'], errors='coerce')
        portfolio_df['CostBasis'] = pd.to_numeric(portfolio_df['CostBasis'], errors='coerce')
        original_rows = len(portfolio_df)
        portfolio_df.dropna(subset=['Quantity', 'CostBasis'], inplace=True)
        portfolio_df = portfolio_df[portfolio_df['Quantity'] > 0]
        if len(portfolio_df) < original_rows: logging.warning(f"Dropped {original_rows - len(portfolio_df)} rows due to invalid/zero data.")
        logging.info(f"Loaded portfolio from '{csv_path}'.")
        return portfolio_df
    except Exception as e: logging.error(f"Error loading portfolio CSV '{csv_path}': {e}", exc_info=True); return pd.DataFrame(columns=required_columns)

def get_stock_data(tickers):
    # (Function remains the same)
     if not tickers: return {}
     stock_data = {}; valid_tickers = [t for t in tickers if t];
     if not valid_tickers: return {}
     try:
        logging.info(f"[Current Data] Fetching for tickers: {valid_tickers}")
        info_objects = yf.Tickers(valid_tickers)
        for ticker in valid_tickers:
            try:
                info = info_objects.tickers[ticker.upper()].fast_info
                current_price = info.get('last_price', info.get('previous_close'))
                currency = info.get('currency', 'N/A'); short_name = info.get('shortName', ticker)
                if current_price is not None: stock_data[ticker] = {'current_price': current_price, 'currency': currency, 'short_name': short_name}
                else:
                     logging.warning(f"fast_info failed for {ticker}, trying history(1d).")
                     hist = yf.Ticker(ticker).history(period="1d")
                     if not hist.empty:
                         current_price = hist['Close'].iloc[-1]
                         if 'currency' not in info or info['currency'] == 'N/A':
                            try: full_info = yf.Ticker(ticker).info; currency = full_info.get('currency', 'N/A'); short_name = full_info.get('shortName', ticker)
                            except Exception: logging.warning(f"Could not get full info for {ticker}")
                         stock_data[ticker] = {'current_price': current_price, 'currency': currency, 'short_name': short_name}
                     else: stock_data[ticker] = {'current_price': 0, 'currency': currency, 'short_name': f"{short_name} (Price N/A)"}
            except Exception as e_ticker: logging.error(f"Error getting current data for {ticker}: {e_ticker}", exc_info=True); stock_data[ticker] = {'current_price': 0, 'currency': 'N/A', 'short_name': f"{ticker} (Fetch Error)"}
        logging.info(f"[Current Data] Finished fetching.")
     except Exception as e_global: logging.error(f"Major error during yfinance Tickers fetch: {e_global}", exc_info=True); stock_data = {t:{'current_price': 0, 'currency': 'N/A', 'short_name': f"{t} (Global Fetch Error)"} for t in valid_tickers}
     return stock_data

def get_historical_data(tickers, portfolio_df):
    # (Function remains the same as stock_tracker_py_csv_reverted_v5)
    if not tickers or portfolio_df.empty: return None
    try:
        logging.info(f"[History] Fetching max daily data for: {tickers}")
        hist_data_raw = yf.download(tickers, period="max", interval="1d", progress=False)
        logging.info(f"[History] Finished fetching.")
        if hist_data_raw.empty: logging.warning("[History] No historical data returned."); return None

        hist_data = None
        if isinstance(hist_data_raw.columns, pd.MultiIndex):
            if 'Close' in hist_data_raw.columns.get_level_values(0): logging.info("[History] Selecting 'Close' from MultiIndex (level 0)."); hist_data = hist_data_raw['Close']
            else:
                 logging.warning("[History] 'Close' not found at level 0, trying swap."); hist_data_swapped = hist_data_raw.swaplevel(axis=1)
                 if 'Close' in hist_data_swapped.columns.get_level_values(0): logging.info("[History] Selecting 'Close' after swap."); hist_data = hist_data_swapped['Close']
                 else: logging.error("[History] Could not find 'Close' column group."); return None
        else:
            if 'Close' in hist_data_raw.columns: logging.info("[History] Selecting 'Close' from simple DF."); hist_data = hist_data_raw[['Close']]
            else: logging.error("[History] Could not find 'Close' column in simple DF."); return None
        if isinstance(hist_data, pd.Series): hist_data = hist_data.to_frame(name=hist_data.name)

        hist_data = hist_data.ffill()
        quantity_map = portfolio_df.set_index('Ticker')['Quantity'].to_dict()
        total_current_cost_basis = portfolio_df['CostBasis'].sum()
        daily_total_values = {}; processed_tickers = []
        for ticker in quantity_map.keys():
            if ticker in hist_data.columns:
                processed_tickers.append(ticker)
                ticker_hist_value = (hist_data[ticker] * quantity_map[ticker])
                for date, value in ticker_hist_value.items():
                    if pd.notna(value): daily_total_values[date] = daily_total_values.get(date, 0) + value
            else: logging.warning(f"[History] No historical 'Close' data processed for: {ticker}")
        if not daily_total_values: logging.warning("[History] Could not calculate daily values."); return None
        logging.info(f"[History] Calculated daily values using: {processed_tickers}")
        sorted_dates = sorted(daily_total_values.keys()); dates_str = [d.strftime('%Y-%m-%d') for d in sorted_dates]
        values = [daily_total_values[d] for d in sorted_dates]; gains = [v - total_current_cost_basis for v in values]
        chart_data = { "dates": dates_str, "values": values, "gains": gains }; logging.info(f"[History] Prepared chart data: {len(dates_str)} points.")
        return chart_data
    except Exception as e: logging.error(f"Error fetching/processing historical data: {e}", exc_info=True); return None

# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    portfolio_df = load_portfolio_from_csv(PORTFOLIO_CSV)
    portfolio_details = []; error_message = None
    total_portfolio_value = 0.0; total_portfolio_cost_basis = 0.0; total_portfolio_gain_loss = 0.0
    rsu_total_value = 0.0; rsu_total_cost_basis = 0.0; rsu_total_gain_loss = 0.0
    non_rsu_total_value = 0.0; non_rsu_total_cost_basis = 0.0; non_rsu_total_gain_loss = 0.0
    value_chart_data = None; gain_chart_data = None

    if not os.path.exists(PORTFOLIO_CSV): error_message = f"Error: '{PORTFOLIO_CSV}' not found."
    elif portfolio_df.empty and os.path.exists(PORTFOLIO_CSV) and os.path.getsize(PORTFOLIO_CSV) == 0: error_message = f"'{PORTFOLIO_CSV}' is empty."
    elif portfolio_df.empty and os.path.exists(PORTFOLIO_CSV): error_message = f"Could not load valid data from '{PORTFOLIO_CSV}'."

    if not portfolio_df.empty:
        tickers = portfolio_df['Ticker'].unique().tolist()
        logging.info(f"Tickers loaded from CSV: {tickers}")
        stock_data = get_stock_data(tickers)

        for index, row in portfolio_df.iterrows():
            ticker = row['Ticker']; quantity = row['Quantity']; cost_basis = row['CostBasis']
            data = stock_data.get(ticker)
            current_price = 0; current_value = 0; avg_purchase_price = 0
            gain_loss = 0; gain_loss_percent = 0; currency = 'N/A'; short_name = ticker
            is_rsu = ticker in RSU_TICKERS
            try:
                quantity = float(quantity); cost_basis = float(cost_basis)
                if quantity != 0: avg_purchase_price = cost_basis / quantity
                else: avg_purchase_price = 0
                total_portfolio_cost_basis += cost_basis
                if data and data.get('current_price') is not None and data['current_price'] > 0:
                    current_price = float(data['current_price']); current_value = quantity * current_price
                    gain_loss = current_value - cost_basis
                    if cost_basis != 0: gain_loss_percent = (gain_loss / cost_basis) * 100
                    currency = data.get('currency', 'N/A'); short_name = data.get('short_name', ticker)
                else:
                    short_name = data.get('short_name', f"{ticker} (Load Error)") if data else f"{ticker} (Not Found)"
                    currency = data.get('currency', 'N/A') if data else 'N/A'; current_value = 0; gain_loss = 0 - cost_basis
                    if cost_basis != 0: gain_loss_percent = -100.0
                total_portfolio_value += current_value; total_portfolio_gain_loss += gain_loss
                if is_rsu: rsu_total_cost_basis += cost_basis; rsu_total_value += current_value; rsu_total_gain_loss += gain_loss
                else: non_rsu_total_cost_basis += cost_basis; non_rsu_total_value += current_value; non_rsu_total_gain_loss += gain_loss
                portfolio_details.append({'ticker': ticker, 'short_name': short_name, 'quantity': quantity, 'avg_purchase_price': avg_purchase_price, 'cost_basis': cost_basis, 'current_price': current_price, 'current_value': current_value, 'gain_loss': gain_loss, 'gain_loss_percent': gain_loss_percent, 'currency': currency, 'is_rsu': is_rsu})
            except Exception as e: logging.error(f"Calculation error for {ticker}: {e}", exc_info=True); portfolio_details.append({'ticker': ticker, 'short_name': f"{ticker} (Calc Error)", 'quantity': quantity, 'avg_purchase_price': 0, 'cost_basis': cost_basis, 'current_price': 0, 'current_value': 0, 'gain_loss': 0, 'gain_loss_percent': 0, 'currency': 'N/A', 'is_rsu': is_rsu})

        portfolio_details.sort(key=lambda x: x['ticker'])
        historical_data = get_historical_data(tickers, portfolio_df)
        if historical_data:
            value_chart_data = {"labels": historical_data["dates"], "datasets": [{"label": "Portfolio Value", "data": historical_data["values"], "borderColor": 'rgb(79, 70, 229)', "tension": 0.1, "pointRadius": 0, "borderWidth": 2}]}
            # --- REMOVED backgroundColor lambda ---
            gain_chart_data = {"labels": historical_data["dates"], "datasets": [{"label": "Portfolio Gain/Loss", "data": historical_data["gains"], "borderColor": 'rgb(16, 185, 129)', "tension": 0.1, "pointRadius": 0, "borderWidth": 2, "fill": { "target": "origin", "above": "rgba(16, 185, 129, 0.1)" } }]}

    primary_currency = 'USD'
    if portfolio_details:
        valid_currencies = [p['currency'] for p in portfolio_details if p['currency'] != 'N/A' and p.get('current_value', 0) > 0]
        if valid_currencies:
            try: primary_currency = max(set(valid_currencies), key=valid_currencies.count)
            except ValueError: primary_currency = 'USD'
        elif any(p['currency'] != 'N/A' for p in portfolio_details):
             primary_currency = next((p['currency'] for p in portfolio_details if p['currency'] != 'N/A'), 'USD')

    current_time_formatted = datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')

    return render_template('index.html',
                           portfolio=portfolio_details,
                           total_value=total_portfolio_value, total_cost_basis=total_portfolio_cost_basis, total_gain_loss=total_portfolio_gain_loss,
                           rsu_total_value=rsu_total_value, rsu_total_cost_basis=rsu_total_cost_basis, rsu_total_gain_loss=rsu_total_gain_loss,
                           non_rsu_total_value=non_rsu_total_value, non_rsu_total_cost_basis=non_rsu_total_cost_basis, non_rsu_total_gain_loss=non_rsu_total_gain_loss,
                           value_chart_data_json=json.dumps(value_chart_data) if value_chart_data else None,
                           gain_chart_data_json=json.dumps(gain_chart_data) if gain_chart_data else None, # Pass gain data
                           primary_currency=primary_currency, error_message=error_message,
                           portfolio_csv_name=PORTFOLIO_CSV, current_time=current_time_formatted)

# --- Main Execution ---
if __name__ == '__main__':
    logging.info("Starting Flask development server...")
    if not os.path.exists(PORTFOLIO_CSV):
         print(f"\nERROR: '{PORTFOLIO_CSV}' not found.\n", file=sys.stderr)
    app.run(debug=True, host='0.0.0.0', port=5001)
