import yfinance
import pandas as pd
import numpy as np
import argparse
import os
import sys
from io import StringIO
from datetime import date

def get_financial_data(ticker):
    """
    Retrieves enterprise value, market cap, next earnings date, and next dividend date for a given stock ticker.

    Args:
        ticker (str): The stock ticker symbol.

    Returns:
        tuple: A tuple containing enterprise value, market cap, next earnings date, and next dividend date.
               Returns (None, None, None, None) if the ticker is not found or an error occurs.
    """
    # Redirect stderr to capture yfinance's direct error prints
    old_stderr = sys.stderr
    sys.stderr = captured_stderr = StringIO()

    try:
        stock = yfinance.Ticker(ticker)
        info = stock.info

        # Restore stderr and get the captured output
        sys.stderr = old_stderr
        error_output = captured_stderr.getvalue()

        # Check for 404 in the captured output or if info is invalid
        if "404" in error_output or (not info or 'symbol' not in info):
            print(f"Could not find data for {ticker}: Not Found (404). Handled.")
            return None, None, None, None

        enterprise_value = info.get('enterpriseValue')
        market_cap = info.get('marketCap')

        try:
            calendar = stock.calendar
        except Exception:
            calendar = {}

        next_earnings_date = "Not Available"
        today = date.today()
        earnings_dates_raw = []
        if isinstance(calendar, dict) and 'Earnings Date' in calendar:
            earnings_dates_raw = calendar.get('Earnings Date', [])
        elif isinstance(calendar, pd.DataFrame) and 'Earnings Date' in calendar.columns:
            earnings_dates_raw = calendar['Earnings Date'].dropna().tolist()

        if earnings_dates_raw:
            future_dates = [d.date() if hasattr(d, 'date') else d for d in earnings_dates_raw]
            future_dates = [d for d in future_dates if isinstance(d, date) and d > today]
            if future_dates:
                next_earnings_date = min(future_dates).strftime('%Y-%m-%d')

        next_dividend_date = "Not Available"
        if isinstance(calendar, dict):
            ex_div_val = calendar.get('Ex-Dividend Date')
            if ex_div_val and isinstance(ex_div_val, pd.Timestamp):
                ex_div_date = ex_div_val.date()
                if ex_div_date > today:
                    next_dividend_date = ex_div_date.strftime('%Y-%m-%d')
        elif isinstance(calendar, pd.DataFrame):
            if 'Ex-Dividend Date' in calendar.columns and not calendar['Ex-Dividend Date'].dropna().empty:
                ex_div_dates = pd.to_datetime(calendar['Ex-Dividend Date'].dropna()).dt.date
                future_dividend_dates = sorted([d for d in ex_div_dates if d > today])
                if future_dividend_dates:
                    next_dividend_date = future_dividend_dates[0].strftime('%Y-%m-%d')

        return enterprise_value, market_cap, next_earnings_date, next_dividend_date

    except Exception as e:
        sys.stderr = old_stderr # Ensure stderr is restored on other errors
        print(f"An unexpected error occurred for {ticker}: {e}")
        return None, None, None, None

def scrape_from_csv(csv_path):
    """
    Reads a CSV file of stock symbols and scrapes their enterprise value, market cap,
    next earnings date, and next dividend date.

    Args:
        csv_path (str): The path to the CSV file.
    """
    try:
        df = pd.read_csv(csv_path, delimiter=';')
        
        for col in ['Enterprise Value', 'Market Cap', 'Next Earnings Date', 'Next Dividend Date', 'MCap/EV (%)']:
            if col not in df.columns:
                df[col] = None

        process_mask = ~((df['SectorName'] == 'Currency') | (df['IndustryName'] == 'Exchange Traded Fund'))

        for index, row in df[process_mask].iterrows():
            if pd.notna(row.get('Enterprise Value')):
                continue

            symbol = row['Symbol']
            symbol_fix = symbol
            
            if isinstance(symbol, str) and len(symbol) > 2 and symbol.endswith(('a', 'b')):
                class_s = symbol[-1].upper()
                base = symbol[:-1]
                symbol_fix = f"{base}-{class_s}"
                print(f"Scraping {symbol} (trying as {symbol_fix})...")
            else:
                 print(f"Scraping {symbol}...")

            enterprise_value, market_cap, next_earnings_date, next_dividend_date = get_financial_data(symbol_fix)
            
            if enterprise_value is None and market_cap is None and symbol_fix != symbol:
                print(f"Could not find data for {symbol_fix}, trying original symbol {symbol}...")
                enterprise_value, market_cap, next_earnings_date, next_dividend_date = get_financial_data(symbol)

            df.loc[index, 'Enterprise Value'] = enterprise_value
            df.loc[index, 'Market Cap'] = market_cap
            df.loc[index, 'Next Earnings Date'] = next_earnings_date
            df.loc[index, 'Next Dividend Date'] = next_dividend_date
            
            if enterprise_value is not None and market_cap is not None and enterprise_value > 0:
                df.loc[index, 'MCap/EV (%)'] = (market_cap / enterprise_value) * 100
            else:
                df.loc[index, 'MCap/EV (%)'] = np.nan

        print("\nScraping complete. Results:")
        display_cols = ['Symbol', 'Enterprise Value', 'Market Cap', 'Next Earnings Date', 'Next Dividend Date', 'MCap/EV (%)']
        print(df[display_cols].tail())

        output_filename = f"{os.path.splitext(csv_path)[0]}.csv"
        if not output_filename.endswith('-EV.csv'):
             base, _ = os.path.splitext(csv_path)
             output_filename = f"{base}-EV.csv"

        df.to_csv(output_filename, index=False, sep=';')
        print(f"\nResults saved to {output_filename}")

    except FileNotFoundError:
        print(f"Error: The file '{csv_path}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape enterprise value, market cap, earnings, and dividend dates for stocks in a CSV file.')
    parser.add_argument('csv_file', type=str, help='The path to the input CSV file.')
    args = parser.parse_args()
    
    scrape_from_csv(args.csv_file)
