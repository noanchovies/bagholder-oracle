# seed_db.py
import pandas as pd
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import sys

# Import the Holding model and Base from app.py
try:
    # Assumes seed_db.py is in the same directory as app.py
    from app import Holding, Base, DATABASE_URL # Import necessary components from app
except ImportError as e:
    print(f"Error importing from app.py: {e}", file=sys.stderr)
    print("Make sure seed_db.py is in the same directory as app.py.", file=sys.stderr)
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

# --- Configuration ---
PORTFOLIO_CSV = 'portfolio.csv' # The local CSV file to read from

def seed_database():
    """Reads the portfolio CSV and inserts data into the database."""

    if not DATABASE_URL:
        logging.error("DATABASE_URL environment variable not set. Cannot connect to database.")
        return

    if not os.path.exists(PORTFOLIO_CSV):
        logging.error(f"Error: Portfolio file '{PORTFOLIO_CSV}' not found in the current directory. Cannot seed database.")
        return

    engine = None
    Session = None
    try:
        # Connect Timeout added
        engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 10})
        Session = sessionmaker(bind=engine)
        logging.info("Database engine created for seeding.")

        # Create tables if they don't exist
        logging.info("Ensuring database tables exist...")
        Base.metadata.create_all(bind=engine)
        logging.info("Tables checked/created.")

    except SQLAlchemyError as e:
        logging.error(f"Error setting up database connection or creating tables: {e}", exc_info=True)
        return # Cannot proceed without engine/tables

    session = Session()
    try:
        logging.info(f"Reading data from local '{PORTFOLIO_CSV}'...")
        portfolio_df = pd.read_csv(PORTFOLIO_CSV)

        # Validation
        required_columns = ['Ticker', 'Quantity', 'CostBasis']
        if not all(col in portfolio_df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in portfolio_df.columns]
            logging.error(f"CSV must contain required columns. Missing: {missing}")
            session.close()
            return

        # Convert types and validate
        portfolio_df['Ticker'] = portfolio_df['Ticker'].astype(str).str.strip()
        portfolio_df['Quantity'] = pd.to_numeric(portfolio_df['Quantity'], errors='coerce')
        # Ensure CostBasis is treated as float/numeric (handles integers too)
        portfolio_df['CostBasis'] = pd.to_numeric(portfolio_df['CostBasis'], errors='coerce')

        # Drop rows with invalid numeric data or zero quantity
        portfolio_df.dropna(subset=['Quantity', 'CostBasis'], inplace=True)
        portfolio_df = portfolio_df[portfolio_df['Quantity'] > 0]

        logging.info(f"Found {len(portfolio_df)} valid rows in CSV to potentially insert.")

        inserted_count = 0
        skipped_count = 0
        for index, row in portfolio_df.iterrows():
            ticker = row['Ticker']
            quantity = row['Quantity']
            cost_basis = row['CostBasis'] # This is the total cost basis

            # Check if ticker already exists
            exists = session.query(Holding).filter(Holding.ticker == ticker).first()
            if exists:
                logging.warning(f"Ticker '{ticker}' already exists in the database. Skipping insertion.")
                skipped_count += 1
                continue

            # Create new Holding object
            holding = Holding(
                ticker=ticker,
                quantity=float(quantity),
                cost_basis=float(cost_basis) # Store the total cost basis
            )
            session.add(holding)
            inserted_count += 1
            logging.info(f"Prepared ticker '{ticker}' for insertion (Qty: {quantity}, CostBasis: {cost_basis}).")

        if inserted_count > 0:
             logging.info(f"Attempting to commit {inserted_count} new holdings...")
             session.commit()
             logging.info("Successfully committed new holdings to the database.")
        else:
             logging.info("No new holdings to insert.")

        if skipped_count > 0:
             logging.info(f"Skipped {skipped_count} holdings that already existed.")

    except IntegrityError as e:
         logging.error(f"Database integrity error (likely duplicate ticker): {e}", exc_info=True)
         session.rollback() # Rollback the transaction
    except SQLAlchemyError as e:
        logging.error(f"Database error during seeding: {e}", exc_info=True)
        session.rollback() # Rollback the transaction
    except FileNotFoundError:
         logging.error(f"Error: Portfolio file '{PORTFOLIO_CSV}' not found during read attempt.")
    except ValueError as ve:
         logging.error(f"Data validation error reading '{PORTFOLIO_CSV}': {ve}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during seeding: {e}", exc_info=True)
        if session.is_active:
             session.rollback()
    finally:
        logging.info("Closing database session used for seeding.")
        session.close()

if __name__ == '__main__':
    print("\n--- Starting Database Seeding ---")
    # Ensure output is visible immediately
    sys.stdout.flush()
    seed_database()
    print("--- Database Seeding Finished ---\n")
    sys.stdout.flush()
