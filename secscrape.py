import requests
import json
import pandas as pd
from datetime import datetime, timezone
import yfinance as yf

# --- USER-DEFINED VARIABLES ---

# User-defined variable to limit the number of filings to retrieve
MAX_FILINGS = 100

# --- HELPER FUNCTIONS ---

def format_large_number(num):
    """Formats a large number into a readable string (B, M, K)."""
    if pd.isna(num) or not isinstance(num, (int, float)):
        return "N/A"
    num = float(num)
    if abs(num) >= 1_000_000_000:
        return f"${num / 1_000_000_000:,.2f} B"
    elif abs(num) >= 1_000_000:
        return f"${num / 1_000_000:,.2f} M"
    elif abs(num) >= 1_000:
        return f"${num / 1_000:,.2f} K"
    else:
        return f"${num:,.2f}"

def get_latest_stock_price(ticker):
    """Gets the latest closing stock price for a given ticker using yfinance."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            price_date = hist.index[-1].strftime('%Y-%m-%d')
            return price, price_date
        else:
            info = stock.info
            if 'previousClose' in info and info['previousClose'] is not None:
                price = info['previousClose']
                print(f"NOTE: Using 'previousClose' price for {ticker} as recent history was unavailable.")
                return price, datetime.now().strftime('%Y-%m-%d')
            else:
                print(f"WARNING: Could not retrieve price for {ticker} from yfinance.")
                return None, None
    except Exception as e:
        print(f"An error occurred while fetching stock price for {ticker} with yfinance: {e}")
        return None, None

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

def fetch_filings_for_ticker(ticker, cik):
    """Fetches recent SEC filings for a single stock ticker."""
    print(f"Fetching filings for {ticker.upper()} (CIK: {cik})...")
    api_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    headers = {'User-Agent': 'My Scraper 1.0 contact@example.com'}
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching filings from SEC API for {ticker}: {e}")
        return []

    recent_filings = data.get('filings', {}).get('recent', {})
    if not recent_filings.get('accessionNumber'):
        return []

    filings = []
    for i in range(len(recent_filings['accessionNumber'])):
        filing_type = recent_filings['form'][i]
        filing_date = recent_filings['filingDate'][i]
        description = recent_filings['primaryDocDescription'][i]
        accession_num_stripped = recent_filings['accessionNumber'][i].replace('-', '')
        primary_doc_name = recent_filings['primaryDocument'][i]
        doc_link = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_num_stripped}/{primary_doc_name}"
        filings.append({
            "Ticker": ticker.upper(), "Filing Type": filing_type, "Description": description,
            "Filing Date": filing_date, "Link": doc_link
        })
    return filings

def get_enterprise_value_data(ticker, cik):
    """Fetches financial data and calculates Enterprise Value."""
    api_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    headers = {'User-Agent': 'My Scraper 1.0 contact@example.com'}
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        facts = response.json()
    except Exception as e:
        print(f"Error fetching financial facts for {ticker}: {e}")
        return None

    def get_latest_fact_value(fact_data):
        if not fact_data or 'units' not in fact_data or 'USD' not in fact_data['units']:
            return None, None
        valid_filings = [f for f in fact_data['units']['USD'] if f.get('fy') is not None and f.get('end') is not None]
        if not valid_filings:
            return None, None
        latest_filing = max(valid_filings, key=lambda x: datetime.strptime(x['end'], '%Y-%m-%d'))
        return latest_filing.get('val'), latest_filing.get('end')

    shares, price, market_cap = None, None, None
    try:
        stock = yf.Ticker(ticker)
        shares = stock.info.get('sharesOutstanding')
    except Exception as e:
        print(f"An error occurred while fetching shares outstanding for {ticker} with yfinance: {e}")
    price, price_date = get_latest_stock_price(ticker)
    if shares is not None and price is not None:
        market_cap = shares * price

    us_gaap_facts = facts.get('facts', {}).get('us-gaap', {})
    cash_fact = us_gaap_facts.get('CashAndCashEquivalentsAtCarryingValue')
    cash, cash_date = get_latest_fact_value(cash_fact)

    debt_tags = ['LongTermDebtAndCapitalLeaseObligations', 'DebtAndCapitalLeaseObligationsCurrent', 'LongTermDebt', 'ShortTermBorrowings']
    total_debt, debt_date, latest_debt_values = 0, None, {}
    most_recent_debt_date = None
    for tag in debt_tags:
        fact = us_gaap_facts.get(tag)
        if fact:
            val, date = get_latest_fact_value(fact)
            if date:
                current_date = datetime.strptime(date, '%Y-%m-%d')
                if most_recent_debt_date is None or current_date > most_recent_debt_date:
                    most_recent_debt_date = current_date
    if most_recent_debt_date:
        debt_date = most_recent_debt_date.strftime('%Y-%m-%d')
        for tag in debt_tags:
            fact = us_gaap_facts.get(tag)
            if fact:
                val, date = get_latest_fact_value(fact)
                if date == debt_date:
                    latest_debt_values[tag] = val
        if 'LongTermDebtAndCapitalLeaseObligations' in latest_debt_values or 'DebtAndCapitalLeaseObligationsCurrent' in latest_debt_values:
            total_debt = latest_debt_values.get('LongTermDebtAndCapitalLeaseObligations', 0) + latest_debt_values.get('DebtAndCapitalLeaseObligationsCurrent', 0)
        else:
            total_debt = latest_debt_values.get('LongTermDebt', 0) + latest_debt_values.get('ShortTermBorrowings', 0)

    enterprise_value = None
    if market_cap is not None and cash is not None:
        enterprise_value = market_cap + total_debt - cash

    return {
        "Market Cap": market_cap, "Market Cap Date": price_date,
        "Total Debt": total_debt if total_debt > 0 else 0, "Debt Date": debt_date,
        "Cash & Equivalents": cash, "Cash Date": cash_date,
        "Enterprise Value": enterprise_value
    }

def get_earnings_dates(ticker):
    """
    Gets the next and previous earnings dates from yfinance.
    This function is debugged to correctly handle yfinance data structures.
    """
    print(f"[INFO] Fetching earnings dates for {ticker}...")
    next_earnings_date = "Not Available"
    previous_earnings_date = "Not Available"

    try:
        stock = yf.Ticker(ticker)

        # --- MODIFIED SECTION ---
        # yfinance now returns a DataFrame for earnings_dates.
        # We will fetch it once and then find the next and previous dates from it.
        earnings_history = stock.earnings_dates

        if earnings_history is not None and not earnings_history.empty:
            # The index of the DataFrame contains the earnings dates
            now_utc = datetime.now(timezone.utc)

            # Find future dates
            future_dates = earnings_history.index[earnings_history.index > now_utc]
            if not future_dates.empty:
                # The first date in the sorted future dates is the next one
                next_earnings_date = future_dates.min().strftime('%Y-%m-%d')

            # Find past dates
            past_dates = earnings_history.index[earnings_history.index < now_utc]
            if not past_dates.empty:
                # The last date in the sorted past dates is the most recent previous one
                previous_earnings_date = past_dates.max().strftime('%Y-%m-%d')

    except Exception as e:
        print(f"Could not retrieve earnings dates for {ticker} from yfinance: {e}")

    return {"next": next_earnings_date, "previous": previous_earnings_date}



def display_quarterly_data(ticker):
    """Displays earnings date and quarterly data for the last 5 quarters."""
    print("\n" + "="*80)
    print(f"Quarterly Report & Earnings Date for: {ticker.upper()}")
    print("="*80)

    # Call the new, corrected function for earnings dates
    earnings_dates = get_earnings_dates(ticker)
    print(f"Next Earnings Date: {earnings_dates['next']}")
    print(f"Previous Earnings Date: {earnings_dates['previous']}")


    try:
        stock = yf.Ticker(ticker)
        q_financials = stock.quarterly_financials
        q_cashflow = stock.quarterly_cashflow
        if not isinstance(q_financials, pd.DataFrame) or q_financials.empty:
            print("\nQuarterly financial data not available.")
            return

        # --- MODIFIED TO 5 QUARTERS ---
        q_financials = q_financials.iloc[:, :5]
        if isinstance(q_cashflow, pd.DataFrame) and not q_cashflow.empty:
            q_cashflow = q_cashflow.iloc[:, :5]
        else:
            q_cashflow = pd.DataFrame()

        metrics = {}
        if 'Total Revenue' in q_financials.index:
            metrics['Total Revenue'] = q_financials.loc['Total Revenue']
        if 'Net Income' in q_financials.index:
            metrics['Net Income'] = q_financials.loc['Net Income']
        if 'Free Cash Flow' in q_cashflow.index:
            metrics['Free Cash Flow'] = q_cashflow.loc['Free Cash Flow']

        if not metrics:
            print("\nCould not extract key financial metrics.")
            return

        quarterly_df = pd.DataFrame(metrics)
        quarterly_df = quarterly_df.transpose()
        quarterly_df.index.name = "Metric"
        quarterly_df.columns = [d.strftime('%Y-%m-%d') for d in quarterly_df.columns]
        formatted_df = quarterly_df.map(format_large_number)
        print("\nQuarterly Financial Summary (Last 5 Quarters):")
        print(formatted_df.to_string())

    except Exception as e:
        print(f"\nAn unexpected error occurred while retrieving quarterly data for {ticker}: {e}")

def display_yearly_data(ticker):
    """Displays yearly financial summary for the last 5 years."""
    print("\n" + "="*80)
    print(f"Yearly Financial Summary for: {ticker.upper()}")
    print("="*80)
    
    try:
        stock = yf.Ticker(ticker)
        y_financials = stock.financials
        y_cashflow = stock.cashflow
        
        if not isinstance(y_financials, pd.DataFrame) or y_financials.empty:
            print("\nYearly financial data not available.")
            return

        # --- GET LAST 5 YEARS ---
        y_financials = y_financials.iloc[:, :5]
        if isinstance(y_cashflow, pd.DataFrame) and not y_cashflow.empty:
            y_cashflow = y_cashflow.iloc[:, :5]
        else:
            y_cashflow = pd.DataFrame()
            
        metrics = {}
        if 'Total Revenue' in y_financials.index:
            metrics['Total Revenue'] = y_financials.loc['Total Revenue']
        if 'Net Income' in y_financials.index:
            metrics['Net Income'] = y_financials.loc['Net Income']
        if 'Free Cash Flow' in y_cashflow.index:
            metrics['Free Cash Flow'] = y_cashflow.loc['Free Cash Flow']

        if not metrics:
            print("\nCould not extract key yearly financial metrics.")
            return
            
        yearly_df = pd.DataFrame(metrics)
        yearly_df = yearly_df.transpose()
        yearly_df.index.name = "Metric"
        # Column headers are already years from yfinance
        yearly_df.columns = [str(d.year) for d in yearly_df.columns]
        formatted_df = yearly_df.map(format_large_number)
        
        print("\nYearly Financial Summary (Last 5 Years):")
        print(formatted_df.to_string())

    except Exception as e:
        print(f"\nAn unexpected error occurred while retrieving yearly data for {ticker}: {e}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # To use the script, you'll need to install the required libraries:
    # pip install requests pandas yfinance
    
    input_string = input("Enter stock ticker(s), separated by commas (e.g., CHGG, NVDA, AMD, MSFT): ")
    tickers = [t.strip().upper() for t in input_string.split(',') if t.strip()]
    if not tickers:
        print("No valid tickers entered.")
    else:
        all_filings, ticker_to_cik = [], {}
        for ticker in tickers:
            cik = get_cik(ticker)
            if not cik:
                print(f"Could not find CIK for ticker: {ticker.upper()}. Skipping.")
                continue
            ticker_to_cik[ticker] = cik
            all_filings.extend(fetch_filings_for_ticker(ticker, cik))
        if all_filings:
            df = pd.DataFrame(sorted(all_filings, key=lambda x: x['Filing Date'], reverse=True)[:MAX_FILINGS])
            print(f"\nDisplaying the top {len(df)} most recent filings for: {', '.join(tickers)}")
            print(df.to_string(columns=['Ticker', 'Filing Type', 'Filing Date', 'Description', 'Link']))

        print("\n" + "="*80)
        print("Enterprise Value Report")
        print("Note: Market Cap and Shares Outstanding are sourced from yfinance.")
        print("      Other financial data is from the most recent SEC filings.")
        print("="*80)
        ev_data = []
        for ticker in tickers:
            cik = ticker_to_cik.get(ticker)
            if not cik:
                ev_data.append({"Ticker": ticker, "Market Cap": "CIK not found"})
                continue
            print(f"Fetching financial data for {ticker}...")
            financials = get_enterprise_value_data(ticker, cik)
            row_data = {"Ticker": ticker}
            if financials:
                row_data.update(financials)
            ev_data.append(row_data)
        if ev_data:
            ev_df = pd.DataFrame(ev_data)
            for col in ["Market Cap", "Total Debt", "Cash & Equivalents", "Enterprise Value"]:
                if col in ev_df.columns:
                    ev_df[col] = ev_df[col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) and isinstance(x, (int, float)) else "N/A")
            report_cols = ["Ticker", "Enterprise Value", "Market Cap", "Total Debt", "Cash & Equivalents", "Market Cap Date", "Debt Date", "Cash Date"]
            final_cols = [c for c in report_cols if c in ev_df.columns]
            print(ev_df[final_cols].to_string(index=False))

        for ticker in tickers:
            display_quarterly_data(ticker)
            display_yearly_data(ticker)
