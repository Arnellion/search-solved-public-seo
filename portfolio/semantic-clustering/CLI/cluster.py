import time
import chardet
import pandas as pd
import os
import numpy as np
from collections import Counter
from sentence_transformers import SentenceTransformer
from polyfuzz import PolyFuzz
from polyfuzz.models import SentenceEmbeddings
import plotly.express as px
import plotly.io as pio
from rich import print
from nltk import ngrams
import typer
import platform
from rich.box import Box
from rich.console import Console
from rich.panel import Panel
import win32com.client as win32
from nltk.stem import PorterStemmer
import string

win32c = win32.constants

app = typer.Typer()

COMMON_COLUMN_NAMES = [
    "Keyword", "Keywords", "keyword", "keywords",
    "Search Terms", "Search terms", "Search term", "Search Term"
]

def stem_and_remove_punctuation(text: str, stem: bool):
    stemmer = PorterStemmer()
    # Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    # Stem the text if the stem flag is True
    if stem:
        text = ' '.join([stemmer.stem(word) for word in text.split()])
    return text

def create_unigram(cluster: str):
    """Create unigram from the cluster and return the most common word."""
    words = cluster.split()
    most_common_word = Counter(words).most_common(1)[0][0]
    return most_common_word

def get_model(model_name: str):
    """Create and return a SentenceTransformer model based on the given model name."""
    print(f"[white]Loading the SentenceTransformer model '{model_name}'...[/white]")
    model = SentenceTransformer(model_name)
    print("[white]Model loaded.[/white]")
    return model

def load_file(file_path: str):
    """Load a CSV file and return a DataFrame."""
    print(f"[white]Loading the CSV file from '{file_path}'...[/white]")
    result = chardet.detect(open(file_path, 'rb').read())
    encoding_value = result["encoding"]
    white_space = False if encoding_value != "UTF-16" else True

    df = pd.read_csv(
        file_path,
        encoding=encoding_value,
        delim_whitespace=white_space,
        on_bad_lines='skip',
    )
    print("[white]CSV file loaded.[/white]")
    return df

def create_chart(df, chart_type, output_path, volume):
    """Create a sunburst chart or a treemap."""
    if volume is not None:
        size = volume
    else:
        size = 'cluster_size'

    if chart_type == "sunburst":
        fig = px.sunburst(df, path=['hub', 'spoke'], values=size,
                          color_discrete_sequence=px.colors.qualitative.Pastel2)
    elif chart_type == "treemap":
        fig = px.treemap(df, path=['hub', 'spoke'], values=size,
                         color_discrete_sequence=px.colors.qualitative.Pastel2)
    else:
        print(f"[bold red]Invalid chart type: {chart_type}. Valid options are 'sunburst' and 'treemap'.[/bold red]")
        return

    fig.show()

    # Save the chart in the same directory as the final CSV.
    chart_file_path = os.path.join(os.path.dirname(output_path), f"{chart_type}.html")
    pio.write_html(fig, chart_file_path)

@app.command()
def main(
        file_path: str = typer.Argument(..., help='Path to your CSV file.'),
        column_name: str = typer.Option(None, help='Name of the column in your CSV to be processed.'),
        output_path: str = typer.Option(None, help='Path where the output CSV will be saved.'),
        chart_type: str = typer.Option("treemap", help="Type of chart to generate. 'sunburst' or 'treemap'."),
        device: str = typer.Option("cpu", help="Device to be used by SentenceTransformer. 'cpu' or 'cuda'."),
        model_name: str = typer.Option("all-MiniLM-L6-v2",
                                       help="Name of the SentenceTransformer model to use. For available models, refer to https://www.sbert.net/docs/pretrained_models.html"),
        min_similarity: float = typer.Option(0.95, help="Minimum similarity for clustering."),
        remove_dupes: bool = typer.Option(True, help="Whether to remove duplicates from the dataset."),
        excel_pivot: bool = typer.Option(False, help="Whether to save the output as an Excel pivot table."),
        volume: str = typer.Option(None, help='Name of the column containing numerical values. If --volume is used, the keyword with the largest volume will be used as the name of the cluster. If not, the shortest word will be used.'),
        stem: bool = typer.Option(True, "--no-stem", help="Whether to perform stemming on the 'hub' column.", show_default=False)
):
    # Clear the screen
    if platform.system() == 'Windows':
        os.system('cls')
    else:
        os.system('clear')

    # Print welcome message
    console = Console()
    welcome_message = "[bold white]Semantic Keyword Clustering Script Lee Foot 10-07-2023[/bold white]"
    panel = Panel(welcome_message, style="bold yellow", title="[b]SBERT Clustering[/b]")
    console.print(panel)

    if device not in ["cpu", "cuda"]:
        print("[bold red]Invalid device. Valid options are 'cpu' and 'cuda'.[/bold red]")
        return

    try:
        model = get_model(model_name)
    except Exception as e:
        print(f"[bold red]Failed to load the SentenceTransformer model: {e}[/bold red]")
        return

    try:
        df = load_file(file_path)
    except FileNotFoundError as e:
        print(f"[bold red]The file {file_path} does not exist.[/bold red]")
        return

    if column_name is None:
        print("[white]Searching for a column from the list of default column names...[/white]")
        for common_name in COMMON_COLUMN_NAMES:
            if common_name in df.columns:
                column_name = common_name
                print(f"[white]Found column '{column_name}'.[/white]\n")
                break
        else:
            print(f"[bold red]Could not find a suitable column for processing. Please specify the column name with the --column option.[/bold red]")
            return

    if column_name not in df.columns:
        print(f"[bold red]The column name {column_name} is not in the DataFrame.[/bold red]")
        return

    if volume is not None and volume not in df.columns:
        print(f"[bold red]The column name {volume} is not in the DataFrame.[/bold red]")
        return

        # Print options
    options_message = (
        f"[white]File path:[/white] [bold yellow]{file_path}[/bold yellow]\n"
        f"[white]Column name:[/white] [bold yellow]{column_name}[/bold yellow]\n"
        f"[white]Output path:[/white] [bold yellow]{output_path}[/bold yellow]\n"
        f"[white]Chart type:[/white] [bold yellow]{chart_type}[/bold yellow]\n"
        f"[white]Device:[/white] [bold yellow]{device}[/bold yellow]\n"
        f"[white]SentenceTransformer model:[/white] [bold yellow]{model_name}[/bold yellow]\n"
        f"[white]Minimum similarity:[/white] [bold yellow]{min_similarity}[/bold yellow]\n"
        f"[white]Remove duplicates:[/white] [bold yellow]{remove_dupes}[/bold yellow]\n"
        f"[white]Volume column:[/white] [bold yellow]{volume}[/bold yellow]\n"
        f"[white]Stemming enabled:[/white] [bold yellow]{stem}[/bold yellow]"
    )
    panel = Panel.fit(options_message, title="[b]Using The Following Options[/b]", style="white", border_style="white")
    console.print(panel)

    df.rename(columns={column_name: 'keyword', "spoke": "spoke Old"}, inplace=True)

    if remove_dupes:
        df.drop_duplicates(subset='keyword', inplace=True)

    df = df[df["keyword"].notna()]
    df['keyword'] = df['keyword'].astype(str)
    from_list = df['keyword'].to_list()

    embedding_model = SentenceTransformer(model_name, device=device)
    distance_model = SentenceEmbeddings(embedding_model)

    startTime = time.time()
    print("[white]Starting to cluster keywords...[/white]")

    model = PolyFuzz(distance_model)
    model = model.fit(from_list)
    model.group(link_min_similarity=min_similarity)

    df_cluster = model.get_matches()
    df_cluster.rename(columns={"From": "keyword", "Similarity": "similarity", "Group": "spoke"}, inplace=True)
    df = pd.merge(df, df_cluster[['keyword', 'spoke']], on='keyword', how='left')

    df['cluster_size'] = df['spoke'].map(df.groupby('spoke')['spoke'].count())
    df.loc[df["cluster_size"] == 1, "spoke"] = "no_cluster"
    df.insert(0, 'spoke', df.pop('spoke'))
    df['spoke'] = df['spoke'].str.encode('ascii', 'ignore').str.decode('ascii')
    df['keyword_len'] = df['keyword'].astype(str).apply(len)

    if volume is not None:
        df[volume] = df[volume].replace({'': 0, np.nan: 0}).astype(int)
        df = df.sort_values(by=volume, ascending=False)
    else:
        df = df.sort_values(by="keyword_len", ascending=True)

    df.insert(0, 'hub', df['spoke'].apply(create_unigram))
    df['hub'] = df['hub'].apply(lambda x: stem_and_remove_punctuation(x, stem))

    df = df[
        ['hub', 'spoke', 'cluster_size'] + [col for col in df.columns if col not in ['hub', 'spoke', 'cluster_size']]]

    df.sort_values(["spoke", "cluster_size"], ascending=[True, False], inplace=True)

    df['spoke'] = (df['spoke'].str.split()).str.join(' ')

    print(f"All keywords clustered successfully. Took {round(time.time() - startTime, 2)} seconds!")

    if output_path is None:
        output_path = os.path.splitext(file_path)[0] + '_output.csv'

    create_chart(df, chart_type, output_path, volume)

    df.drop(columns=['cluster_size', 'keyword_len'], inplace=True)
    output_path = "/python_scripts/serp_cluster.xlsx"

    if excel_pivot:
        # Save the DataFrame to an Excel file
        df.to_excel(output_path, index=False)

        # Start an instance of Excel
        excel = win32.gencache.EnsureDispatch('Excel.Application')
        excel.Visible = False

        # Open the workbook in Excel
        wb = excel.Workbooks.Open(output_path)

        # Get the active worksheet
        ws1 = wb.ActiveSheet

        # Create a new worksheet for the pivot table
        ws2 = wb.Sheets.Add()
        ws2.Name = "PivotTable"

        # Set up the pivot table source data
        source_range = ws1.UsedRange

        # Get the range address
        source_range_address = source_range.GetAddress()

        # Create the pivot cache
        pc = wb.PivotCaches().Create(SourceType=win32c.xlDatabase, SourceData=ws1.UsedRange)

        # Define the pivot table range
        pivot_range = ws2.Range(f"A1:C{df.shape[0] + 1}")

        # Create the pivot table
        pivot_table = pc.CreatePivotTable(TableDestination=pivot_range, TableName="PivotTable")

        # Set up the row fields
        pivot_table.PivotFields("hub").Orientation = win32c.xlRowField
        pivot_table.PivotFields("hub").Position = 1
        pivot_table.PivotFields("spoke").Orientation = win32c.xlRowField
        pivot_table.PivotFields("spoke").Position = 2
        pivot_table.PivotFields("keyword").Orientation = win32c.xlRowField

        if volume is not None:
            pivot_table.PivotFields(volume).Orientation = win32c.xlDataField

            # Save and close
        wb.Save()
        excel.Application.Quit()

        print(f"[white]Results saved to '{output_path}'.[/white]")

    else:
        # Save dataframe to a CSV file
        df.to_csv(output_path, index=False)

        print(f"[white]Results saved to '{output_path}'.[/white]")

if __name__ == "__main__":
    app()