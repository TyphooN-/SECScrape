import requests
import json
import pandas as pd
from datetime import datetime, timezone, date
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

def format_share_number(num):
    """Formats a number with commas for readability."""
    if pd.isna(num) or not isinstance(num, (int, float)):
        return "N/A"
    return f"{int(num):,}"


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
            val, date_str = get_latest_fact_value(fact)
            if date_str:
                current_date = datetime.strptime(date_str, '%Y-%m-%d')
                if most_recent_debt_date is None or current_date > most_recent_debt_date:
                    most_recent_debt_date = current_date
    if most_recent_debt_date:
        debt_date = most_recent_debt_date.strftime('%Y-%m-%d')
        for tag in debt_tags:
            fact = us_gaap_facts.get(tag)
            if fact:
                val, date_str = get_latest_fact_value(fact)
                if date_str == debt_date:
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

# --- FIXED EARNINGS DATE FUNCTION ---
def get_earnings_dates(ticker):
    """
    Gets the next and previous earnings dates from yfinance.
    This version handles both dictionary and DataFrame calendar objects.
    """
    print(f"[INFO] Fetching earnings dates for {ticker}...")
    next_earnings_date = "Not Available"
    previous_earnings_date = "Not Available"
    today = date.today()

    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar

        # --- Logic for Next Earnings Date ---
        earnings_dates_raw = []
        # Handle dictionary response from yfinance
        if isinstance(calendar, dict) and 'Earnings Date' in calendar:
            earnings_dates_raw = calendar['Earnings Date']
        # Handle DataFrame response
        elif isinstance(calendar, pd.DataFrame) and 'Earnings Date' in calendar.columns:
            earnings_dates_raw = calendar['Earnings Date'].dropna().tolist()

        # Find the soonest future date from the list
        if earnings_dates_raw:
            future_dates = [d for d in earnings_dates_raw if isinstance(d, date) and d > today]
            if future_dates:
                next_earnings_date = min(future_dates).strftime('%Y-%m-%d')

        # --- Logic for Previous Earnings Date ---
        earnings_history = stock.earnings_dates
        if earnings_history is not None and not earnings_history.empty:
            now_utc = datetime.now(timezone.utc)
            past_dates = earnings_history.index[earnings_history.index < now_utc]
            if not past_dates.empty:
                previous_earnings_date = past_dates.max().strftime('%Y-%m-%d')

    except Exception as e:
        print(f"Could not retrieve earnings dates for {ticker} from yfinance: {e}")

    return {"next": next_earnings_date, "previous": previous_earnings_date}

# --- FIXED DIVIDEND DATE FUNCTION ---
def get_dividend_info(ticker):
    """
    Gets the next and last dividend dates for a given ticker.
    This version handles both dictionary and DataFrame calendar objects.
    """
    try:
        stock = yf.Ticker(ticker)
        dividends = stock.dividends
        today = date.today()
        today_utc = pd.Timestamp.now(tz='UTC').normalize()

        if dividends.empty or (today_utc - dividends.index.max()).days > 365:
            return {"is_dividend_stock": False}

        last_payment_date = dividends.index.max().strftime('%Y-%m-%d')
        calendar = stock.calendar
        next_ex_div_date = "Not Available"
        next_payment_date = "Not Available"

        # Handle dictionary response
        if isinstance(calendar, dict):
            ex_div_val = calendar.get('Ex-Dividend Date')
            pay_val = calendar.get('Dividend Date')
            if ex_div_val and isinstance(ex_div_val, date) and ex_div_val > today:
                next_ex_div_date = ex_div_val.strftime('%Y-%m-%d')
            if pay_val and isinstance(pay_val, date) and pay_val > today:
                next_payment_date = pay_val.strftime('%Y-%m-%d')

        # Handle DataFrame response
        elif isinstance(calendar, pd.DataFrame):
            if 'Ex-Dividend Date' in calendar.columns and not calendar['Ex-Dividend Date'].dropna().empty:
                ex_div_val = pd.to_datetime(calendar['Ex-Dividend Date'].dropna().iloc[0]).date()
                if ex_div_val > today:
                    next_ex_div_date = ex_div_val.strftime('%Y-%m-%d')
            if 'Dividend Date' in calendar.columns and not calendar['Dividend Date'].dropna().empty:
                pay_val = pd.to_datetime(calendar['Dividend Date'].dropna().iloc[0]).date()
                if pay_val > today:
                    next_payment_date = pay_val.strftime('%Y-%m-%d')

        return {
            "is_dividend_stock": True,
            "last_payment_date": last_payment_date,
            "next_ex_dividend_date": next_ex_div_date,
            "next_payment_date": next_payment_date
        }
    except Exception as e:
        print(f"[ERROR] Could not retrieve dividend info for {ticker}: {e}")
        return {"is_dividend_stock": False}

# --- FUNCTION FOR INSTITUTIONAL HOLDERS ---
def display_institutional_holders(ticker):
    """Displays all institutional holders for a given ticker."""
    print("\n" + "="*80)
    print(f"Institutional Holders for: {ticker.upper()}")
    print("="*80)
    try:
        stock = yf.Ticker(ticker)
        holders = stock.institutional_holders

        if holders is None or holders.empty:
            print(f"No institutional holder data available for {ticker.upper()}.")
            return

        # CHANGED: Use the entire 'holders' DataFrame instead of the head
        holders_df = holders.copy()

        # --- Robust Formatting ---
        if 'Shares' in holders_df.columns:
            holders_df['Shares'] = holders_df['Shares'].apply(format_share_number)

        if '% Out' in holders_df.columns:
            holders_df['% Out'] = holders_df['% Out'].apply(lambda x: f"{x:.2%}")
        elif 'pctHeld' in holders_df.columns:
            holders_df['pctHeld'] = holders_df['pctHeld'].apply(lambda x: f"{x:.2%}")
            holders_df.rename(columns={'pctHeld': '% Out'}, inplace=True)

        if 'pctChange' in holders_df.columns:
            holders_df['pctChange'] = holders_df['pctChange'].apply(lambda x: f"{x:+.2%}")

        if 'Date Reported' in holders_df.columns:
            holders_df['Date Reported'] = pd.to_datetime(holders_df['Date Reported']).dt.strftime('%Y-%m-%d')

        if 'Value' in holders_df.columns:
             holders_df = holders_df.drop(columns=['Value'])

        print(holders_df.to_string(index=False))

    except Exception as e:
        print(f"\nAn unexpected error occurred while retrieving institutional holders for {ticker}: {e}")


# --- DISPLAY FUNCTION FOR QUARTERLY DATA (Uses the fixed functions) ---
def display_quarterly_data(ticker):
    """Displays earnings dates, dividend info, and quarterly data."""
    print("\n" + "="*80)
    print(f"Quarterly Report & Key Dates for: {ticker.upper()}")
    print("="*80)

    # --- EARNINGS DATES ---
    earnings_dates = get_earnings_dates(ticker)
    print(f"Next Earnings Date:           {earnings_dates['next']}")
    print(f"Previous Earnings Date:       {earnings_dates['previous']}")

    # --- DIVIDEND DATES ---
    dividend_info = get_dividend_info(ticker)
    if dividend_info.get("is_dividend_stock"):
        print(f"Next Dividend Payment Date:   {dividend_info.get('next_payment_date', 'N/A')}")
        print(f"Next Ex-Dividend Date:        {dividend_info.get('next_ex_dividend_date', 'N/A')}")
        print(f"Last Dividend Payment Date:   {dividend_info.get('last_payment_date', 'N/A')}")
    else:
        print(f"Dividend Status:              {ticker.upper()} does not pay a dividend.")

    # --- FINANCIALS ---
    try:
        stock = yf.Ticker(ticker)
        q_financials = stock.quarterly_financials
        q_cashflow = stock.quarterly_cashflow
        if not isinstance(q_financials, pd.DataFrame) or q_financials.empty:
            print("\nQuarterly financial data not available.")
            return

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

        quarterly_df = pd.DataFrame(metrics).transpose()
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

        yearly_df = pd.DataFrame(metrics).transpose()
        yearly_df.index.name = "Metric"
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
        # --- Filings Report ---
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
            print(df.to_string(columns=['Ticker', 'Filing Type', 'Filing Date', 'Description', 'Link'], index=False))

        # --- Enterprise Value Report ---
        print("\n" + "="*80)
        print("Enterprise Value Report")
        print("Note: Market Cap is from yfinance. Other financial data is from recent SEC filings.")
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
                    ev_df[col] = ev_df[col].apply(lambda x: format_large_number(x))
            report_cols = ["Ticker", "Enterprise Value", "Market Cap", "Total Debt", "Cash & Equivalents", "Market Cap Date", "Debt Date", "Cash Date"]
            final_cols = [c for c in report_cols if c in ev_df.columns]
            print(ev_df[final_cols].to_string(index=False))

        # --- Individual Ticker Reports ---
        for ticker in tickers:
            display_quarterly_data(ticker)
            display_yearly_data(ticker)
            # --- ADDED CALL TO THE NEW FUNCTION ---
            display_institutional_holders(ticker)
