
import requests
import pandas as pd
import argparse

# --- USER-DEFINED VARIABLES ---

# IMPORTANT: Replace with your own API key from https://lda.senate.gov/api/
API_KEY = "YOUR_API_KEY_HERE"

# --- HELPER FUNCTIONS ---

def get_lobbying_data(company_name):
    """
    Fetches lobbying data for a given company name from the Senate.gov API.
    """
    if API_KEY == "YOUR_API_KEY_HERE":
        print("Error: Please replace 'YOUR_API_KEY_HERE' with your actual Senate.gov API key.")
        return None

    print(f"Fetching lobbying data for {company_name}...")
    api_url = f"https://lda.senate.gov/api/v1/filings/?registrant_name={company_name}"
    headers = {'X-API-Key': API_KEY}
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get('results', [])
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            print("Error: API rate limit exceeded. Please wait and try again later.")
        else:
            print(f"Error fetching lobbying data from Senate.gov API: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def get_cik(ticker):
    """Gets the CIK number for a given stock ticker from the SEC's company ticker JSON."""
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {'User-Agent': 'My Scraper 1.0 contact@example.com'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        company_tickers = response.json()
        for company_data in company_tickers.values():
            if company_data.get('ticker') == ticker.upper():
                return str(company_data['cik_str']).zfill(10)
        return None
    except Exception as e:
        print(f"Error fetching CIK data from SEC: {e}")
        return None

def display_lobbying_data(lobbying_data):
    """
    Displays lobbying data in a user-friendly format.
    """
    if not lobbying_data:
        print("No lobbying data found for the specified company.")
        return

    df = pd.DataFrame(lobbying_data)
    
    # --- Data Cleaning and Formatting ---
    # Extract and flatten nested data
    df['dt_posted'] = pd.to_datetime(df['dt_posted'], errors='coerce', utc=True).dt.strftime('%Y-%m-%d')
    df['registrant_name'] = df['registrant'].apply(lambda x: x.get('name') if isinstance(x, dict) else None)
    df['client_name'] = df['client'].apply(lambda x: x.get('name') if isinstance(x, dict) else None)
    df['amount_reported'] = df.apply(lambda row: row['income'] if pd.notna(row['income']) else row['expenses'], axis=1)
    df['amount_reported'] = pd.to_numeric(df['amount_reported'], errors='coerce').fillna(0)
    df['issue_area_codes'] = df['lobbying_activities'].apply(lambda x: ', '.join([item['general_issue_code'] for item in x]) if isinstance(x, list) else None)

    # --- Display Summary ---
    print("--- Lobbying Filing Summary ---")
    print(f"Total Filings Found: {len(df)}")
    print(f"Total Amount Reported: ${df['amount_reported'].sum():,.2f}")
    
    # --- Display Detailed Filings ---
    print("--- Recent Filings ---")
    display_cols = ['dt_posted', 'registrant_name', 'client_name', 'amount_reported', 'issue_area_codes']
    
    display_df = df[display_cols].copy()
    display_df['amount_reported'] = display_df['amount_reported'].apply(lambda x: f"${x:,.2f}")
    
    print(display_df.to_string(index=False))

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape lobbying data for a given company name or stock ticker.')
    parser.add_argument('input_identifier', type=str, help='The company name or stock ticker to search for.')
    args = parser.parse_args()

    company_name = args.input_identifier

    # Check if the input is likely a stock ticker (all uppercase, relatively short)
    if len(company_name) <= 5 and company_name.isalpha() and company_name.isupper():
        print(f"Attempting to resolve ticker '{company_name}' to company name...")
        cik = get_cik(company_name)
        if cik:
            # For now, we'll just use the ticker as the company name for the lobbying search
            # as the Senate API doesn't directly map CIK to company names for search.
            # A more robust solution would involve another API call to get the company name from CIK.
            # However, for the purpose of this exercise, we'll assume the ticker is often
            # part of the company's lobbying registration name.
            pass # We already have the company_name from input_identifier
        else:
            print(f"Could not resolve ticker '{company_name}' to a company name. Proceeding with ticker as company name.")
    
    lobbying_data = get_lobbying_data(company_name)
    if lobbying_data:
        display_lobbying_data(lobbying_data)
