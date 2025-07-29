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
            if col_format:
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
        ('VaR_to_Ask_Ratio', 'VaR/Ask Ratio', '.4f'),
        ('Note', 'Note', None)
    ]
    _print_table(title, dataframe, columns_info)

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
        top_100_var = df.sort_values(by='VaR_to_Ask_Ratio', ascending=False).head(100)
        
        mcap_in_bottom_100 = pd.merge(mcap_outliers, bottom_100_var, on='Symbol', how='inner')
        mcap_in_bottom_100['Note'] = mcap_in_bottom_100.apply(lambda row: f"{row['Note_x']} in Bottom 100 VaR", axis=1)
        mcap_in_bottom_100 = mcap_in_bottom_100.rename(columns={'IndustryName_x': 'IndustryName', 'MCap/EV (%)_x': 'MCap/EV (%)', 'VaR_to_Ask_Ratio_x': 'VaR_to_Ask_Ratio'})

        mcap_in_top_100 = pd.merge(mcap_outliers, top_100_var, on='Symbol', how='inner')
        mcap_in_top_100['Note'] = mcap_in_top_100.apply(lambda row: f"{row['Note_x']} in Top 100 VaR", axis=1)
        mcap_in_top_100 = mcap_in_top_100.rename(columns={'IndustryName_x': 'IndustryName', 'MCap/EV (%)_x': 'MCap/EV (%)', 'VaR_to_Ask_Ratio_x': 'VaR_to_Ask_Ratio'})
        
        actionable_outliers = pd.concat([dual_outliers, mcap_in_bottom_100, mcap_in_top_100]).drop_duplicates(subset=['Symbol']).sort_values(by='MCap/EV (%)', ascending=False)

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
