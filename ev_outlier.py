import pandas as pd
import numpy as np
import re
import argparse
import sys # Import sys to redirect stdout
import os # Import os for path manipulation

# This constant is used in multiple functions, so it's defined globally.
MINIMUM_GROUP_SIZE = 5
STOCKS_TOP = 50 # User-defined variable for top/bottom N display for Stocks
CFD_TOP = 40    # User-defined variable for top/bottom N display for CFDs
FUTURES_TOP = 5 # User-defined variable for top/bottom N display for Futures
TOP_N_DISPLAY = 20 # User-defined variable for top/bottom N display (will be set dynamically)

def get_outlier_note(row, bounds_dict, small_industries_list):
    """
    Determines the outlier status note for a given stock row.

    Args:
        row (pd.Series): A row from the DataFrame.
        bounds_dict (dict): A dictionary containing the outlier bounds for each industry.
        small_industries_list (list): A list of industries classified as small.

    Returns:
        str: A note indicating the stock's outlier status.
    """
    industry = row['IndustryName']
    sector = row['SectorName'] # Get the sector for the current row
    ratio = row['MCap/EV (%)']

    # Determine which group the stock belongs to for bound checking
    if industry in small_industries_list:
        # If it's a small industry, its group name is its aggregated sector group
        group_name = f"AGGREGATED {sector.upper()} INDUSTRIES"
        if sector == 'Undefined':
            group_name = "AGGREGATED MISCELLANEOUS"

    else:
        # Otherwise, it's its own industry group
        group_name = industry

    # Check if bounds were successfully calculated for this group
    if group_name in bounds_dict:
        bounds = bounds_dict[group_name]
        if ratio < bounds['lower']:
            return '(LOW - Statistically Significant)'
        elif ratio > bounds['upper']:
            return '(HIGH - Statistically Significant)'
    
    # Default note if it's not a statistical outlier within its group
    return '(Within Normal Range)'

def _print_table(title, dataframe, columns_info):
    print(f"\n\n{'='*25} {title} {'='*25}")
    if dataframe.empty:
        print("No outliers found in this category.")
        return

    # Calculate column widths
    column_widths = {}
    for col_df_name, col_header, col_format in columns_info:
        max_len = len(col_header)
        if col_df_name in dataframe.columns:
            if col_format:
                if col_format.endswith('%'):
                    # Handle percentage formatting separately
                    base_format = col_format[:-1] # Remove the %
                    formatted_data = dataframe[col_df_name].apply(lambda x: f"{x:{base_format}}%")
                else:
                    formatted_data = dataframe[col_df_name].apply(lambda x: f"{x:{col_format}}")
                max_len = max(max_len, formatted_data.str.len().max())
            else:
                max_len = max(max_len, dataframe[col_df_name].astype(str).str.len().max())
        column_widths[col_df_name] = max_len

    # Adjust for specific columns that might have fixed width requirements or minimums
    column_widths['Symbol'] = max(column_widths.get('Symbol', 0), 10)
    column_widths['IndustryName'] = max(column_widths.get('IndustryName', 0), 40)
    column_widths['MCap/EV (%)'] = max(column_widths.get('MCap/EV (%)', 0), 15)
    column_widths['Note'] = max(column_widths.get('Note', 0), 4) # Minimum for 'Note'

    # Print header
    header_parts = []
    for col_df_name, col_header, _ in columns_info:
        header_parts.append(f"{col_header:<{column_widths[col_df_name]}}")
    header_line = " | ".join(header_parts)
    print("-" * len(header_line))
    print(header_line)
    print("-" * len(header_line))

    # Print data rows
    for _, row in dataframe.iterrows():
        row_parts = []
        for col_df_name, _, col_format in columns_info:
            value = row[col_df_name]
            formatted_value_str = ""
            if pd.isna(value):
                formatted_value_str = "N/A" # Or an empty string, depending on preference
            elif col_format:
                if col_format.endswith('%'):
                    base_format = col_format[:-1]
                    formatted_value_str = f"{value:{base_format}}%"
                else:
                    formatted_value_str = f"{value:{col_format}}"
            else:
                formatted_value_str = str(value)
            
            row_parts.append(formatted_value_str.ljust(column_widths[col_df_name]))
        print(" | ".join(row_parts))
    print("-" * len(header_line))

def analyze_group(group_name, group_df, bounds_dict=None, small_industries_list=None):
    """
    Performs a statistical VaR outlier analysis on a given group of stocks.
    This function will produce NO output unless at least one
    statistically significant outlier is found.

    Args:
        group_name (str): The name of the industry/group being analyzed.
        group_df (pd.DataFrame): The DataFrame containing the data.
        bounds_dict (dict, optional): A dictionary to store the calculated bounds.
    """
    # Silently exit if the group is too small for meaningful analysis
    if len(group_df) < MINIMUM_GROUP_SIZE:
        return

    # --- Perform calculations silently first ---
    Q1 = group_df['MCap/EV (%)'].quantile(0.25)
    Q3 = group_df['MCap/EV (%)'].quantile(0.75)
    IQR = Q3 - Q1

    # Only proceed if there is a statistical range to measure
    if IQR > 0:
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        # MODIFICATION: Store the calculated bounds in the shared dictionary
        if bounds_dict is not None:
            bounds_dict[group_name] = {'lower': lower_bound, 'upper': upper_bound}

        all_outliers = group_df[
            (group_df['MCap/EV (%)'] < lower_bound) |
            (group_df['MCap/EV (%)'] > upper_bound)
        ].copy()

        # --- Only print a report if outliers were actually found ---
        if not all_outliers.empty:
            print(f"\n{'='*30} Analysis for: {group_name.upper()} {'='*30}")
            
            print(f"Contains {len(group_df)} total instruments.")

            print(f"\n--- MCap/EV (%) Ratio Statistics ---")
            print(f"Q1 (25th percentile): {Q1:.4f}")
            print(f"Q3 (75th percentile): {Q3:.4f}")
            print(f"IQR (Interquartile Range): {IQR:.4f}")
            print(f"Lower Outlier Bound: {lower_bound:.4f}")
            print(f"Upper Outlier Bound: {upper_bound:.4f}")

            print(f"--- Found {len(all_outliers)} Total Statistical MCap/EV (%) Outliers ---")
            
            # Print details of each outlier
            if not all_outliers.empty:
                all_outliers['Note'] = all_outliers.apply(
                    get_outlier_note,
                    axis=1,
                    args=(bounds_dict, small_industries_list)
                )
                columns_info = [
                    ('Symbol', 'Symbol', None),
                    ('IndustryName', 'Industry', None),
                    ('MCap/EV (%)', 'MCap/EV (%)', '.2f%'),
                    ('AskPrice', 'Ask Price', '.2f'),
                    ('Spread %', 'Spread %', '.2f%'),
                    ('VaR_to_Ask_Ratio', 'VaR/Ask Ratio', None),
                    ('Note', 'Note', None)
                ]
                _print_table("Statistical MCap/EV (%) Outliers", all_outliers, columns_info)

def print_mcap_ev_table(title, dataframe, industry_bounds, small_industries):
    if not dataframe.empty:
        dataframe['Note'] = dataframe.apply(get_outlier_note, axis=1, args=(industry_bounds, small_industries))
    columns_info = [
        ('Symbol', 'Symbol', None),
        ('IndustryName', 'Industry', None),
        ('MCap/EV (%)', 'MCap/EV (%)', '.2f%'),
        ('AskPrice', 'Ask Price', '.2f'),
        ('Spread %', 'Spread %', '.2f%'),
        ('VaR_to_Ask_Ratio', 'VaR/Ask Ratio', None),
        ('Note', 'Note', None)
    ]
    _print_table(title, dataframe, columns_info)


def find_mcap_ev_outliers(filename, overwrite=False):
    """
    Main function to load and clean data, then orchestrate a tiered analysis that
    only reports on groups where significant outliers are found.
    """
    try:
        global TOP_N_DISPLAY
        file_type = "Unknown"
        if re.search(r'Stocks', filename, re.IGNORECASE):
            file_type = "Stocks"
            TOP_N_DISPLAY = STOCKS_TOP
        elif re.search(r'CFD', filename, re.IGNORECASE):
            file_type = "CFD"
            TOP_N_DISPLAY = CFD_TOP
        elif re.search(r'Futures', filename, re.IGNORECASE):
            file_type = "Futures"
            TOP_N_DISPLAY = FUTURES_TOP
        
        print(f"Detected file type: {file_type}. Displaying top/bottom {TOP_N_DISPLAY} assets at end.")

        df = pd.read_csv(filename, delimiter=';')
        df.columns = df.columns.str.strip()

        # Check for symbols with invalid values before cleaning
        if 'MCap/EV (%)' in df.columns and 'Symbol' in df.columns:
            # Using .astype(str).str.strip() to safely handle different dtypes and whitespace
            invalid_mask = df['MCap/EV (%)'].astype(str).str.strip() == '-inf'
            for symbol in df.loc[invalid_mask, 'Symbol']:
                print(f"WARNING: {symbol} has an invalid MCap/EV (%) value and will be excluded.")

        df = df[df['MCap/EV (%)'] != -np.inf] # Exclude rows with -inf

        required_columns = ['Symbol', 'SectorName', 'IndustryName', 'MCap/EV (%)', 'TradeMode', 'AskPrice', 'BidPrice', 'VaR_to_Ask_Ratio']
        if not all(col in df.columns for col in required_columns):
            print(f"Warning: Some required columns are missing. Analysis might be incomplete. Missing: {[col for col in required_columns if col not in df.columns]}")
        
        # Ensure AskPrice is treated as numeric, coercing errors to NaN
        if 'AskPrice' in df.columns:
            df['AskPrice'] = pd.to_numeric(df['AskPrice'], errors='coerce')
        if 'BidPrice' in df.columns:
            df['BidPrice'] = pd.to_numeric(df['BidPrice'], errors='coerce')

        # Calculate Spread % if BidPrice and AskPrice are available
        if 'BidPrice' in df.columns and 'AskPrice' in df.columns:
            df['Spread %'] = ((df['AskPrice'] - df['BidPrice']) / df['AskPrice']) * 100
        else:
            print("Warning: BidPrice or AskPrice not found. Cannot calculate Spread %.")
            df['Spread %'] = np.nan # Fill with NaN if calculation is not possible

        if 'VaR_to_Ask_Ratio' in df.columns:
            df['VaR_to_Ask_Ratio'] = pd.to_numeric(df['VaR_to_Ask_Ratio'], errors='coerce')

        # Convert TradeMode to numeric, coercing errors to NaN
        df['TradeMode'] = pd.to_numeric(df['TradeMode'], errors='coerce')
        
        # Identify unactionable symbols based on TradeMode == 3
        unactionable_symbols_df = df[df['TradeMode'] == 3][['Symbol', 'IndustryName']].copy()
        
        # Filter out unactionable symbols from the main DataFrame for analysis
        df = df[df['TradeMode'] != 3]

        industry_counts = df['IndustryName'].value_counts()
        
        large_industries = industry_counts[industry_counts >= MINIMUM_GROUP_SIZE].index.tolist()
        small_industries = industry_counts[industry_counts < MINIMUM_GROUP_SIZE].index.tolist()

        industry_bounds = {}

        for industry in sorted(large_industries):
            industry_df = df[df['IndustryName'] == industry].copy()
            analyze_group(industry, industry_df, bounds_dict=industry_bounds, small_industries_list=small_industries)

        if small_industries:
            small_industries_df = df[df['IndustryName'].isin(small_industries)].copy()
            sectors_with_small_industries = small_industries_df['SectorName'].unique().tolist()
            
            miscellaneous_industries = []
            for sector in sorted(sectors_with_small_industries):
                sector_df = small_industries_df[small_industries_df['SectorName'] == sector]
                if len(sector_df) >= MINIMUM_GROUP_SIZE:
                    aggregated_group_name = f"AGGREGATED {sector.upper()} INDUSTRIES"
                    analyze_group(aggregated_group_name, sector_df, bounds_dict=industry_bounds, small_industries_list=small_industries)
                else:
                    miscellaneous_industries.append(sector_df)
            
            if miscellaneous_industries:
                miscellaneous_df = pd.concat(miscellaneous_industries)
                if len(miscellaneous_df) >= MINIMUM_GROUP_SIZE:
                    analyze_group("AGGREGATED MISCELLANEOUS", miscellaneous_df, bounds_dict=industry_bounds, small_industries_list=small_industries)
                else:
                    print(f"\nNOTE: A miscellaneous group of {len(miscellaneous_df)} instruments was formed but was too small to analyze (minimum size: {MINIMUM_GROUP_SIZE}).")

        global_tradable_stocks_with_etfs = df.copy()

        global_Q1 = global_tradable_stocks_with_etfs['MCap/EV (%)'].quantile(0.25)
        global_Q3 = global_tradable_stocks_with_etfs['MCap/EV (%)'].quantile(0.75)
        global_IQR = global_Q3 - global_Q1
        global_lower_bound = global_Q1 - 1.5 * global_IQR
        global_upper_bound = global_Q3 + 1.5 * global_IQR

        print(f"\n{'='*25} Global MCap/EV (%) Ratio Statistics {'='*25}")
        print(f"Q1 (25th percentile): {global_Q1:.4f}")
        print(f"Q3 (75th percentile): {global_Q3:.4f}")
        print(f"IQR (Interquartile Range): {global_IQR:.4f}")
        print(f"Lower Outlier Bound: {global_lower_bound:.4f}")
        print(f"Upper Outlier Bound: {global_upper_bound:.4f}")

        top_n_highest_mcap_ev = global_tradable_stocks_with_etfs.sort_values(by='MCap/EV (%)', ascending=False).head(TOP_N_DISPLAY)
        print_mcap_ev_table(f"Top {TOP_N_DISPLAY} Highest MCap/EV (%) Assets", top_n_highest_mcap_ev, industry_bounds, small_industries)

        bottom_n_lowest_mcap_ev = global_tradable_stocks_with_etfs.sort_values(by='MCap/EV (%)', ascending=True).head(TOP_N_DISPLAY)
        print_mcap_ev_table(f"Bottom {TOP_N_DISPLAY} Lowest MCap/EV (%) Assets", bottom_n_lowest_mcap_ev, industry_bounds, small_industries)

        if not unactionable_symbols_df.empty:
            print(f"\n{'='*25} Unactionable (Close-Only) Symbols {'='*25}")
            for index, row in unactionable_symbols_df.iterrows():
                print(f"- {row['Symbol']} ({row['IndustryName']})")

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Find MCap/EV outliers in a given CSV file.')
    parser.add_argument('filename', type=str, help='The path to the CSV file to analyze.')
    
    args = parser.parse_args()
    
    # --- Output Redirection ---
    output_filename = "ev_outlier.txt"
    
    # Save the original stdout so we can restore it later
    original_stdout = sys.stdout
    
    try:
        # Open the output file in write mode
        with open(output_filename, 'w') as f:
            # Redirect stdout to the file
            sys.stdout = f
            print(f"Analysis results for {args.filename}")
            print(f"Report generated on: {pd.Timestamp.now()}\n")
            
            # Run the analysis function
            find_mcap_ev_outliers(args.filename)
            
        # Let the user know where the output was saved
        # (This message will go to the original stdout)
        sys.stdout = original_stdout
        print(f"Analysis complete. Output saved to '{output_filename}'")

    except Exception as e:
        # If anything goes wrong, make sure to restore stdout
        sys.stdout = original_stdout
        print(f"An error occurred during file redirection: {e}")
