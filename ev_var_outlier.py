import pandas as pd
import numpy as np
import re
import argparse
import sys # Import sys to redirect stdout
import os # Import os for path manipulation

class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

MINIMUM_GROUP_SIZE = 5
STOCKS_TOP = 50 # User-defined variable for top/bottom N display for Stocks
CFD_TOP = 40    # User-defined variable for top/bottom N display for CFDs
FUTURES_TOP = 5 # User-defined variable for top/bottom N display for Futures
TOP_N_DISPLAY = 20 # User-defined variable for top/bottom N display (will be set dynamically)

def get_outlier_note(row, mcap_bounds, var_bounds, small_industries_list):
    industry = row['IndustryName']
    sector = row['SectorName']
    mcap_ratio = row['MCap/EV (%)']
    var_ratio = row['VaR_to_Ask_Ratio']

    group_name = industry
    if industry in small_industries_list:
        group_name = f"AGGREGATED {sector.upper()} INDUSTRIES"
        if sector == 'Undefined':
            group_name = "AGGREGATED MISCELLANEOUS"

    mcap_note = ''
    if group_name in mcap_bounds:
        bounds = mcap_bounds[group_name]
        if mcap_ratio < bounds['lower']:
            mcap_note = 'MCap/EV (LOW)'
        elif mcap_ratio > bounds['upper']:
            mcap_note = 'MCap/EV (HIGH)'

    var_note = ''
    if group_name in var_bounds:
        bounds = var_bounds[group_name]
        if var_ratio < bounds['lower']:
            var_note = 'VaR (LOW)'
        elif var_ratio > bounds['upper']:
            var_note = 'VaR (HIGH)'

    if mcap_note and var_note:
        return f"Dual Outlier: {mcap_note}, {var_note}"
    elif mcap_note:
        return f"MCap/EV Outlier: {mcap_note}"
    return ''

def analyze_group(group_name, group_df, mcap_bounds, var_bounds):
    if len(group_df) < MINIMUM_GROUP_SIZE:
        return

    for ratio_col, bounds_dict in [('MCap/EV (%)', mcap_bounds), ('VaR_to_Ask_Ratio', var_bounds)]:
        Q1 = group_df[ratio_col].quantile(0.25)
        Q3 = group_df[ratio_col].quantile(0.75)
        IQR = Q3 - Q1
        if IQR > 0:
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            bounds_dict[group_name] = {'lower': lower_bound, 'upper': upper_bound}

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
    column_widths['AskPrice'] = max(column_widths.get('AskPrice', 0), 10)
    column_widths['Spread %'] = max(column_widths.get('Spread %', 0), 10)
    column_widths['VaR_to_Ask_Ratio'] = max(column_widths.get('VaR_to_Ask_Ratio', 0), 15)
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


def print_outlier_table(title, dataframe):
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

def find_dual_outliers(filename):
    try:
        global TOP_N_DISPLAY # Added this line to allow modification of TOP_N_DISPLAY

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

        # Ensure numeric types for relevant columns, coercing errors to NaN
        numeric_cols = ['MCap/EV (%)', 'AskPrice', 'BidPrice', 'VaR_to_Ask_Ratio', 'TradeMode']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate Spread %
        if 'BidPrice' in df.columns and 'AskPrice' in df.columns:
            df['Spread %'] = ((df['AskPrice'] - df['BidPrice']) / df['AskPrice']) * 100
        else:
            print("Warning: BidPrice or AskPrice not found. Cannot calculate Spread %.")
            df['Spread %'] = np.nan

        # Handle inf/-inf values by replacing them with NaN
        df = df.replace([np.inf, -np.inf], np.nan)

        # Drop rows where MCap/EV (%) or VaR_to_Ask_Ratio are NaN, as these are critical for analysis
        df = df.dropna(subset=['MCap/EV (%)', 'VaR_to_Ask_Ratio'])

        # Identify unactionable symbols based on TradeMode == 3
        unactionable_symbols_df = df[df['TradeMode'] == 3][['Symbol', 'IndustryName']].copy()
        df = df[df['TradeMode'] != 3] # Exclude unactionable from analysis

        # Initialize close_only_symbols as an empty DataFrame if no unactionable symbols are found
        if unactionable_symbols_df.empty:
            close_only_symbols = pd.DataFrame(columns=['Symbol', 'IndustryName'])
        else:
            close_only_symbols = unactionable_symbols_df

        industry_counts = df['IndustryName'].value_counts()
        large_industries = industry_counts[industry_counts >= MINIMUM_GROUP_SIZE].index.tolist()
        small_industries = industry_counts[industry_counts < MINIMUM_GROUP_SIZE].index.tolist()

        mcap_bounds, var_bounds = {}, {}

        for industry in sorted(large_industries):
            industry_df = df[df['IndustryName'] == industry]
            analyze_group(industry, industry_df, mcap_bounds, var_bounds)

        if small_industries:
            small_industries_df = df[df['IndustryName'].isin(small_industries)]
            sectors = small_industries_df['SectorName'].unique()
            miscellaneous_industries = []
            for sector in sorted(sectors):
                sector_df = small_industries_df[small_industries_df['SectorName'] == sector]
                if len(sector_df) >= MINIMUM_GROUP_SIZE:
                    analyze_group(f"AGGREGATED {sector.upper()} INDUSTRIES", sector_df, mcap_bounds, var_bounds)
                else:
                    miscellaneous_industries.append(sector_df)
            
            if miscellaneous_industries:
                miscellaneous_df = pd.concat(miscellaneous_industries)
                if len(miscellaneous_df) >= MINIMUM_GROUP_SIZE:
                    analyze_group("AGGREGATED MISCELLANEOUS", miscellaneous_df, mcap_bounds, var_bounds)

        df['Note'] = df.apply(get_outlier_note, axis=1, args=(mcap_bounds, var_bounds, small_industries))
        
        # Consolidate Outliers
        dual_outliers = df[df['Note'].str.contains('Dual Outlier')].copy()
        mcap_outliers = df[df['Note'].str.contains('MCap/EV Outlier')].copy()

        # Get the top/bottom N VaR assets from the original df
        bottom_n_var_symbols = df.sort_values(by='VaR_to_Ask_Ratio', ascending=True).head(TOP_N_DISPLAY)['Symbol']
        top_n_var_symbols = df.sort_values(by='VaR_to_Ask_Ratio', ascending=False).head(TOP_N_DISPLAY)['Symbol']
        
        # Filter mcap_outliers to get those also in bottom_n_var_symbols
        mcap_in_bottom_n = mcap_outliers[mcap_outliers['Symbol'].isin(bottom_n_var_symbols)].copy()
        if not mcap_in_bottom_n.empty:
            mcap_in_bottom_n['Note'] = mcap_in_bottom_n['Note'].apply(lambda x: f"{x} in Bottom {TOP_N_DISPLAY} VaR")
        mcap_in_bottom_n = mcap_in_bottom_n[['Symbol', 'IndustryName', 'MCap/EV (%)', 'AskPrice', 'Spread %', 'VaR_to_Ask_Ratio', 'Note']]

        # Filter mcap_outliers to get those also in top_n_var_symbols
        mcap_in_top_n = mcap_outliers[mcap_outliers['Symbol'].isin(top_n_var_symbols)].copy()
        if not mcap_in_top_n.empty:
            mcap_in_top_n['Note'] = mcap_in_top_n['Note'].apply(lambda x: f"{x} in Top {TOP_N_DISPLAY} VaR")
        mcap_in_top_n = mcap_in_top_n[['Symbol', 'IndustryName', 'MCap/EV (%)', 'AskPrice', 'Spread %', 'VaR_to_Ask_Ratio', 'Note']]
        
        actionable_outliers = pd.concat([dual_outliers, mcap_in_bottom_n, mcap_in_top_n]).drop_duplicates(subset=['Symbol']).sort_values(by='MCap/EV (%)', ascending=False)

        print_outlier_table("Actionable Outliers", actionable_outliers)

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
        print_outlier_table(f"Top {TOP_N_DISPLAY} Highest MCap/EV (%) Assets", top_n_highest_mcap_ev)

        bottom_n_lowest_mcap_ev = global_tradable_stocks_with_etfs.sort_values(by='MCap/EV (%)', ascending=True).head(TOP_N_DISPLAY)
        print_outlier_table(f"Bottom {TOP_N_DISPLAY} Lowest MCap/EV (%) Assets", bottom_n_lowest_mcap_ev)

        if not close_only_symbols.empty:
            print(f"\n\n{'='*25} Unactionable (Close-Only) Symbols {'='*25}")
            for _, row in close_only_symbols.iterrows():
                print(f"- {row['Symbol']} ({row['IndustryName']})")

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Find dual outliers for MCap/EV and VaR/Ask Ratio.')
    parser.add_argument('filename', type=str, help='The path to the CSV file to analyze.')
    args = parser.parse_args()
    
    # --- Output Redirection ---
    # Construct the output filename based on the input filename
    base_filename = os.path.splitext(os.path.basename(args.filename))[0]
    output_filename = f"{base_filename}-ev_var_outlier.txt"
    
    original_stdout = sys.stdout
    
    try:
        with open(output_filename, 'w') as f:
            sys.stdout = Tee(f, original_stdout)
            print(f"Analysis results for {args.filename}")
            print(f"Report generated on: {pd.Timestamp.now()}\n")
            
            find_dual_outliers(args.filename)
            
        sys.stdout = original_stdout
        print(f"\nAnalysis complete. Output also saved to '{output_filename}'")

    except Exception as e:
        sys.stdout = original_stdout
        print(f"An error occurred during file redirection: {e}")
