import pandas as pd
import numpy as np
import re
import argparse

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
                print("-" * 125)
                print(f"{'Symbol':<10} | {'Industry':<25} | {'MCap/EV (%)':<15} | {'Note'}")
                print("-" * 125)
                for index, row in all_outliers.iterrows():
                    print(f"{row['Symbol']:<10} | {row['IndustryName']:<25.25} | {row['MCap/EV (%)']:.2f}% | {row['Note']}")
                print("-" * 125)

def print_mcap_ev_table(title, dataframe, industry_bounds, small_industries):
    print(f"\n{'='*25} {title} {'='*25}")
    if not dataframe.empty:
        dataframe['Note'] = dataframe.apply(get_outlier_note, axis=1, args=(industry_bounds, small_industries))
        print("-" * 125)
        print(f"{'Symbol':<10} | {'Industry':<40} | {'MCap/EV (%)':<15} | {'Note'}")
        print("-" * 125)
        for index, row in dataframe.iterrows():
            print(f"{row['Symbol']:<10} | {row['IndustryName']:<40.40} | {row['MCap/EV (%)']:.2f}% | {row['Note']}")
        print("-" * 125)
    else:
        print("Could not identify any candidates in this category.")

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

        df = pd.read_csv(filename, delimiter=',')

        # Check for symbols with invalid values before cleaning
        if 'MCap/EV (%)' in df.columns and 'Symbol' in df.columns:
            # Using .astype(str).str.strip() to safely handle different dtypes and whitespace
            invalid_mask = df['MCap/EV (%)'].astype(str).str.strip() == '-inf'
            for symbol in df.loc[invalid_mask, 'Symbol']:
                print(f"WARNING: {symbol} has an invalid MCap/EV (%) value and will be excluded.")

        df = df[df['MCap/EV (%)'] != -np.inf] # Exclude rows with -inf

        required_columns = ['Symbol', 'SectorName', 'IndustryName', 'MCap/EV (%)']
        if not all(col in df.columns for col in required_columns):
            print(f"Warning: Some required columns are missing. Analysis might be incomplete. Missing: {[col for col in required_columns if col not in df.columns]}")

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

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Find MCap/EV outliers in a given CSV file.')
    parser.add_argument('filename', type=str, help='The path to the CSV file to analyze.')
    
    args = parser.parse_args()
    
    find_mcap_ev_outliers(args.filename)
