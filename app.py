# app.py
import pandas as pd
import yfinance as yf
from flask import Flask, render_template, request
import os
import logging
import sys

# --- Configuration ---
PORTFOLIO_CSV = 'portfolio.csv' # Name of your portfolio CSV file

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Helper Functions ---
def load_portfolio_from_csv(csv_path):
    """Loads portfolio data from a CSV file including CostBasis."""
    required_columns = ['Ticker', 'Quantity', 'CostBasis']
    try:
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
            logging.warning(f"'{csv_path}' not found or is empty. Returning empty DataFrame.")
            return pd.DataFrame(columns=required_columns)

        # Read the CSV
        portfolio_df = pd.read_csv(csv_path)

        # --- Validation ---
        if not all(col in portfolio_df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in portfolio_df.columns]
            raise ValueError(f"CSV must contain required columns. Missing: {missing}")

        # --- Type Conversion & Cleaning ---
        portfolio_df['Ticker'] = portfolio_df['Ticker'].astype(str).str.strip()
        portfolio_df['Quantity'] = pd.to_numeric(portfolio_df['Quantity'], errors='coerce')
        # CostBasis should be numeric (handles integers from your last CSV format)
        portfolio_df['CostBasis'] = pd.to_numeric(portfolio_df['CostBasis'], errors='coerce')

        # Drop rows where essential numeric conversions failed or quantity is zero
        original_rows = len(portfolio_df)
        portfolio_df.dropna(subset=['Quantity', 'CostBasis'], inplace=True)
        portfolio_df = portfolio_df[portfolio_df['Quantity'] > 0] # Remove rows with 0 quantity

        if len(portfolio_df) < original_rows:
             logging.warning(f"Dropped {original_rows - len(portfolio_df)} rows due to invalid/zero numeric data in Quantity or CostBasis.")

        logging.info(f"Successfully loaded and validated portfolio from '{csv_path}'.")
        return portfolio_df

    except pd.errors.EmptyDataError:
        logging.warning(f"'{csv_path}' is empty. Returning empty DataFrame.")
        return pd.DataFrame(columns=required_columns)
    except FileNotFoundError:
        logging.error(f"Error: Portfolio file '{csv_path}' not found.")
        return pd.DataFrame(columns=required_columns)
    except ValueError as ve:
        logging.error(f"Data validation error in '{csv_path}': {ve}")
        return pd.DataFrame(columns=required_columns)
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading '{csv_path}': {e}", exc_info=True)
        return pd.DataFrame(columns=required_columns)

def get_stock_data(tickers):
    """Fetches current stock data using yfinance."""
    # (This function remains the same)
    if not tickers:
        logging.info("No tickers provided to fetch data for.")
        return {}

    stock_data = {}
    valid_tickers = [t for t in tickers if t]
    if not valid_tickers:
        logging.warning("Ticker list is empty after filtering.")
        return {}

    try:
        logging.info(f"Attempting to fetch data for tickers: {valid_tickers}")
        data = yf.download(valid_tickers, period="1d", group_by='ticker', threads=True)

        logging.info("Fetching additional info (name, currency)...")
        ticker_infos = {}
        try:
            info_objects = yf.Tickers(valid_tickers)
            for ticker in valid_tickers:
                 try:
                     if ticker.upper() in info_objects.tickers:
                         ticker_infos[ticker] = info_objects.tickers[ticker.upper()].info
                     else:
                         logging.warning(f"Ticker {ticker} not in batch info, trying individually.")
                         ticker_infos[ticker] = yf.Ticker(ticker).info
                 except Exception as e_info_ind:
                     logging.error(f"Could not get .info for {ticker}: {e_info_ind}")
                     ticker_infos[ticker] = {}
        except Exception as e_info:
            logging.error(f"Error fetching batch .info data: {e_info}", exc_info=True)
            for ticker in valid_tickers: ticker_infos[ticker] = {}

        logging.info("Processing downloaded data...")
        for ticker in valid_tickers:
            current_price = None
            currency = 'N/A'
            short_name = ticker
            info = ticker_infos.get(ticker, {})
            currency = info.get('currency', 'N/A')
            short_name = info.get('shortName', ticker)

            try:
                price_data_available = False
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker in data.columns.get_level_values(0) and 'Close' in data[ticker].columns and not data[ticker]['Close'].empty:
                         current_price = data[ticker]['Close'].iloc[-1]
                         price_data_available = True
                elif ticker in data.columns and 'Close' in data.columns and not data['Close'].empty:
                     current_price = data['Close'].iloc[-1]
                     price_data_available = True

                if price_data_available and current_price is not None and not pd.isna(current_price):
                    stock_data[ticker] = {'current_price': current_price, 'currency': currency, 'short_name': short_name}
                else:
                    stock_data[ticker] = {'current_price': 0, 'currency': currency, 'short_name': f"{short_name} (Price N/A)"}
            except Exception as e_ticker:
                logging.error(f"Error processing data for ticker {ticker}: {e_ticker}", exc_info=True)
                stock_data[ticker] = {'current_price': 0, 'currency': currency, 'short_name': f"{short_name} (Processing Error)"}
        logging.info(f"Finished processing yfinance data.")
    except Exception as e_global:
        logging.error(f"Major error during yfinance download/processing: {e_global}", exc_info=True)
        for ticker in valid_tickers: stock_data[ticker] = {'current_price': 0, 'currency': 'N/A', 'short_name': f"{ticker} (Global Fetch Error)"}
    return stock_data

# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    """Main route to display the portfolio from CSV with gain/loss."""
    portfolio_df = load_portfolio_from_csv(PORTFOLIO_CSV) # Load from CSV
    portfolio_details = []
    error_message = None
    total_portfolio_value = 0.0
    total_portfolio_cost_basis = 0.0
    total_portfolio_gain_loss = 0.0

    # Check CSV status
    if not os.path.exists(PORTFOLIO_CSV):
        error_message = f"Error: '{PORTFOLIO_CSV}' not found."
    elif portfolio_df.empty and os.path.exists(PORTFOLIO_CSV) and os.path.getsize(PORTFOLIO_CSV) == 0:
         error_message = f"'{PORTFOLIO_CSV}' is empty. Please add Ticker,Quantity,CostBasis data."
    elif portfolio_df.empty and os.path.exists(PORTFOLIO_CSV):
         error_message = f"Could not load valid data from '{PORTFOLIO_CSV}'. Check format (Ticker,Quantity,CostBasis) and logs."

    if not portfolio_df.empty:
        tickers = portfolio_df['Ticker'].unique().tolist()
        logging.info(f"Tickers loaded from CSV: {tickers}")
        stock_data = get_stock_data(tickers)

        # Calculate current value and gain/loss for each holding from DataFrame
        for index, row in portfolio_df.iterrows(): # Iterate over DataFrame rows
            ticker = row['Ticker']
            quantity = row['Quantity']
            cost_basis = row['CostBasis'] # Get CostBasis directly from row

            # Skip if essential data is missing (already checked in load_portfolio_from_csv)
            # if not ticker or pd.isna(quantity) or pd.isna(cost_basis): continue # Redundant check

            data = stock_data.get(ticker)
            current_price = 0
            current_value = 0
            avg_purchase_price = 0
            gain_loss = 0
            gain_loss_percent = 0
            currency = 'N/A'
            short_name = ticker

            try:
                # Values from DataFrame should be numeric types after load
                quantity = float(quantity)
                cost_basis = float(cost_basis)

                if quantity != 0: avg_purchase_price = cost_basis / quantity
                else: avg_purchase_price = 0

                total_portfolio_cost_basis += cost_basis # Sum (mixes currencies)

                if data and data.get('current_price') is not None and data['current_price'] > 0:
                    current_price = float(data['current_price'])
                    current_value = quantity * current_price
                    gain_loss = current_value - cost_basis
                    if cost_basis != 0: gain_loss_percent = (gain_loss / cost_basis) * 100

                    currency = data.get('currency', 'N/A')
                    short_name = data.get('short_name', ticker)
                    total_portfolio_value += current_value # Sum (mixes currencies)
                    total_portfolio_gain_loss += gain_loss # Sum (mixes currencies)
                else:
                    short_name = data.get('short_name', f"{ticker} (Load Error)") if data else f"{ticker} (Not Found)"
                    currency = data.get('currency', 'N/A') if data else 'N/A'
                    current_value = 0
                    gain_loss = 0 - cost_basis
                    if cost_basis != 0: gain_loss_percent = -100.0

                portfolio_details.append({
                    'ticker': ticker, 'short_name': short_name, 'quantity': quantity,
                    'avg_purchase_price': avg_purchase_price, 'cost_basis': cost_basis,
                    'current_price': current_price, 'current_value': current_value,
                    'gain_loss': gain_loss, 'gain_loss_percent': gain_loss_percent,
                    'currency': currency
                })

            except ValueError as ve:
                 logging.error(f"Calculation error for {ticker}: {ve}", exc_info=True)
                 portfolio_details.append({'ticker': ticker, 'short_name': f"{ticker} (Calc Error)", 'quantity': quantity, 'avg_purchase_price': 0, 'cost_basis': cost_basis, 'current_price': 0, 'current_value': 0, 'gain_loss': 0, 'gain_loss_percent': 0, 'currency': 'N/A'})
            except Exception as e:
                 logging.error(f"Unexpected error during calculation for {ticker}: {e}", exc_info=True)

    # Sort portfolio details alphabetically by ticker
    portfolio_details.sort(key=lambda x: x['ticker'])

    # Determine the primary currency for display purposes (still mixes values)
    primary_currency = 'USD'
    if portfolio_details:
        valid_currencies = [p['currency'] for p in portfolio_details if p['currency'] != 'N/A' and p.get('current_value', 0) > 0]
        if valid_currencies:
            try: primary_currency = max(set(valid_currencies), key=valid_currencies.count)
            except ValueError: primary_currency = 'USD'
        elif any(p['currency'] != 'N/A' for p in portfolio_details):
             primary_currency = next((p['currency'] for p in portfolio_details if p['currency'] != 'N/A'), 'USD')

    # *** Reminder: Totals below mix currencies and are not financially precise ***
    return render_template('index.html',
                           portfolio=portfolio_details,
                           total_value=total_portfolio_value,
                           total_cost_basis=total_portfolio_cost_basis,
                           total_gain_loss=total_portfolio_gain_loss,
                           primary_currency=primary_currency, # Label for the inaccurate totals
                           error_message=error_message,
                           portfolio_csv_name=PORTFOLIO_CSV) # Pass CSV name back


# --- Main Execution ---
if __name__ == '__main__':
    logging.info("Starting Flask development server...")
    # Ensure the portfolio CSV exists before starting
    if not os.path.exists(PORTFOLIO_CSV):
         print(f"\nERROR: '{PORTFOLIO_CSV}' not found. Please create it with Ticker,Quantity,CostBasis columns.\n", file=sys.stderr)
    # Run the Flask development server
    # Host 0.0.0.0 makes it accessible on the local network
    # Debug=True is helpful for local development
    app.run(debug=True, host='0.0.0.0', port=5001)

