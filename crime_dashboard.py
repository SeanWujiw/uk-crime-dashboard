from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import re
import folium
from folium import Icon, Marker
from folium.plugins import MarkerCluster
from branca.element import Figure

# ─── STEP 0: “Download-if-missing” snippet ────────────────────────────────────
import pathlib, requests

# Create a “data” directory next to this script
DATA_DIR = pathlib.Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Define where we’ll store the CSV locally, and the S3 URL
CSV_PATH = DATA_DIR / "crime_data_merged.csv"
CSV_URL  = "https://uk-crime-dashboard-data.s3.eu-west-2.amazonaws.com/crime_data_merged.csv"

# If the CSV isn’t already on disk, fetch it from S3
if not CSV_PATH.exists():
    print("Downloading merged CSV from S3…")
    with requests.get(CSV_URL, stream=True) as r:
        r.raise_for_status()
        with open(CSV_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print("Download complete →", CSV_PATH)

# Load the dataframe exactly as before
merged_df = pd.read_csv(CSV_PATH)
# ───────────────────────────────────────────────────────────────────────────────

# Function to strip trailing codes from LSOA names
def extract_location_name(lsoa_name):
    return re.sub(r"\s\d+[A-Z]*$", "", lsoa_name)

merged_df["Common Location"] = merged_df["LSOA name"].apply(extract_location_name)

# Prepare dropdown values
months = sorted(merged_df["Month"].unique())
month_options = [{"label": m, "value": m} for m in months]
month_options.insert(0, {"label": "All Months", "value": "all"})

crime_types = sorted(merged_df["Crime type"].unique())
crime_type_options = [{"label": "All Crimes", "value": "All Crimes"}] + [
    {"label": ct, "value": ct} for ct in crime_types
]

locations = sorted(merged_df["LSOA name"].unique())
common_locations = sorted(merged_df["Common Location"].unique())

# Compute average coords for each common location
location_coords = (
    merged_df.groupby("Common Location")[["Latitude", "Longitude"]]
    .mean()
    .dropna()
    .reset_index()
)
coords_dict = {
    row["Common Location"]: (row["Latitude"], row["Longitude"])
    for _, row in location_coords.iterrows()
}

color_palette = [
    "red",
    "blue",
    "green",
    "purple",
    "orange",
    "darkred",
    "lightred",
    "beige",
    "darkblue",
    "darkgreen",
    "cadetblue",
    "darkpurple",
    "pink",
    "lightblue",
    "lightgreen",
    "gray",
    "black",
    "lightgray",
]

# ─── Initialize Dash app ──────────────────────────────────────────────────────
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "UK Crime Dashboard"
server = app.server  # for deployment

# ─── Tab 1: Bar Chart Dashboard ────────────────────────────────────────────────
tab1_layout = html.Div(
    [
        html.H3("Bar Chart Dashboard", style={"color": "white"}),
        dcc.Dropdown(
            id="month-dropdown",
            options=month_options,
            value="all",
            clearable=False,
            style={"width": "50%", "color": "black"},
        ),
        dcc.Dropdown(
            id="bar-crime-type-dropdown",
            options=crime_type_options,
            multi=True,
            value=["All Crimes"],
            placeholder="Select crime types",
            style={"width": "70%", "margin-top": "10px", "color": "black"},
        ),
        html.Div(
            [
                dcc.RadioItems(
                    id="metric-toggle",
                    options=[
                        {
                            "label": html.Span(
                                [
                                    html.Strong("Raw Crime Counts"),
                                    html.Span(
                                        " – total number of crimes reported",
                                        style={"fontWeight": "normal"},
                                    ),
                                ]
                            ),
                            "value": "total",
                        },
                        {
                            "label": html.Span(
                                [
                                    html.Strong("Normalised Crime Rate"),
                                    html.Span(
                                        " – crimes per 1,000 people per km²",
                                        style={"fontWeight": "normal"},
                                    ),
                                ]
                            ),
                            "value": "normalised",
                        },
                    ],
                    value="total",
                    labelStyle={
                        "display": "block",
                        "margin-bottom": "5px",
                        "color": "white",
                    },
                )
            ],
            style={"backgroundColor": "#000000", "padding": "10px", "margin-top": "10px"},
        ),
        html.Div(
            [
                dcc.RadioItems(
                    id="rank-toggle",
                    options=[
                        {"label": "Top 10 Highest", "value": "top"},
                        {"label": "Top 10 Lowest", "value": "bottom"},
                    ],
                    value="top",
                    labelStyle={
                        "display": "inline-block",
                        "margin-right": "20px",
                        "color": "white",
                    },
                )
            ],
            style={"backgroundColor": "#000000", "padding": "10px", "margin-top": "10px"},
        ),
        html.Div(
            [
                dcc.Checklist(
                    id="bar-combine-toggle",
                    options=[
                        {
                            "label": "Combine LSOAs by Common Location Name",
                            "value": "combine",
                        }
                    ],
                    value=[],
                    labelStyle={"color": "white"},
                )
            ],
            style={"backgroundColor": "#000000", "padding": "10px", "margin-top": "10px"},
        ),
        dcc.Graph(id="bar-chart"),
    ],
    style={"backgroundColor": "#000000", "padding": "20px"},
)

@app.callback(
    Output("bar-chart", "figure"),
    Input("month-dropdown", "value"),
    Input("metric-toggle", "value"),
    Input("bar-crime-type-dropdown", "value"),
    Input("rank-toggle", "value"),
    Input("bar-combine-toggle", "value"),
)
def update_bar_chart(selected_month, selected_metric, selected_crimes, rank_choice, combine_toggle):
    df = merged_df.copy()
    # Filter by month
    if selected_month != "all":
        df = df[df["Month"] == selected_month]
    # Filter by crime type
    if "All Crimes" not in selected_crimes:
        df = df[df["Crime type"].isin(selected_crimes)]
    # Grouping
    if "combine" in combine_toggle:
        df["Common Location"] = df["LSOA name"].apply(extract_location_name)
        grouped = (
            df.groupby("Common Location")
            .agg(
                {
                    "Crime ID": "count",
                    "Population Density (people per km^2)": "mean",
                }
            )
            .reset_index()
            .rename(columns={"Crime ID": "Total Crimes"})
        )
        y_axis_label = "Common Location"
    else:
        grouped = (
            df.groupby("LSOA name")
            .agg(
                {
                    "Crime ID": "count",
                    "Population Density (people per km^2)": "mean",
                }
            )
            .reset_index()
            .rename(columns={"Crime ID": "Total Crimes"})
        )
        y_axis_label = "LSOA name"
    # Calculate normalised rate
    grouped["Crime Rate (per 1,000 people per km^2)"] = (
        grouped["Total Crimes"] / grouped["Population Density (people per km^2)"] * 1000
    )
    ascending = rank_choice == "bottom"
    y_col = (
        "Total Crimes"
        if selected_metric == "total"
        else "Crime Rate (per 1,000 people per km^2)"
    )
    top_df = grouped.sort_values(by=y_col, ascending=ascending).head(10)
    num_results = len(top_df)
    fig = px.bar(
        top_df,
        x=y_col,
        y=y_axis_label,
        orientation="h",
        title=(
            f"Top {num_results} "
            f"{'Locations' if 'combine' in combine_toggle else 'LSOAs'} "
            f"by {'Total Crimes' if selected_metric=='total' else 'Normalised Crime Rate'} "
            f"– {'All Months' if selected_month=='all' else selected_month} "
            f"({'Lowest' if ascending else 'Highest'})"
        ),
        labels={y_axis_label: y_axis_label, y_col: y_col},
        height=500,
    )
    fig.update_layout(
        yaxis={"autorange": "reversed"},
        plot_bgcolor="#000000",
        paper_bgcolor="#000000",
        font_color="white",
    )
    return fig


# ─── Tab 2: Time Series Explorer ────────────────────────────────────────────────
tab2_layout = html.Div(
    [
        html.H3("Crime Time Series Explorer", style={"color": "white"}),
        dcc.Checklist(
            id="ts-combine-toggle",
            options=[
                {"label": "Combine LSOAs by Common Location Name", "value": "combine"}
            ],
            value=[],
            labelStyle={"color": "white"},
        ),
        dcc.Dropdown(
            id="ts-location-dropdown",
            options=[{"label": loc, "value": loc} for loc in locations],
            value=[locations[0]],
            clearable=False,
            searchable=True,
            multi=True,
            placeholder="Select one or more locations...",
            style={"width": "70%", "margin-top": "10px", "color": "black"},
        ),
        dcc.Dropdown(
            id="ts-crime-dropdown",
            options=crime_type_options,
            value=["All Crimes"],
            clearable=False,
            searchable=True,
            multi=True,
            placeholder="Select one or more crime types...",
            style={"width": "70%", "margin-top": "10px", "color": "black"},
        ),
        dcc.Graph(id="time-series-chart"),
    ],
    style={"backgroundColor": "#000000", "padding": "20px"},
)

@app.callback(
    Output("time-series-chart", "figure"),
    Output("ts-location-dropdown", "options"),
    Output("ts-location-dropdown", "value"),
    Input("ts-combine-toggle", "value"),
    Input("ts-location-dropdown", "value"),
    Input("ts-crime-dropdown", "value"),
)
def update_time_series(combine_toggle, selected_locations, selected_crimes):
    combine = "combine" in combine_toggle
    df = merged_df.copy()
    df["Common Location"] = df["LSOA name"].apply(extract_location_name)

    if combine:
        loc_col = "Common Location"
        loc_list = sorted(df[loc_col].unique())
    else:
        loc_col = "LSOA name"
        loc_list = sorted(df[loc_col].unique())

    location_options = [{"label": loc, "value": loc} for loc in loc_list]
    if not selected_locations or any(loc not in loc_list for loc in selected_locations):
        selected_locations = [loc_list[0]]

    df_filtered = df[df[loc_col].isin(selected_locations)]
    if not selected_crimes or "All Crimes" in selected_crimes:
        grouped = (
            df_filtered.groupby(["Month", loc_col])
            .size()
            .reset_index(name="Crime Count")
        )
        grouped["Crime type"] = "All Crimes"
    else:
        df_filtered = df_filtered[df_filtered["Crime type"].isin(selected_crimes)]
        grouped = (
            df_filtered.groupby(["Month", loc_col, "Crime type"])
            .size()
            .reset_index(name="Crime Count")
        )

    multiple_crime_types = not (
        not selected_crimes
        or len(selected_crimes) == 1
        or "All Crimes" in selected_crimes
    )
    if multiple_crime_types:
        color_arg = "Crime type"
        line_group_arg = loc_col
        hover_name = loc_col
    else:
        color_arg = loc_col
        line_group_arg = "Crime type"
        hover_name = "Crime type"

    fig = px.line(
        grouped,
        x="Month",
        y="Crime Count",
        color=color_arg,
        line_group=line_group_arg,
        hover_name=hover_name,
        title="Crime Counts Over Time",
        markers=True,
    )
    fig.update_layout(
        plot_bgcolor="#000000",
        paper_bgcolor="#000000",
        font_color="white",
        xaxis_title="Month",
        yaxis_title="Crime Count",
    )
    return fig, location_options, selected_locations


# ─── Tab 3: Searchable Folium Map ────────────────────────────────────────────────
tab3_layout = html.Div(
    [
        html.H3("Searchable Map", style={"color": "white"}),
        dcc.Dropdown(
            id="map-location-dropdown",
            options=[{"label": loc, "value": loc} for loc in common_locations],
            value=[],
            multi=True,
            placeholder="Search and select locations...",
            style={"width": "70%", "color": "black"},
        ),
        html.Iframe(id="folium-map", srcDoc=None, width="100%", height="500"),
    ],
    style={"backgroundColor": "#000000", "padding": "20px"},
)

@app.callback(
    Output("folium-map", "srcDoc"),
    Input("map-location-dropdown", "value"),
)
def update_map(selected_locations):
    # Create a Folium Figure for embedding
    fig = Figure(height="500px")
    m = folium.Map(location=[53.5, -1.5], zoom_start=6, scrollWheelZoom=False)
    fig.add_child(m)

    legend_html = """<div style='position: absolute; top: 10px; right: 10px;
        background-color: white; border: 2px solid grey; padding: 10px;
        font-size:14px; z-index:9999;'><b>Location</b><br>"""
    for i, loc in enumerate(selected_locations):
        if loc in coords_dict:
            lat, lon = coords_dict[loc]
            color = color_palette[i % len(color_palette)]
            folium.Marker(
                location=[lat, lon],
                popup=loc,
                tooltip=loc,
                icon=folium.Icon(color=color),
            ).add_to(m)
            legend_html += f"""<div style='display: flex; align-items: center; margin-bottom: 4px;'>
                <div style='background:{color}; width: 16px; height: 6px; margin-right: 6px;'></div>{loc}
            </div>"""

    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    # Render Folium map to HTML string
    html_str = m.get_root().render()
    return html_str


# ─── App Layout with Tabs + Footer Credit ───────────────────────────────────────
app.layout = html.Div(
    [
        html.H2(
            "UK Crime Data Explorer (England, Wales & Northern Ireland, Jan–Mar 2025)",
            style={"textAlign": "center", "color": "white"},
        ),
        dcc.Tabs(
            [
                dcc.Tab(label="Bar Chart", children=[tab1_layout]),
                dcc.Tab(label="Time Series", children=[tab2_layout]),
                dcc.Tab(label="Searchable Map", children=[tab3_layout]),
            ]
        ),
        # ─── Footer credit ────────────────────────────────────────────────────────
        html.Div(
            "Built by Sean Wujiw",
            style={
                "textAlign": "left-align",
                "color": "lightgray",
                "fontSize": "0.8rem",
                "marginTop": "20px",
                "marginBottom": "20px",
            },
        ),
    ],
    style={"backgroundColor": "#000000"},
)

# ─── Run Server ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=8051)