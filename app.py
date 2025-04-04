# app.py
import pandas as pd
import yfinance as yf
from flask import Flask, render_template, request, g
import os
import logging
import time
from sqlalchemy import create_engine, Column, Integer, String, Float, MetaData
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session
from sqlalchemy.exc import SQLAlchemyError
import sys

# --- Initial Debug Print ---
print("--- app.py starting execution ---", flush=True)

# --- Configuration ---
# Database URL comes from environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')
# --- Debug Print for DATABASE_URL ---
print(f"--- DATABASE_URL read from environment: {DATABASE_URL}", flush=True)

if not DATABASE_URL:
    logging.error("FATAL: DATABASE_URL environment variable not set.")
    # sys.exit("Database URL is required.") # Keep this commented for now

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

# --- Database Setup (SQLAlchemy) ---
engine = None
SessionLocal = None
Base = declarative_base()

print(f"--- Attempting to create engine with URL: {DATABASE_URL}", flush=True)
try:
    if DATABASE_URL:
        engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 10})
        SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
        Base.metadata.bind = engine
        logging.info("Database engine created successfully.")
    else:
         logging.warning("Database URL not provided, database features disabled.")

except SQLAlchemyError as e:
    logging.error(f"Error creating database engine or connecting: {e}", exc_info=True)
    engine = None
    SessionLocal = None
# --- Debug Print after Engine Attempt ---
print("--- Engine creation attempted (check logs for success/error) ---", flush=True)


# --- Database Model ---
class Holding(Base):
    __tablename__ = 'holdings' # Table name

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, index=True, nullable=False)
    quantity = Column(Float, nullable=False) # Use Float for quantity flexibility
    cost_basis = Column(Float, nullable=False) # Total cost basis (integer from CSV stored as float)

    def __repr__(self):
        return f"<Holding(ticker='{self.ticker}', quantity={self.quantity}, cost_basis={self.cost_basis})>"

# --- Flask App Initialization ---
app = Flask(__name__)
print("--- Flask app object created ---", flush=True) # Added another print

# --- Request Teardown for DB Session ---
@app.teardown_appcontext
def remove_session(*args, **kwargs):
    """Closes the database session after each request."""
    if SessionLocal:
        SessionLocal.remove()

# --- Helper Functions ---
def get_db():
    """Provides a database session per request."""
    if not SessionLocal:
        logging.error("Database session factory not initialized.")
        return None
    return SessionLocal()

def load_portfolio_from_db():
    """Loads portfolio data from the PostgreSQL database."""
    db = get_db()
    if not db: return []

    try:
        holdings = db.query(Holding).order_by(Holding.ticker).all()
        logging.info(f"Successfully loaded {len(holdings)} holdings from database.")
        return holdings
    except SQLAlchemyError as e:
        logging.error(f"Error loading portfolio from database: {e}", exc_info=True)
        db.rollback()
        return []

def get_stock_data(tickers):
    """Fetches current stock data using yfinance."""
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
                    # else: logging.warning(f"Price data issue for {ticker} in multi-index.") # Reduce log noise
                elif ticker in data.columns and 'Close' in data.columns and not data['Close'].empty:
                     current_price = data['Close'].iloc[-1]
                     price_data_available = True
                # else: logging.warning(f"Could not find valid price data for {ticker} in download results.") # Reduce log noise

                if price_data_available and current_price is not None and not pd.isna(current_price):
                    stock_data[ticker] = {'current_price': current_price, 'currency': currency, 'short_name': short_name}
                    # logging.info(f"Processed {ticker}: Price={current_price}, Currency={currency}") # Reduce log noise
                else:
                    # logging.warning(f"Could not determine valid price for {ticker} from download data.") # Reduce log noise
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
    """Main route to display the portfolio from database with gain/loss."""
    print("--- Request received for / route ---", flush=True) # Added print
    portfolio_details = []
    error_message = None
    total_portfolio_value = 0.0
    total_portfolio_cost_basis = 0.0
    total_portfolio_gain_loss = 0.0

    if not engine or not SessionLocal:
        error_message = "Database connection not configured or failed. Check logs and DATABASE_URL environment variable."
        logging.error(error_message) # Log the error too
        holdings = []
    else:
        holdings = load_portfolio_from_db()
        if not holdings and not error_message:
             error_message = "Portfolio database table is empty. Consider seeding initial data (see documentation/seed script)."

    if holdings:
        tickers = [h.ticker for h in holdings]
        logging.info(f"Tickers loaded from DB: {tickers}")
        stock_data = get_stock_data(tickers)

        for holding in holdings:
            ticker = holding.ticker
            quantity = holding.quantity
            cost_basis = holding.cost_basis

            data = stock_data.get(ticker)
            current_price = 0
            current_value = 0
            avg_purchase_price = 0
            gain_loss = 0
            gain_loss_percent = 0
            currency = 'N/A'
            short_name = ticker

            try:
                quantity = float(quantity)
                cost_basis = float(cost_basis)

                if quantity != 0: avg_purchase_price = cost_basis / quantity
                else: avg_purchase_price = 0

                total_portfolio_cost_basis += cost_basis

                if data and data.get('current_price') is not None and data['current_price'] > 0:
                    current_price = float(data['current_price'])
                    current_value = quantity * current_price
                    gain_loss = current_value - cost_basis
                    if cost_basis != 0: gain_loss_percent = (gain_loss / cost_basis) * 100

                    currency = data.get('currency', 'N/A')
                    short_name = data.get('short_name', ticker)
                    total_portfolio_value += current_value
                    total_portfolio_gain_loss += gain_loss
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

    primary_currency = 'USD'
    if portfolio_details:
        valid_currencies = [p['currency'] for p in portfolio_details if p['currency'] != 'N/A' and p.get('current_value', 0) > 0]
        if valid_currencies:
            try: primary_currency = max(set(valid_currencies), key=valid_currencies.count)
            except ValueError: primary_currency = 'USD'
        elif any(p['currency'] != 'N/A' for p in portfolio_details):
             primary_currency = next((p['currency'] for p in portfolio_details if p['currency'] != 'N/A'), 'USD')

    return render_template('index.html',
                           portfolio=portfolio_details, total_value=total_portfolio_value,
                           total_cost_basis=total_portfolio_cost_basis, total_gain_loss=total_portfolio_gain_loss,
                           primary_currency=primary_currency, error_message=error_message,
                           portfolio_csv_name=None)

# --- Main Execution (for local testing) ---
if __name__ == '__main__':
    # This block does NOT run when using Gunicorn in Docker
    logging.info("Starting Flask development server (for local testing only)...")
    # ... (rest of __main__ block remains the same) ...
    if not DATABASE_URL:
         print("\nWARNING: DATABASE_URL not set. Database features will likely fail.", file=sys.stderr)
         print("For local testing, set it like: export DATABASE_URL='postgresql://user:pass@host:port/db'\n", file=sys.stderr)
    if engine:
        try:
             logging.info("Creating database tables if they don't exist (needed for local run)...")
             Base.metadata.create_all(bind=engine)
             logging.info("Tables checked/created.")
        except SQLAlchemyError as e:
             logging.error(f"Error creating tables during local startup: {e}", exc_info=True)

    app.run(debug=False, host='0.0.0.0', port=5001)

