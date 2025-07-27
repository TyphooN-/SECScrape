
import yfinance as yf
import pandas as pd
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
        # Filter out rows where SectorName is 'Currency'
        df = df[df['SectorName'] != 'Currency']
        df = df[df['IndustryName'] != 'Exchange Traded Fund']
        results = []
        for index, row in df.iterrows():
            symbol = row['Symbol']
            sector = row['SectorName']
            industry = row['IndustryName']
            ask_price = row['AskPrice']
            var_1_lot = row['VaR_1_Lot']
            var_to_ask_ratio = row['VaR_to_Ask_Ratio']
            print(f"Scraping {symbol}...")
            enterprise_value, market_cap = get_enterprise_value(symbol)
            results.append({
                'Symbol': symbol,
                'SectorName': sector,
                'IndustryName': industry,
                'Enterprise Value': enterprise_value,
                'Market Cap': market_cap,
                'Ask Price': ask_price,
                'VaR_1_Lot': var_1_lot,
                'VaR_to_Ask_Ratio': var_to_ask_ratio
            })
        
        results_df = pd.DataFrame(results)
        results_df['MCap/EV (%)'] = (results_df['Market Cap'] / results_df['Enterprise Value']) * 100
        print("\nScraping complete. Results:")
        print(results_df)
        output_filename = f"{os.path.splitext(csv_path)[0]}-EV.csv"
        results_df.to_csv(output_filename, index=False)
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
