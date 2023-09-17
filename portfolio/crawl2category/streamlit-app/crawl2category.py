import streamlit as st
import string
import nltk
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import base64
import inflect
import chardet
from nltk.corpus import stopwords
from collections import Counter
import traceback

# Initialize the inflect engine
p = inflect.engine()
nltk.download('punkt')
st.set_page_config(page_title="Product2Category - Automatic Category Suggestion Tool", layout="wide")

# Check if stopwords are already downloaded
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

# Load the stopwords
stop_words = set(stopwords.words('english'))

# Load the pre-trained Sentence Transformer model
model = SentenceTransformer('paraphrase-MiniLM-L3-v2')  # Fastest

def clean_text(text):
    return ''.join([c if c not in string.punctuation else ' ' for c in text]).lower()

def detect_file_encoding(file):
    rawdata = file.read(10000)
    file.seek(0)  # Ensure the file pointer is reset after reading
    result = chardet.detect(rawdata)
    return result['encoding']

def filter_combinations(product_name, combinations, threshold):
    if not combinations:
        return []
    similarities = semantic_similarity_batch([product_name], combinations)[0]
    return [combo for idx, combo in enumerate(combinations) if similarities[idx] > threshold]

def pluralize_except_numbers(text):
    if isinstance(text, str):
        if text[-1].isdigit():
            return text
        return p.plural(text)
    return text


def generate_ngrams(text, n):
    tokens = nltk.word_tokenize(text)
    ngrams = list(nltk.ngrams(tokens, n))
    ngrams = [' '.join(gram) for gram in ngrams]
    ngrams = [clean_text(gram) for gram in ngrams]
    ngrams = [remove_stopwords(gram) for gram in ngrams]
    return ngrams


def remove_stopwords(text):
    tokens = nltk.word_tokenize(text)
    filtered_tokens = [word for word in tokens if word.lower() not in stop_words]
    return ' '.join(filtered_tokens)

def semantic_similarity_batch(texts1, texts2):
    vectors1 = model.encode(texts1)
    vectors2 = model.encode(texts2)
    dot_products = np.dot(vectors1, vectors2.T)
    norms1 = np.linalg.norm(vectors1, axis=1)
    norms2 = np.linalg.norm(vectors2, axis=1)
    return dot_products / (norms1[:, None] * norms2)


def process_data(uploaded_file, file_type, selected_column, n_grams, similarity_threshold, override_delimiter):
    try:
        if 'excel' in file_type or 'spreadsheetml' in file_type:
            try:
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            except Exception as e:
                st.error(f"An error occurred while reading the Excel file: {str(e)}")
                return None
        else:
            # Resetting to the beginning of the file
            uploaded_file.seek(0)

            # Detect file encoding
            raw_bytes = uploaded_file.read()
            result = chardet.detect(raw_bytes)
            file_encoding = result['encoding'].lower()

            # Resetting to the beginning of the file again before reading it as a dataframe
            uploaded_file.seek(0)

            if file_encoding == 'utf-8' or file_encoding == 'utf-8-sig':
                df = pd.read_csv(uploaded_file, on_bad_lines='skip', low_memory=False)
            elif file_encoding == 'utf-16':
                df = pd.read_csv(uploaded_file, on_bad_lines='skip', low_memory=False, encoding='utf-16')
            else:
                st.error(f"Unsupported encoding: {file_encoding}")
                return None

        df = df[df[selected_column].notna()]

        if override_delimiter:
            delimiter = override_delimiter
        else:
            delimiter_counts = Counter("".join(df[selected_column].dropna().tolist()))

            for char in string.ascii_letters + string.digits + " ":
                del delimiter_counts[char]
            delimiter = max(delimiter_counts, key=delimiter_counts.get)

        # Display the detected delimiter
        st.info(f"Detected delimiter: '{delimiter}'")
        existing_categories = set()
        for categories in df[selected_column].dropna():
            existing_categories.update(categories.split(delimiter))
        existing_categories = {clean_text(cat) for cat in existing_categories}

        df['N_grams'] = df[selected_column].apply(lambda x: generate_ngrams(x, n_grams))

        # Progress bar for Streamlit
        progress_bar = st.progress(0)
        processed_data = []

        # Get the index of the selected column
        selected_column_idx = df.columns.get_loc(
            selected_column) + 1  # +1 because the first index in itertuples() is the row index

        for idx, row in enumerate(df.itertuples()):
            processed_data.append(filter_combinations(row[selected_column_idx], row.N_grams, similarity_threshold))
            progress_bar.progress((idx + 1) / len(df))

        df['Relevant Combinations'] = processed_data

        df = df.explode("Relevant Combinations")
        df.drop_duplicates(subset=[selected_column, 'Relevant Combinations'], inplace=True)
        df = df[df["Relevant Combinations"].notna()]

        df['Relevant Combinations'] = df['Relevant Combinations'].apply(
            lambda x: x if x not in existing_categories else np.nan)
        df['Plural Combinations'] = df['Relevant Combinations'].apply(pluralize_except_numbers)
        df['Plural Combinations'] = df['Plural Combinations'].apply(
            lambda x: x if x not in existing_categories else np.nan)

        return df

    except Exception as e:
        st.error(f"An error occurred: {e}")


def download_link(object_to_download, download_filename, download_link_text):
    """
    Generates a link to download the given object_to_download.
    """
    if isinstance(object_to_download, pd.DataFrame):
        object_to_download = object_to_download.to_csv(index=False)

    # some strings <-> bytes conversions necessary here
    b64 = base64.b64encode(object_to_download.encode()).decode()

    return f'<a href="data:application/octet-stream;base64,{b64}" download="{download_filename}">{download_link_text}</a>'


# Streamlit UI
st.title("Product2Category - Automatic Category Name Suggester")

# Help Documentation
if st.checkbox("Show Help Documentation"):
    st.markdown("""
    ### **Overview**

    This Tool analyses product exports or crawl files to automatically suggest opportunties to create new categories. It works by generating n-gram combinations of product names, both in plural and singular form and appends them to the original file.

    These n-gram combinations can be utilized to identify potential search volume opportunities, hinting at chances to create new product categories.

    ### **How to Use**

    1. **Upload a File**:
       Begin by uploading a crawl file or a product export from your e-commerce platform. This file should preferably be in CSV format.

    2. **Select the Product Name Column**:
       Once the file is uploaded, you'll be prompted to select the column that contains product names from a dropdown menu.

    3. **Configure Settings**:
       - **N-grams**: Select the desired 'N' for generating N-grams. This represents the number of words or tokens in the generated combinations.
       - **Similarity Threshold**: Adjust the slider to set the similarity threshold. This determines how similar the suggested combinations are to the original product name.
       - **Override Delimiter**: If your categories column uses a specific delimiter (e.g., a comma, semicolon), specify it here. If left blank, the tool will attempt to auto-detect the delimiter.

    4. **Process**: 
       Click the 'Process' button. The tool will then generate the n-gram combinations and display the results in a table format.

    5. **Download**:
       After processing, you can download the modified file with the two new columns appended. The file will be in CSV format and will be named 'suggested_keywords.csv'.

    6. **Next Steps**:
       It's recommended to run the generated n-gram combinations through a search volume analysis tool. This will provide insights into potential search traffic and indicate opportunities for creating new product categories.

    ### **Tips and Best Practices**

    - **File Format**: While the tool primarily supports CSV files, ensure that the uploaded file is well-structured and consistent to avoid any parsing errors.
    - **Search Volume Analysis**: Use renowned search volume analysis tools for accurate insights. This can help in making informed decisions about category creation.
    - **Regular Updates**: Regularly updating your product list and rerunning the analysis can provide fresh insights as market trends change.
    """)

# UI Elements for File Upload and Processing
uploaded_file = st.file_uploader("Choose a file", type=['csv', 'xlsx', 'xls'])

if uploaded_file is not None:
    raw_bytes = uploaded_file.read()
    st.write(raw_bytes[:1000])  # Print the first 1000 bytes to check its content
    file_details = uploaded_file.type
    st.write(f"Detected file type: {file_details}")

    # Initialize df_preview
    df_preview = None

    # If the file is an excel file
    if 'excel' in file_details or 'spreadsheetml' in file_details:
        try:
            df_preview = pd.read_excel(uploaded_file, nrows=5, engine='openpyxl')  # specify the engine
        except Exception as e:
            st.error(f"An error occurred while reading the Excel file: {str(e)}")
            st.write(traceback.format_exc())

    # Otherwise, if it's a CSV
    elif 'csv' in file_details:
        try:
            # Determine the encoding of the uploaded file
            uploaded_file.seek(0)
            file_encoding = detect_file_encoding(uploaded_file)

            # Now, proceed to read with the detected encoding
            uploaded_file.seek(0)  # Resetting to the beginning of the file
            df_preview = pd.read_csv(uploaded_file, nrows=5, encoding=file_encoding)
        except pd.errors.EmptyDataError:
            st.error("The uploaded CSV file does not contain any data or columns. Please upload a valid CSV file.")
        except Exception as e:
            st.error(f"An error occurred while reading the CSV file: {str(e)}")
            st.write(traceback.format_exc())

    else:
        st.error("Unsupported file type. Please upload a CSV or Excel file.")

    # If df_preview is successfully created
    if df_preview is not None:
        st.write('Preview of uploaded data:')
        st.write(df_preview)

        selected_column = st.selectbox("Select the column with product names", df_preview.columns.tolist())

    n_grams = st.slider("Select N for N-grams", 1, 10, 6)
    similarity_threshold = st.slider("Select similarity threshold", 0.1, 1.0, 0.6)
    override_delimiter = st.text_input("Override delimiter (leave empty to auto-detect)")

    if st.button('Process'):
        uploaded_file.seek(0)  # Reset the file pointer to the beginning
        result_df = process_data(uploaded_file, file_details, selected_column, n_grams, similarity_threshold,
                                 override_delimiter)

        st.write('Processed Data:')
        st.write(result_df)

        # Add a download button
        if result_df is not None:
            st.markdown(download_link(result_df, 'suggested_keywords.csv', 'Download Processed Data as CSV'),
                        unsafe_allow_html=True)
