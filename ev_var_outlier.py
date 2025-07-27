import pandas as pd
import numpy as np
import re
import argparse

MINIMUM_GROUP_SIZE = 5
STOCKS_TOP = 50

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

def print_outlier_table(title, dataframe):
    print(f"\n\n{'='*25} {title} {'='*25}")
    if not dataframe.empty:
        print("-" * 150)
        print(f"{'Symbol':<10} | {'Industry':<40} | {'MCap/EV (%)':<15} | {'VaR/Ask Ratio':<15} | {'Note'}")
        print("-" * 150)
        for _, row in dataframe.iterrows():
            print(f"{row['Symbol']:<10} | {row['IndustryName']:<40.40} | {row['MCap/EV (%)']:.2f}% | {row['VaR_to_Ask_Ratio']:.4f} | {row['Note']}")
        print("-" * 150)
    else:
        print("No outliers found in this category.")

def find_dual_outliers(filename):
    try:
        df = pd.read_csv(filename)
        df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=['MCap/EV (%)', 'VaR_to_Ask_Ratio'])

        # Unactionable Symbols
        close_only_symbols = df[df['TradeMode'] == 3]
        df = df[df['TradeMode'] != 3] # Exclude close-only from analysis

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
        bottom_100_var = df.sort_values(by='VaR_to_Ask_Ratio', ascending=True).head(100)
        
        mcap_in_bottom_100 = pd.merge(mcap_outliers, bottom_100_var, on='Symbol', how='inner')
        mcap_in_bottom_100['Note'] = mcap_in_bottom_100.apply(lambda row: f"{row['Note_x']} in Bottom 100 VaR", axis=1)
        mcap_in_bottom_100 = mcap_in_bottom_100.rename(columns={'IndustryName_x': 'IndustryName', 'MCap/EV (%)_x': 'MCap/EV (%)', 'VaR_to_Ask_Ratio_x': 'VaR_to_Ask_Ratio'})
        
        actionable_outliers = pd.concat([dual_outliers, mcap_in_bottom_100]).drop_duplicates(subset=['Symbol']).sort_values(by='MCap/EV (%)', ascending=False)

        print_outlier_table("Actionable Outliers", actionable_outliers)

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
    find_dual_outliers(args.filename)
