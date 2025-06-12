from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import re
import folium
from folium import Icon, Marker
from folium.plugins import MarkerCluster
from branca.element import Figure

#### Load data ####

# Read the merged crime dataset (AWS S3 stored CSV). This contains all crime incidents
# for January–March 2025 across England, Wales, and Northern Ireland, joined with population/area data.
# The csv being read was created in Jupyter Notebooks after cleaning and merging each crime and population data csv file
merged_df = pd.read_csv("crime_data_merged.csv")



##### Define a helper function to normalize LSOA names by stripping trailing codes. ####

# Example: "Westminster 001A" → "Westminster". This is to group multiple LSOAs that share a common prefix.
#regex library helps removing the code at the end
def extract_location_name(lsoa_name):
    return re.sub(r"\s\d+[A-Z]*$", "", lsoa_name)

# Create a new column “Common Location” by applying the helper function above to add to the data frame.
# This aggregates multiple LSOAs under one broader “location” label for the user
merged_df["Common Location"] = merged_df["LSOA name"].apply(extract_location_name)




#### Prepare dropdown options for "month", "crime type", and "locations" ####

#1 Month dropdown: collect unique months from the dataset, sort them, and add an “All Months” option at the front.
months = sorted(merged_df["Month"].unique())                                     #grab unique months string and sort them
month_options = [{"label": m, "value": m} for m in months]                       #list comprehension to turn each month into key-value pairs (needed for dash callbacks)
month_options.insert(0, {"label": "All Months", "value": "all"}) #add an option for the user to look at all months instead of just one

#2 Crime-type dropdown: collect unique crime categories, sort them, and prepend an “All Crimes” choice.
crime_types = sorted(merged_df["Crime type"].unique())                          #grab unique crime type string and sort them
crime_type_options = [{"label": "All Crimes", "value": "All Crimes"}] + [
    {"label": ct, "value": ct} for ct in crime_types
]                                                                               #list comprehension to turn each crime type into key-value pairs (needed for dash callbacks)

#3 Location lists: one for full LSOA names, another for the simplified “Common Location” names.
locations = sorted(merged_df["LSOA name"].unique())                              #grab unique LSOA string and sort them
common_locations = sorted(merged_df["Common Location"].unique())                 #grab unique location string and sort them




#### Compute average latitude/longitude for each Common Location ####

# For plotting markers on Folium map, so each “Common Location” gets one pin at its centroid.
location_coords = (
    merged_df
    .groupby("Common Location")[["Latitude", "Longitude"]]  #clusters all rows by location name column
    .mean()                                                 #takes avg. latitude and longitude for each location giving a single centroid per location
    .dropna()                                               #remove locations with missing coordinates
    .reset_index()                                          #turn location index back into normal data frame to iterate more easily
)
# Build a lookup dictionary { Common Location → (lat, lon) } for quick access in the map callback.
coords_dict = {
    row["Common Location"]: (row["Latitude"], row["Longitude"])
    for _, row in location_coords.iterrows()
}                                                           #list comprehension creating key-value pairs

# Define a palette of distinct colors for mapping up to ~18 locations.
# Cycle through these when rendering markers so each selected location has its own color.
color_palette = [
    "red", "blue", "green", "purple", "orange", "darkred", "lightred", "beige",
    "darkblue", "darkgreen", "cadetblue", "darkpurple", "pink", "lightblue",
    "lightgreen", "gray", "black", "lightgray"
]




##### Initialize the Dash app with a Bootstrap theme ####

#initialize new app
#stylesheets parameter points to CSS framework for using bootstraps buttons, controls etc.
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

#title in HTML head (window title)
app.title = "UK Crime Dashboard"

# Expose the Flask “server” for deployment on Render (or other platforms)
server = app.server    #Dash uses Flask under the hood, this makes flask instance deployable. PaaS providers look for WSGI "server" object to hook into for deployment




#### Tab 1: Bar Chart Dashboard Layout ####

# The bar chart tab allows filtering by month and crime type, toggling between raw counts
# vs. normalized crime rate, and ranking the Top/Bottom 10 LSOAs (or aggregated “Common Locations”).
tab1_layout = html.Div(
    [
        # Title
        html.H3("Bar Chart Dashboard", style={"color": "white"}), #title, with white color to match dark theme

        ####Build Dropdowns####
        # Dropdown to select a month (or “All Months”)
        dcc.Dropdown(
            id="month-dropdown",    #unique identifier to hook dash callbacks to it
            options=month_options,  #supplies list of month key-value options defined above
            value="all",            # default: show all months
            clearable=False,        # user cannot clear, must choose one option
            style={"width": "50%", "color": "black"}, #defines inline CSS so dropdown is half width and shows black text on white background
        ),

        # Dropdown to select one or more crime types (or “All Crimes”)
        dcc.Dropdown(
            id="bar-crime-type-dropdown",   #unique identifier to hook dash callbacks to it
            options=crime_type_options,     #supplies list of crime type key-value options defined above
            multi=True,                     # allow selecting multiple crime types
            value=["All Crimes"],           # default: “All Crimes”
            placeholder="Select crime types", #hint to the user if the dropdown is empty
            style={"width": "70%", "margin-top": "10px", "color": "black"}, #inline CSS again
        ),

        ####Build Radio buttons####
        # RadioItems to toggle between “Raw Crime Counts” and “Normalised Crime Rate”
        html.Div(
            [
                dcc.RadioItems(
                    id="metric-toggle", #indentifier for callback to listen for to know which metric to display
                    options=[ #choice between two labels (absolute crime or normalised)
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
                    value="total",  # default: show raw counts
                    labelStyle={
                        "display": "block",
                        "margin-bottom": "5px",
                        "color": "white",
                    },
                )
            ],
            style={"backgroundColor": "#000000", "padding": "10px", "margin-top": "10px"}, #dark background with padding
        ),

        # RadioItems to choose Top 10 Highest or Top 10 Lowest
        html.Div(
            [
                dcc.RadioItems(
                    id="rank-toggle", #identifier for callbacks
                    options=[
                        {"label": "Top 10 Highest", "value": "top"},
                        {"label": "Top 10 Lowest", "value": "bottom"},
                    ],
                    value="top",  # default: Top 10 Highest
                    labelStyle={
                        "display": "inline-block",
                        "margin-right": "20px",
                        "color": "white",
                    },
                )
            ],
            style={"backgroundColor": "#000000", "padding": "10px", "margin-top": "10px"},
        ),

        ####Build Checklist####
        # Checklist to optionally “Combine LSOAs by Common Location Name”
        # When checked, aggregate by stripped-down location (e.g., all “Westminster” LSOAs become one group).
        html.Div(
            [
                dcc.Checklist(
                    id="bar-combine-toggle", #identifier for callbacks
                    options=[
                        {
                            "label": "Combine LSOAs by Common Location Name",
                            "value": "combine",
                        }
                    ],
                    value=[],  # default: don’t combine, show individual LSOAs
                    labelStyle={"color": "white"},
                )
            ],
            style={"backgroundColor": "#000000", "padding": "10px", "margin-top": "10px"},
        ),

        # The actual bar chart (Plotly) will render here via callback.
        dcc.Graph(id="bar-chart"),
    ],
    style={"backgroundColor": "#000000", "padding": "20px"},
)





##### Callback for Tab 1: Update Bar Chart ####

#This decorator is wiring up the bar chart so that any change to one of the controls by the user will automatically re-render the chart
@app.callback(
    #targets id= "bar-chart" above anf updates its "figure" (the plotly figure that renders the bars).
    Output("bar-chart", "figure"),

    #when the user interacts with any of these controls, dash collects the current 5 values, passes them
    #into the callback function, then updates the plotly chart on screen
    Input("month-dropdown", "value"),
    Input("metric-toggle", "value"),
    Input("bar-crime-type-dropdown", "value"),
    Input("rank-toggle", "value"),
    Input("bar-combine-toggle", "value"),
)
#Create call back function inside decorator
def update_bar_chart(selected_month, selected_metric, selected_crimes, rank_choice, combine_toggle):
    # Make a copy of merged_df so we don’t modify the original in-place
    df = merged_df.copy()

    #1 Filter by month if not “all”
    if selected_month != "all":
        df = df[df["Month"] == selected_month]

    #2 Filter by crime type if not “All Crimes”
    if "All Crimes" not in selected_crimes:
        df = df[df["Crime type"].isin(selected_crimes)]

    #3 Decide grouping: either by “Common Location” or by full “LSOA name”
    #This determines the Y-Axis title for the bar chart
    if "combine" in combine_toggle:
        # Recompute “Common Location” on the filtered subset (in case underlying df changed)
        df["Common Location"] = df["LSOA name"].apply(extract_location_name)
        grouped = (
            df.groupby("Common Location")
            .agg({
                "Crime ID": "count",                               # count incidents
                "Population Density (people per km^2)": "mean",     # average pop density across that group
            })
            .reset_index()
            .rename(columns={"Crime ID": "Total Crimes"})          # rename for clarity
        )
        y_axis_label = "Common Location"
    else:
        grouped = (
            df.groupby("LSOA name")
            .agg({
                "Crime ID": "count",
                "Population Density (people per km^2)": "mean",
            })
            .reset_index()
            .rename(columns={"Crime ID": "Total Crimes"})
        )
        y_axis_label = "LSOA name"

    #4 Compute normalised crime rate (if user selects that option)
    #(Total Crimes) ÷ (Population Density per km^2) × 1000
    grouped["Crime Rate (per 1,000 people per km^2)"] = (
        grouped["Total Crimes"] / grouped["Population Density (people per km^2)"] * 1000
    )

    #5 Determine sorting order (Top 10 Highest vs. Top 10 Lowest)
    ascending = (rank_choice == "bottom")

    #6 Pick which metric to plot on x‐axis
    y_col = (
        "Total Crimes"
        if selected_metric == "total"
        else "Crime Rate (per 1,000 people per km^2)"
    )

    #7 Sort by chosen metric and take top 10 (or bottom 10, depending on ascending flag)
    top_df = grouped.sort_values(by=y_col, ascending=ascending).head(10)
    num_results = len(top_df)

    #8 Build a horizontal bar chart with Plotly Express
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
    # Reverse the y-axis so highest values appear on top
    fig.update_layout(
        yaxis={"autorange": "reversed"},
        plot_bgcolor="#000000",   # dark background behind bars
        paper_bgcolor="#000000",  # dark background around entire plot
        font_color="white",       # white text on dark background
    )

    return fig




#### Tab 2: Time Series Explorer Layout ####
# This tab shows how crime counts change over time for selected locations and crime types.
tab2_layout = html.Div(
    [
        html.H3("Crime Time Series Explorer", style={"color": "white"}),

        # Allow grouping by “Common Location” across multiple LSOAs
        dcc.Checklist(
            id="ts-combine-toggle",
            options=[{"label": "Combine LSOAs by Common Location Name", "value": "combine"}],
            value=[],  # default: show individual LSOAs
            labelStyle={"color": "white"},
        ),

        # Multi‐select dropdown for location(s). If “combine” is checked, the options below
        # will update to “Common Location” names; otherwise they remain full LSOA names.
        dcc.Dropdown(
            id="ts-location-dropdown",
            options=[{"label": loc, "value": loc} for loc in locations],
            value=[locations[0]],    # default: select the first LSOA in sorted list
            clearable=False,
            searchable=True,
            multi=True,
            placeholder="Select one or more locations...",
            style={"width": "70%", "margin-top": "10px", "color": "black"},
        ),

        # Multi‐select dropdown for crime type(s), with “All Crimes” as default
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

        # The line chart will render here via callback
        dcc.Graph(id="time-series-chart"),
    ],
    style={"backgroundColor": "#000000", "padding": "20px"},
)




#### Callback for Tab 2: Update Time Series Chart ####
@app.callback(
    Output("time-series-chart", "figure"),
    Output("ts-location-dropdown", "options"),
    Output("ts-location-dropdown", "value"),
    Input("ts-combine-toggle", "value"),
    Input("ts-location-dropdown", "value"),
    Input("ts-crime-dropdown", "value"),
)
def update_time_series(combine_toggle, selected_locations, selected_crimes):
    # Check if user wants “combine” (i.e. aggregate by “Common Location”)
    combine = ("combine" in combine_toggle)

    # Work on a copy of merged_df so original is not modified
    df = merged_df.copy()
    df["Common Location"] = df["LSOA name"].apply(extract_location_name)

    # Determine which column to filter on (Common Location vs. full LSOA name)
    if combine:
        loc_col = "Common Location"
        loc_list = sorted(df[loc_col].unique())
    else:
        loc_col = "LSOA name"
        loc_list = sorted(df[loc_col].unique())

    # Build a fresh set of options for the location‐dropdown
    location_options = [{"label": loc, "value": loc} for loc in loc_list]

    # If current selected_locations is empty or contains invalid entries, reset to first item
    if not selected_locations or any(loc not in loc_list for loc in selected_locations):
        selected_locations = [loc_list[0]]

    # Filter the data down to the chosen locations
    df_filtered = df[df[loc_col].isin(selected_locations)]

    # Now, handle crime‐type filtering
    if (not selected_crimes) or ("All Crimes" in selected_crimes):
        # If “All Crimes” chosen (or none), group by Month + location and count incidents
        grouped = (
            df_filtered.groupby(["Month", loc_col])
            .size()
            .reset_index(name="Crime Count")
        )
        grouped["Crime type"] = "All Crimes"  # add a dummy column so Plotly has something consistent to plot
    else:
        # Otherwise filter by the chosen crime types and get counts by month, location, crime type
        df_filtered = df_filtered[df_filtered["Crime type"].isin(selected_crimes)]
        grouped = (
            df_filtered.groupby(["Month", loc_col, "Crime type"])
            .size()
            .reset_index(name="Crime Count")
        )

    # Decide how to color the lines:
    # If user selected multiple crime types (not “All Crimes”), color by crime type and group by location
    multiple_crime_types = not (
        (not selected_crimes)
        or (len(selected_crimes) == 1)
        or ("All Crimes" in selected_crimes)
    )
    if multiple_crime_types:
        color_arg = "Crime type"
        line_group_arg = loc_col
        hover_name = loc_col
    else:
        # Otherwise color by location and group by “Crime type” (all will be “All Crimes” if only that was chosen)
        color_arg = loc_col
        line_group_arg = "Crime type"
        hover_name = "Crime type"

    # Build the line chart
    fig = px.line(
        grouped,
        x="Month",
        y="Crime Count",
        color=color_arg,
        line_group=line_group_arg,
        hover_name=hover_name,
        title="Crime Counts Over Time",
        markers=True,  # show markers at each monthly point
    )
    # Style the background and fonts to match the dashboard’s dark theme
    fig.update_layout(
        plot_bgcolor="#000000",
        paper_bgcolor="#000000",
        font_color="white",
        xaxis_title="Month",
        yaxis_title="Crime Count",
    )

    # Return figure plus updated options/value for the location‐dropdown (to handle “combine” toggling)
    return fig, location_options, selected_locations




#### Tab 3: Searchable Folium Map ####
# This tab renders an embedded Folium map inside an <iframe>. The user can search multiple
# “Common Location” names and display pins (markers) for each with a color‐coded legend.
tab3_layout = html.Div(
    [
        html.H3("Searchable Map", style={"color": "white"}),

        # Dropdown where users can type or select multiple “Common Location” names
        dcc.Dropdown(
            id="map-location-dropdown",
            options=[{"label": loc, "value": loc} for loc in common_locations],
            value=[],       # no selection by default
            multi=True,     # allow multiple locations
            placeholder="Search and select locations...",
            style={"width": "70%", "color": "black"},
        ),

        # An <iframe> whose srcDoc will be filled with the rendered HTML of our Folium map
        html.Iframe(id="folium-map", srcDoc=None, width="100%", height="500"),
    ],
    style={"backgroundColor": "#000000", "padding": "20px"},
)

##### Callback for Tab 3: Update Folium Map ####
@app.callback(
    Output("folium-map", "srcDoc"),
    Input("map-location-dropdown", "value"),
)
def update_map(selected_locations):
    # Create a Folium Figure wrapper so we can explicitly set its height (prevents extra whitespace).
    fig = Figure(height="500px")

    # Initialize the base map, centered roughly in Britain with zoom=6
    # scrollWheelZoom=False prevents accidental zoom when scrolling the page
    m = folium.Map(location=[53.5, -1.5], zoom_start=6, scrollWheelZoom=False)
    fig.add_child(m)

    # Build an HTML legend (a floating <div> in the map) listing each selected location + its color swatch
    legend_html = """<div style='position: absolute; top: 10px; right: 10px;
        background-color: white; border: 2px solid grey; padding: 10px;
        font-size:14px; z-index:9999;'><b>Location</b><br>"""

    # For each chosen location, look up its (lat, lon), pick a color, and add a Marker to the map
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
            # Add a line to the legend HTML for this color/label
            legend_html += f"""<div style='display: flex; align-items: center; margin-bottom: 4px;'>
                <div style='background:{color}; width: 16px; height: 6px; margin-right: 6px;'></div>{loc}
            </div>"""

    legend_html += "</div>"
    # Inject that legend <div> into the map’s root HTML
    m.get_root().html.add_child(folium.Element(legend_html))

    # Finally, render the complete Folium map to an HTML string and return it, so the <iframe> displays it
    html_str = m.get_root().render()
    return html_str





#### Combine all tabs into the main app layout ####
app.layout = html.Div(
    [
        # Page title/header
        html.H2(
            "UK Crime Data Explorer (England, Wales & Northern Ireland, Jan–Mar 2025)",
            style={"textAlign": "center", "color": "white"},
        ),

        # The three tabs: Bar Chart, Time Series, Searchable Map
        dcc.Tabs(
            [
                dcc.Tab(label="Bar Chart",    children=[tab1_layout]),
                dcc.Tab(label="Time Series",  children=[tab2_layout]),
                dcc.Tab(label="Searchable Map",children=[tab3_layout]),
            ]
        ),
    ],
    style={"backgroundColor": "#000000"},  # dark background around the entire app
)




#### Run the Dash development server on port 8050 ####
if __name__ == "__main__":
    app.run(debug=True, port=8050)
