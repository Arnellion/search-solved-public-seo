import streamlit as st
import pandas as pd
import chardet
from polyfuzz import PolyFuzz
import base64
import numpy as np
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from polyfuzz.models import TFIDF, EditDistance, RapidFuzz
import xlsxwriter


# Streamlit Interface Setup and Utilities ------------------------------------------------------------------------------

def setup_streamlit_interface():
    st.set_page_config(page_title="Automatic Website Migration Tool | LeeFoot.co.uk", layout="wide")
    st.title("Automatic Website Migration Tool")
    st.markdown("### Effortlessly migrate your website data")

    # Add the creator information here
    st.markdown("""
        <p style="font-style: italic;">Created by <a href="https://twitter.com/LeeFootSEO" target="_blank">LeeFootSEO</a> | <a href="https://leefoot.co.uk" target="_blank">Website</a></p>
        """, unsafe_allow_html=True)

    show_instructions_expander()


def create_file_uploader_widget(column, file_types):
    file_type_label = "/".join(file_types).upper()  # Creating a string like "CSV/XLSX/XLS"
    return st.file_uploader(f"Upload {column} {file_type_label}", type=file_types)


def select_columns_for_data_matching(title, options, default_value, max_selections):
    st.write(title)
    return st.multiselect(title, options, default=default_value, max_selections=max_selections)


def show_warning_message(message):
    st.warning(message)


def show_instructions_expander():
    with st.expander("How to Use This Tool"):
        st.write("""
            - Crawl both the staging and live Websites using Screaming Frog SEO Spider.
            - Export the HTML as CSV Files.
            - Upload your 'Live' and 'Staging' CSV files using the file uploaders below.
            - By Default the app looks for columns named 'Address' 'H1-1' and 'Title 1' but they can be manually mapped if not found.
            - Select up to 3 columns that you want to match.
            - Click the 'Process Files' button to start the matching process.
            - Once processed, a download link for the output file will be provided.
            - Statistic such as median match score and a total mediam similarity score will be shown. Run the script with a different combination of columns to get the best score!
        """)


def create_page_footer_with_contact_info():
    st.markdown("""
        <hr style="height:2px;border-width:0;color:gray;background-color:gray">
        <p style="font-style: italic;">Need an app? Need this run as a managed service? <a href="mailto:hello@leefoot.co.uk">Hire Me!</a></p>
        """, unsafe_allow_html=True)


def validate_uploaded_files(file1, file2):
    if not file1 or not file2 or file1.getvalue() == file2.getvalue():
        show_warning_message(
            "Warning: The same file has been uploaded for both live and staging. Please upload different files.")
        return False
    return True


def create_file_uploader_widgets():
    col1, col2 = st.columns(2)
    with col1:
        file_live = create_file_uploader_widget("Live", ['csv', 'xlsx', 'xls'])
    with col2:
        file_staging = create_file_uploader_widget("Staging", ['csv', 'xlsx', 'xls'])
    return file_live, file_staging


def handle_data_matching_and_processing(df_live, df_staging, address_column, selected_additional_columns,
                                        selected_model):
    message_placeholder = st.empty()
    message_placeholder.info('Matching Columns, Please Wait!')

    rename_dataframe_column(df_live, address_column, 'Address')
    rename_dataframe_column(df_staging, address_column, 'Address')

    all_selected_columns = ['Address'] + selected_additional_columns
    progress_bar = st.progress(0)
    df_final = process_uploaded_files_and_match_data(df_live, df_staging, all_selected_columns, progress_bar,
                                                     message_placeholder,
                                                     selected_additional_columns, selected_model)
    return df_final


# File Reading and Data Preparation ------------------------------------------------------------------------------------

def read_excel_file(file, dtype):
    return pd.read_excel_file(file, dtype=dtype)


def read_csv_file_with_detected_encoding(file, dtype):
    result = chardet.detect(file.getvalue())
    encoding = result['encoding']
    return pd.read_csv(file, dtype=dtype, encoding=encoding, on_bad_lines='skip')


def convert_dataframe_to_lowercase(df):
    return df.apply(lambda col: col.str.lower() if col.dtype == 'object' else col)


def rename_dataframe_column(df, old_name, new_name):
    df.rename(columns={old_name: new_name}, inplace=True)


def process_and_validate_uploaded_files(file_live, file_staging):
    if validate_uploaded_files(file_live, file_staging):
        # Determine file type and read accordingly
        if file_live.name.endswith('.csv'):
            df_live = read_csv_file_with_detected_encoding(file_live, "str")
        else:  # Excel file
            df_live = read_excel_file(file_live, "str")

        if file_staging.name.endswith('.csv'):
            df_staging = read_csv_file_with_detected_encoding(file_staging, "str")
        else:  # Excel file
            df_staging = read_excel_file(file_staging, "str")

        # Check if dataframes are empty
        if df_live.empty or df_staging.empty:
            show_warning_message("Warning: One or both of the uploaded files are empty.")
            return None, None
        else:
            return df_live, df_staging
    return None, None


# Data Matching and Analysis -------------------------------------------------------------------------------------------

def initialise_matching_model(selected_model="TF-IDF"):
    if selected_model == "Edit Distance":
        from polyfuzz.models import EditDistance
        model = EditDistance()
    elif selected_model == "RapidFuzz":
        from polyfuzz.models import RapidFuzz
        model = RapidFuzz()
    else:  # Default to TF-IDF
        from polyfuzz.models import TFIDF
        model = TFIDF(min_similarity=0)
    return model


def setup_matching_model(selected_model):
    if selected_model == "Edit Distance":
        model = PolyFuzz(EditDistance())
    elif selected_model == "RapidFuzz":
        model = PolyFuzz(RapidFuzz())
    else:  # Default to TF-IDF
        model = PolyFuzz(TFIDF())
    return model


def match_columns_and_compute_scores(model, df_live, df_staging, matching_columns):
    matches_scores = {}
    for col in matching_columns:
        live_list = df_live[col].fillna('').tolist()
        staging_list = df_staging[col].fillna('').tolist()
        if live_list and staging_list:
            model.match(live_list, staging_list)
            matches = model.get_matches()
            matches_scores[col] = matches
    return matches_scores


def identify_best_matching_url(row, matches_scores, matching_columns, df_staging):
    best_match_info = {'Best Match on': None, 'Highest Matching URL': None,
                       'Highest Similarity Score': 0, 'Best Match Content': None}
    similarities = []

    for col in matching_columns:
        matches = matches_scores.get(col, pd.DataFrame())
        if not matches.empty:
            match_row = matches.loc[matches['From'] == row[col]]
            if not match_row.empty:
                similarity_score = match_row.iloc[0]['Similarity']
                similarities.append(similarity_score)
                if similarity_score > best_match_info['Highest Similarity Score']:
                    best_match_info.update({
                        'Best Match on': col,
                        'Highest Matching URL':
                            df_staging.loc[df_staging[col] == match_row.iloc[0]['To'], 'Address'].values[0],
                        'Highest Similarity Score': similarity_score,
                        'Best Match Content': match_row.iloc[0]['To']
                    })

    best_match_info['Median Match Score'] = np.median(similarities) if similarities else None
    return best_match_info, similarities


def add_additional_info_to_match_results(best_match_info, df_staging, selected_additional_columns):
    for additional_col in selected_additional_columns:
        if additional_col in df_staging.columns:
            staging_value = df_staging.loc[
                df_staging['Address'] == best_match_info['Highest Matching URL'], additional_col].values
            best_match_info[f'Staging {additional_col}'] = staging_value[0] if staging_value.size > 0 else None
    return best_match_info


def identify_best_matching_url_and_median(df_live, df_staging, matches_scores, matching_columns,
                                          selected_additional_columns):
    def process_row(row):
        best_match_info, similarities = identify_best_matching_url(row, matches_scores, matching_columns, df_staging)
        best_match_info = add_additional_info_to_match_results(best_match_info, df_staging, selected_additional_columns)
        # Convert scores to percentage format with '%' sign
        best_match_info['All Column Match Scores'] = [(col, f"{round(score * 100)}%") for col, score in
                                                      zip(matching_columns, similarities)]
        return pd.Series(best_match_info)

    return df_live.apply(process_row, axis=1)


def finalise_match_results_processing(df_live, df_staging, matches_scores, matching_columns,
                                      selected_additional_columns):
    match_results = identify_best_matching_url_and_median(df_live, df_staging, matches_scores, matching_columns,
                                                          selected_additional_columns)
    df_final = prepare_concatenated_dataframe_for_display(df_live, match_results, matching_columns)
    return df_final


def process_uploaded_files_and_match_data(df_live, df_staging, matching_columns, progress_bar, message_placeholder,
                                          selected_additional_columns,
                                          selected_model):
    df_live = convert_dataframe_to_lowercase(df_live)
    df_staging = convert_dataframe_to_lowercase(df_staging)

    model = setup_matching_model(selected_model)
    matches_scores = process_column_matches_and_scores(model, df_live, df_staging, matching_columns)

    for index, _ in enumerate(matching_columns):
        progress = (index + 1) / len(matching_columns)
        progress_bar.progress(progress)

    message_placeholder.info('Finalising the processing. Please Wait!')
    df_final = finalise_match_results_processing(df_live, df_staging, matches_scores, matching_columns,
                                                 selected_additional_columns)

    display_final_results_and_download_link(df_final, 'migration_mapping_data.xlsx')
    message_placeholder.success('Complete!')

    return df_final


def scale_median_match_scores_to_percentage(df_final):
    df_final['Median Match Score Scaled'] = df_final['Median Match Score'] * 100
    return df_final


def group_median_scores_into_brackets(df_final):
    bins = range(0, 110, 10)
    labels = [f'{i}-{i + 10}' for i in range(0, 100, 10)]
    df_final['Score Bracket'] = pd.cut(df_final['Median Match Score Scaled'], bins=bins, labels=labels,
                                       include_lowest=True)
    return df_final


def generate_score_distribution_dataframe(df_final):
    df_final['Median Match Score Scaled'] = df_final['Median Match Score'] * 100
    bins = range(0, 110, 10)
    labels = [f'{i}-{i + 10}' for i in range(0, 100, 10)]
    df_final['Score Bracket'] = pd.cut(df_final['Median Match Score Scaled'], bins=bins, labels=labels,
                                       include_lowest=True)
    score_brackets = df_final['Score Bracket'].value_counts().sort_index().reindex(labels, fill_value=0)

    score_data = pd.DataFrame({
        'Score Bracket': score_brackets.index,
        'URL Count': score_brackets.values
    })
    return score_data


def select_columns_for_data_matching_for_matching(df_live, df_staging):
    common_columns = list(set(df_live.columns) & set(df_staging.columns))
    address_defaults = ['Address', 'URL', 'url', 'Adresse', 'Dirección', 'Indirizzo']
    default_address_column = next((col for col in address_defaults if col in common_columns), common_columns[0])

    st.write("Select the column to use as 'Address':")
    address_column = st.selectbox("Address Column", common_columns, index=common_columns.index(default_address_column))

    additional_columns = [col for col in common_columns if col != address_column]
    default_additional_columns = ['H1-1', 'Title 1', 'Titel 1', 'Título 1', 'Titolo 1']
    default_selection = [col for col in default_additional_columns if col in additional_columns]

    st.write("Select additional columns to match (optional, max 3):")
    max_additional_columns = min(3, len(additional_columns))
    # Ensure default selections do not exceed the maximum allowed
    default_selection = default_selection[:max_additional_columns]
    selected_additional_columns = st.multiselect("Additional Columns", additional_columns,
                                                 default=default_selection,
                                                 max_selections=max_additional_columns)
    return address_column, selected_additional_columns


def process_column_matches_and_scores(model, df_live, df_staging, matching_columns):
    return match_columns_and_compute_scores(model, df_live, df_staging, matching_columns)


# Data Visualization and Reporting -------------------------------------------------------------------------------------

def plot_median_score_histogram(df_final, col):
    bracket_counts = df_final['Score Bracket'].value_counts().sort_index()

    with col:
        plt.figure(figsize=(5, 3))
        ax = bracket_counts.plot(kind='bar', width=0.9)
        ax.set_title('Distribution of Median Match Scores', fontsize=10)
        ax.set_xlabel('Median Match Score Brackets', fontsize=8)
        ax.set_ylabel('URL Count', fontsize=8)
        ax.tick_params(axis='both', which='major', labelsize=8)
        ax.grid(axis='y')
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: int(x)))
        plt.tight_layout()
        st.pyplot(plt)


def display_final_results_and_download_link(df_final, filename):
    show_download_link_for_final_excel(df_final, filename)
    display_median_score_brackets_chart(df_final)
    st.balloons()


def display_median_similarity_indicator_chart(df_final, col):
    median_similarity_score = df_final['Highest Similarity Score'].median()

    if 'previous_score' in st.session_state:
        reference_value = st.session_state['previous_score']
    else:
        reference_value = median_similarity_score

    fig = go.Figure()
    fig.add_trace(go.Indicator(
        mode="number+delta",
        value=median_similarity_score,
        delta={'reference': reference_value, 'relative': False, 'valueformat': '.2%'},
        number={'valueformat': '.2%', 'font': {'color': 'black'}},
        title={'text': "Total Median Similarity Score for Selected Columns", 'font': {'color': 'black'}},
        domain={'row': 0, 'column': 0}))

    fig.update_layout(
        grid={'rows': 1, 'columns': 1, 'pattern': "independent"}
    )

    with col:
        st.plotly_chart(fig)

    st.session_state['previous_score'] = median_similarity_score


def display_median_score_brackets_chart(df_final):
    df_scaled = scale_median_match_scores_to_percentage(df_final)
    df_bracketed = group_median_scores_into_brackets(df_scaled)

    col1, col2 = st.columns(2)
    plot_median_score_histogram(df_bracketed, col1)
    display_median_similarity_indicator_chart(df_final, col2)


# Excel File Operations ------------------------------------------------------------------------------------------------

def create_excel_with_dataframes(df, score_data, filename):
    excel_writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    df.to_excel(excel_writer, sheet_name='Mapped URLs', index=False)
    score_data.to_excel(excel_writer, sheet_name='Median Score Distribution', index=False)
    return excel_writer


def apply_formatting_to_excel_sheets(excel_writer, df):
    workbook = excel_writer.book
    worksheet1 = excel_writer.sheets['Mapped URLs']

    # Formats
    left_align_format = workbook.add_format({'align': 'left'})
    percentage_format = workbook.add_format({'num_format': '0.00%', 'align': 'center'})

    num_rows = len(df)
    num_cols = len(df.columns)
    worksheet1.add_table(0, 0, num_rows, num_cols - 1, {'columns': [{'header': col} for col in df.columns]})
    worksheet1.freeze_panes(1, 0)

    max_col_width = 80
    for i, col in enumerate(df.columns):
        col_width = max(len(col), max(df[col].astype(str).apply(len).max(), 10)) + 2
        col_width = min(col_width, max_col_width)

        # Apply specific formatting for columns 'E', 'F', and 'H' (indices 4, 5, and 7)
        if i in [3, 5, 7]:  # Adjusting the indices for columns E, F, and H
            worksheet1.set_column(i, i, col_width, percentage_format)
            # Apply 3-color scale formatting with specified colors
            worksheet1.conditional_format(1, i, num_rows, i, {
                'type': '3_color_scale',
                'min_color': "#f8696b",  # Custom red for lowest values
                'mid_color': "#ffeb84",  # Custom yellow for middle values
                'max_color': "#63be7b"  # Custom green for highest values
            })
        else:
            worksheet1.set_column(i, i, col_width, left_align_format)

    return workbook


def add_chart_to_excel_sheet(excel_writer, score_data):
    workbook = excel_writer.book
    worksheet2 = excel_writer.sheets['Median Score Distribution']
    chart = workbook.add_chart({'type': 'column'})
    max_row = len(score_data) + 1

    chart.add_series({
        'name': "='Median Score Distribution'!$B$1",
        'categories': "='Median Score Distribution'!$A$2:$A$" + str(max_row),
        'values': "='Median Score Distribution'!$B$2:$B$" + str(max_row),
    })

    chart.set_title({'name': 'Distribution of Median Match Scores'})
    chart.set_x_axis({'name': 'Median Match Score Brackets'})
    chart.set_y_axis({'name': 'URL Count'})
    worksheet2.insert_chart('D2', chart)


def create_excel_download_link(filename):
    with open(filename, 'rb') as file:
        b64 = base64.b64encode(file.read()).decode()
    return f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">Click here to download {filename}</a>'


def generate_excel_download_and_display_link(df, filename, score_data):
    excel_writer = create_excel_with_dataframes(df, score_data, filename)
    apply_formatting_to_excel_sheets(excel_writer, df)
    add_chart_to_excel_sheet(excel_writer, score_data)
    excel_writer.close()

    download_link = create_excel_download_link(filename)
    st.markdown(download_link, unsafe_allow_html=True)


def show_download_link_for_final_excel(df_final, filename):
    df_for_score_data = df_final.drop(['Median Match Score Scaled', 'Score Bracket'], axis=1, inplace=False,
                                      errors='ignore')
    score_data = generate_score_distribution_dataframe(df_for_score_data)
    generate_excel_download_and_display_link(df_final, 'migration_mapping_data.xlsx', score_data)


# Main Function and Additional Utilities -------------------------------------------------------------------------------

def format_match_scores_as_strings(df):
    df['All Column Match Scores'] = df['All Column Match Scores'].apply(lambda x: str(x) if x is not None else None)
    return df


def merge_live_and_matched_dataframes(df_live, match_results, matching_columns):
    final_columns = ['Address'] + [col for col in matching_columns if col != 'Address']
    return pd.concat([df_live[final_columns], match_results], axis=1)


def prepare_concatenated_dataframe_for_display(df_live, match_results, matching_columns):
    final_df = merge_live_and_matched_dataframes(df_live, match_results, matching_columns)
    final_df = format_match_scores_as_strings(final_df)
    return final_df


def main():
    setup_streamlit_interface()

    # Advanced settings expander for model selection
    with st.expander("Advanced Settings"):
        model_options = ['TF-IDF', 'Edit Distance', 'RapidFuzz']
        selected_model = st.selectbox("Select Matching Model", model_options)

        if selected_model == "TF-IDF":
            st.write("Use TF-IDF for comprehensive text analysis, suitable for most use cases.")
        elif selected_model == "Edit Distance":
            st.write(
                "Edit Distance is useful for matching based on character-level differences, such as small text variations.")
        elif selected_model == "RapidFuzz":
            st.write("RapidFuzz is efficient for large datasets, offering fast and approximate string matching.")

    file_live, file_staging = create_file_uploader_widgets()
    if file_live and file_staging:
        df_live, df_staging = process_and_validate_uploaded_files(file_live, file_staging)
        if df_live is not None and df_staging is not None:
            address_column, selected_additional_columns = select_columns_for_data_matching_for_matching(df_live,
                                                                                                        df_staging)
            if st.button("Process Files"):
                df_final = handle_data_matching_and_processing(df_live, df_staging, address_column,
                                                               selected_additional_columns,
                                                               selected_model)

    create_page_footer_with_contact_info()


if __name__ == "__main__":
    main()
