import yfinance as yf
import pandas as pd
import numpy as np
import argparse
import os
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
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        enterprise_value = info.get('enterpriseValue')
        market_cap = info.get('marketCap')

        # --- Earnings Date Logic (from secscrape.py) ---
        next_earnings_date = "Not Available"
        today = date.today()
        calendar = stock.calendar
        earnings_dates_raw = []
        if isinstance(calendar, dict) and 'Earnings Date' in calendar:
            earnings_dates_raw = calendar['Earnings Date']
        elif isinstance(calendar, pd.DataFrame) and 'Earnings Date' in calendar.columns:
            earnings_dates_raw = calendar['Earnings Date'].dropna().tolist()

        if earnings_dates_raw:
            future_dates = [d for d in earnings_dates_raw if isinstance(d, date) and d > today]
            if future_dates:
                next_earnings_date = min(future_dates).strftime('%Y-%m-%d')

        # --- Dividend Date Logic (from secscrape.py) ---
        next_dividend_date = "Not Available"
        if isinstance(calendar, dict):
            ex_div_val = calendar.get('Ex-Dividend Date')
            if ex_div_val and isinstance(ex_div_val, date) and ex_div_val > today:
                next_dividend_date = ex_div_val.strftime('%Y-%m-%d')
        elif isinstance(calendar, pd.DataFrame):
            if 'Ex-Dividend Date' in calendar.columns and not calendar['Ex-Dividend Date'].dropna().empty:
                ex_div_val = pd.to_datetime(calendar['Ex-Dividend Date'].dropna().iloc[0]).date()
                if ex_div_val > today:
                    next_dividend_date = ex_div_val.strftime('%Y-%m-%d')

        return enterprise_value, market_cap, next_earnings_date, next_dividend_date
    except Exception as e:
        print(f"Could not retrieve data for {ticker}: {e}")
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
        
        # Initialize new columns with NaN
        df['Enterprise Value'] = None
        df['Market Cap'] = None
        df['Next Earnings Date'] = None
        df['Next Dividend Date'] = None
        df['MCap/EV (%)'] = None

        process_mask = ~((df['SectorName'] == 'Currency') | (df['IndustryName'] == 'Exchange Traded Fund'))

        for index, row in df[process_mask].iterrows():
            symbol = row['Symbol']
            print(f"Scraping {symbol}...")
            enterprise_value, market_cap, next_earnings_date, next_dividend_date = get_financial_data(symbol)
            
            df.loc[index, 'Enterprise Value'] = enterprise_value
            df.loc[index, 'Market Cap'] = market_cap
            df.loc[index, 'Next Earnings Date'] = next_earnings_date
            df.loc[index, 'Next Dividend Date'] = next_dividend_date
            
            if enterprise_value is not None and market_cap is not None and enterprise_value != 0:
                df.loc[index, 'MCap/EV (%)'] = (market_cap / enterprise_value) * 100
            else:
                df.loc[index, 'MCap/EV (%)'] = np.nan

        print("\nScraping complete. Results:")
        print(df)
        output_filename = f"{os.path.splitext(csv_path)[0]}-EV.csv"
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