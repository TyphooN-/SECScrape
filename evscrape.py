import yfinance as yf
import pandas as pd
import numpy as np
import argparse
import os

def get_enterprise_value(ticker):
    """
    Retrieves the enterprise value and market cap for a given stock ticker.

    Args:
        ticker (str): The stock ticker symbol.

    Returns:
        tuple: A tuple containing the enterprise value and market cap.
               Returns (None, None) if the ticker is not found or an error occurs.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        enterprise_value = info.get('enterpriseValue')
        market_cap = info.get('marketCap')
        return enterprise_value, market_cap
    except Exception as e:
        print(f"Could not retrieve data for {ticker}: {e}")
        return None, None

def scrape_from_csv(csv_path):
    """
    Reads a CSV file of stock symbols and scrapes their enterprise value and market cap.

    Args:
        csv_path (str): The path to the CSV file.
    """
    try:
        df = pd.read_csv(csv_path, delimiter=';')
        
        # Initialize new columns with NaN to ensure they exist before assignment
        df['Enterprise Value'] = None
        df['Market Cap'] = None
        df['MCap/EV (%)'] = None

        # Filter out rows where SectorName is 'Currency' or IndustryName is 'Exchange Traded Fund'
        # Apply filters after reading to ensure all original columns are preserved for filtered rows as well
        # The scraping loop will only process the relevant rows
        
        # Create a mask for rows to be processed (not Currency and not ETF)
        process_mask = ~((df['SectorName'] == 'Currency') | (df['IndustryName'] == 'Exchange Traded Fund'))

        for index, row in df[process_mask].iterrows():
            symbol = row['Symbol']
            print(f"Scraping {symbol}...")
            enterprise_value, market_cap = get_enterprise_value(symbol)
            
            # Assign scraped values back to the original DataFrame
            df.loc[index, 'Enterprise Value'] = enterprise_value
            df.loc[index, 'Market Cap'] = market_cap
            
            # Calculate MCap/EV (%) for the current row if values are available
            if enterprise_value is not None and market_cap is not None and enterprise_value != 0:
                df.loc[index, 'MCap/EV (%)'] = (market_cap / enterprise_value) * 100
            else:
                df.loc[index, 'MCap/EV (%)'] = np.nan # Assign NaN if calculation is not possible

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
    parser = argparse.ArgumentParser(description='Scrape enterprise value and market cap for stocks in a CSV file.')
    parser.add_argument('csv_file', type=str, help='The path to the input CSV file.')
    args = parser.parse_args()
    
    scrape_from_csv(args.csv_file)
