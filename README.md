# UK Crime Dashboard

This repository contains a Dash-based interactive web application for exploring crime data across England, Wales, and Northern Ireland (January–March 2025). The app provides:

* A **Bar Chart** dashboard of top/bottom LSOA or Common Locations by crime count or normalized rate.
* A **Time Series Explorer** showing monthly crime trends for selected locations and crime types.
* A **Searchable Folium Map** displaying location markers on an interactive map.

## Prerequisites

* Python 3.8 or higher
* `pip` installed
* The `crime_data_merged.csv` file (181 MB) placed in the root directory of this project.

## Installing Dependencies

1. (Optional) Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate      # macOS/Linux
   venv\Scripts\activate       # Windows
   ```

2. Install Python packages:

   ```bash
   pip install -r requirements.txt
   ```

   If you don’t have a `requirements.txt`, install manually:

   ```bash
   pip install dash dash-bootstrap-components plotly pandas folium branca
   ```

## Running the App

1. Ensure `crime_data_merged.csv` is in the same directory as `crime_dashboard.py`.
2. Start the Dash server:

   ```bash
   python crime_dashboard.py
   ```
3. Open your browser to:
   [http://127.0.0.1:8050/](http://127.0.0.1:8050/)

## Project Structure

```
├── crime_dashboard.py    # Main Dash application
├── crime_data_merged.csv # Data file (must be present locally)
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

## Troubleshooting

* **Missing CSV**: You will see a `FileNotFoundError`. Make sure `crime_data_merged.csv` is in the project root.
* **Port in use**: Use a different port:

  ```bash
  python crime_dashboard.py --port 8060
  ```
* **Memory issues**: If the 181 MB CSV is too large, consider converting it to Parquet:

  ```python
  df = pd.read_csv("crime_data_merged.csv")
  df.to_parquet("crime_data_merged.parquet")
  ```

  and then load with `pd.read_parquet("crime_data_merged.parquet")`.

## License & Acknowledgments

This project was developed for academic coursework. Data provided by UK Police data and ONS population datasets.
