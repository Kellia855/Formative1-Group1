# Electricity Time-Series Data Pipeline

## About the project

This group project works with hourly electricity data from **1 January 2019 to 31 March 2024**. We explore how electricity consumption and production change over time, prepare the data for analysis and forecasting, store the records in both MySQL and MongoDB, and make the stored data available through a FastAPI service.

Our forecasting task is to predict **electricity consumption one hour ahead**. We use past consumption, recent generation readings, and time-based features to make that prediction.

The dataset was selected because it contains several years of hourly observations. This makes it useful for exploring daily and weekly patterns, changes in electricity demand, and the relationship between consumption and different sources of electricity generation.

## What is included

| File or folder | What it is used for |
|---|---|
| `Formative1_TimeSeries_Electricity_Data_Exploration_Preprocessing (1).ipynb` | Main Google Colab notebook for dataset understanding, data-quality checks, analytical questions, visualisations, preprocessing, feature engineering, model experiments, and model saving. |
| `data/Electricity.csv` | Original dataset used by the offline forecasting script. |
| `data/Electricity_cleaned.csv` | Cleaned hourly dataset produced during exploration and preprocessing. |
| `sql/Electricity.csv` | Copy of the original dataset used by the MySQL loader. |
| `sql/schema.sql` | Creates the MySQL database, its three tables, and the `v_energy_wide` view. |
| `sql/load_data.py` | Prepares the CSV and loads the records into MySQL. |
| `sql/queries.sql` | Example analytical SQL queries. |
| `mongo/load_mongo.py` | Prepares the CSV and loads the records into MongoDB. |
| `mongo/queries_mongo.js` | Example MongoDB queries and aggregations. |
| `api/` | FastAPI application, database connections, request schemas, and SQL/MongoDB routes. |
| `src/preprocessing.py` | Shared cleaning and feature-engineering functions used by the forecasting script. |
| `models/best_model.joblib` | Trained model bundle used to produce forecasts. |
| `predict_forecast.py` | Predicts the next hour's electricity consumption from a CSV or the API. |
| `tests/test_pipeline_parity.py` | Tests that the features created for prediction match the training feature pipeline. |
| `requirements.txt` | Python packages needed for the loaders, API, forecasting script, and tests. |

## Dataset and forecasting problem

Each row represents an hourly observation. The dataset contains:

- `DateTime`: observation timestamp
- `Consumption`: total electricity consumption and the target we want to predict
- `Production`: total electricity production
- Seven generation readings: nuclear, wind, hydroelectric, oil and gas, coal, solar, and biomass

The forecasting script predicts the consumption value for the hour immediately after the latest available observation. This is a **one-hour-ahead forecast**, not a long-term forecast.

## Data preparation and features

The notebook examines the original data before preparing it for analysis and modelling. It checks timestamps, duplicate records, missing hours, missing values, negative generation readings, and numerical distributions.

The notebook's preprocessing pipeline and the database loaders have different purposes, so their cleaning rules are not identical:

- **Notebook and forecasting pipeline:** removes exact duplicate rows, averages records that share a timestamp, clips negative generation readings to zero, creates a regular hourly index, and interpolates short internal gaps of up to six hours. It then creates forecasting features. Rows that still have incomplete features are excluded from the modelling dataset.
- **MySQL and MongoDB loaders:** remove exact duplicate rows, keep the first row when timestamps repeat, and sort the remaining records by timestamp. They do not run the notebook's interpolation and feature-engineering steps.

The forecasting features include previous consumption values (lags of 1, 2, 3, 24, 48, and 168 hours), rolling means and standard deviations over 24- and 168-hour windows, previous-hour generation readings, and calendar features such as hour, day of week, month, and cyclical time encodings.

Rolling statistics are shifted so that the current target value is not included in its own input features. The notebook also uses chronological training, validation, and test periods to respect the time order of the data.

## Set up the project

### Requirements

- Python **3.10 or later**
- MySQL **8 or later** for the SQL database and SQL API routes
- A running MongoDB server for the MongoDB loader and MongoDB API routes

Create and activate a virtual environment from the repository root.

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

The scikit-learn version is pinned to `1.6.1` to match the version used to save the committed model bundle. When loading a saved scikit-learn model, using a different scikit-learn version can cause compatibility warnings or errors.

## MySQL setup

From the repository root, create the database and tables:

```bash
mysql -u root -p < sql/schema.sql
```

> **Important:** `sql/schema.sql` drops and recreates the project's tables and view. Running it again removes the existing project records in those tables.

Load the dataset. The loader's default CSV path is relative to the `sql` folder, so run it from there:

```bash
cd sql
python load_data.py
cd ..
```

The script asks for your MySQL password if `MYSQL_PASSWORD` is not set. You can also provide connection details:

```bash
python load_data.py --host localhost --port 3306 --user root --database electricity_db
```

To use another CSV, provide its path with `--csv`.

Run the example SQL queries from the repository root:

```bash
mysql -u root -p < sql/queries.sql
```

The MySQL design uses three tables:

- `energy_records` stores one row per timestamp, including consumption and production.
- `energy_sources` stores the seven generation-source names and their renewable classification.
- `generation` stores the output for each source and timestamp.

The `v_energy_wide` view brings the generation readings back into one row per timestamp.

## MongoDB setup

Start your MongoDB server. From the repository root, run the loader with the CSV path supplied explicitly:

```bash
cd mongo
python load_mongo.py --csv ../sql/Electricity.csv
cd ..
```

The default MongoDB connection is `mongodb://localhost:27017`. You can change the URI, database, and collection:

```bash
cd mongo
python load_mongo.py --csv ../sql/Electricity.csv --uri "mongodb://localhost:27017" --database electricity_db --collection energy_records
cd ..
```

Each MongoDB document contains a timestamp, consumption, production, and a nested `generation` object with the seven source readings. The loader clears the selected collection before importing and creates a unique ascending index on `timestamp`.

To run the example MongoDB queries from the repository root, use MongoDB Compass's mongosh panel or:

```bash
mongosh "mongodb://localhost:27017" mongo/queries_mongo.js
```

**Please note:** both database loaders replace the records in their destination when they are run. Do not run them against a collection or database containing records you need to keep.

## Run the API

The API reads connection settings from environment variables. The defaults are listed below. You can set these in your terminal or in a local `.env` file in the `api` folder. Do not commit passwords or other secrets to GitHub.

| Variable | Default | Purpose |
|---|---|---|
| `MYSQL_HOST` | `localhost` | MySQL server |
| `MYSQL_PORT` | `3306` | MySQL port |
| `MYSQL_USER` | `root` | MySQL username |
| `MYSQL_PASSWORD` | empty | MySQL password |
| `MYSQL_DATABASE` | `electricity_db` | MySQL database |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection |
| `MONGO_DATABASE` | `electricity_db` | MongoDB database |
| `MONGO_COLLECTION` | `energy_records` | MongoDB collection |

Make sure the database you want to use has been set up and loaded. Start the API from the `api` folder:

```bash
cd api
uvicorn main:app --reload
```

Open the interactive API documentation at:

<http://127.0.0.1:8000/docs>

The root endpoint displays a basic status message. The `/health` endpoint checks connectivity to MySQL and MongoDB.

### Available API endpoints

The API provides equivalent operations for both databases. Use the `/sql` prefix for MySQL and `/mongo` for MongoDB.

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/sql/records` or `/mongo/records` | Lists records with pagination using `limit` and `offset`. |
| `GET` | `/sql/records/latest` or `/mongo/records/latest` | Returns the most recent record. |
| `GET` | `/sql/records/range` or `/mongo/records/range` | Returns records between the required `start` and `end` timestamps. Pagination is also supported. |
| `GET` | `/sql/records/{record_id}` or `/mongo/records/{record_id}` | Returns one record by its ID. |
| `POST` | `/sql/records` or `/mongo/records` | Creates a record. |
| `PUT` | `/sql/records/{record_id}` or `/mongo/records/{record_id}` | Updates the supplied fields. |
| `DELETE` | `/sql/records/{record_id}` or `/mongo/records/{record_id}` | Deletes a record. |

When creating a record, provide the timestamp, consumption, production, and all seven generation values. For example:

```json
{
  "timestamp": "2023-01-01T00:00:00",
  "consumption": 6352,
  "production": 6527,
  "generation": {
    "nuclear": 1395,
    "wind": 79,
    "hydroelectric": 1383,
    "oil_and_gas": 1896,
    "coal": 1744,
    "solar": 0,
    "biomass": 30
  }
}
```

MySQL records have integer IDs, while MongoDB records use string ObjectIds. The API normalises timezone-aware timestamps to naive UTC datetimes before storing them.

## Forecast the next hour

The forecasting script uses the shared functions in `src/preprocessing.py`, so it creates prediction features in the same way as the notebook. It loads the trained model and its expected feature-column order from `models/best_model.joblib`.

The model needs at least 168 hours of usable history. The script requests a 192-hour window to leave some room for missing hours and cleaning. If there is not enough usable history, or a long gap prevents the required features from being created, the script reports an error rather than making a prediction from incomplete inputs.

### Option 1: Forecast from the CSV

Run this command from the repository root:

```bash
python predict_forecast.py --csv data/Electricity.csv
```

To test a past forecast and compare it with the actual next-hour value (when that value exists in the CSV), use:

```bash
python predict_forecast.py --csv data/Electricity.csv --as-of "2024-03-31 22:00"
```

### Option 2: Forecast using the API

First, start the API and make sure the relevant database is running and contains the electricity records. Then, from a second terminal in the repository root, run:

```bash
python predict_forecast.py --api http://localhost:8000 --source sql
```

Or use MongoDB:

```bash
python predict_forecast.py --api http://localhost:8000 --source mongo
```

The script gets the latest timestamp and then requests the required history from the API's date-range endpoint. You can supply a different model bundle with `--model path/to/model.joblib`.

### Example forecast run

The offline command was tested against the included CSV and model bundle using:

```bash
python predict_forecast.py --csv data/Electricity.csv --as-of "2024-03-31 22:00"
```

It produced a forecast for `2024-03-31 23:00`:

| Output | Value |
|---|---:|
| Last observed consumption | 5,527 |
| Predicted consumption | 5,171.4 |
| Actual consumption | 5,111 |
| Absolute error | 60.4 |

This is an example back-test from one timestamp. It should not be treated as a summary of the model's overall performance.

## Run the tests

From the repository root:

```bash
python -m pytest tests/ -q
```

The current test suite checks that the features generated for a next-hour prediction match the training pipeline and that the script rejects a history window that is too short.

## Run the notebook

The main exploration notebook is designed for Google Colab and includes a Google Drive mount step. Upload the notebook to Colab, place the dataset in the Drive location expected by the notebook, and run the cells in order.

The original dataset is also included in the repository at `data/Electricity.csv` and `sql/Electricity.csv`. The cleaned dataset produced during preprocessing is stored at `data/Electricity_cleaned.csv`.

## Notes and assumptions

- The renewable classification in `sql/schema.sql` is a project assumption: wind, hydroelectric, solar, and biomass are marked as renewable.
- The notebook's cleaning approach is designed for exploration and forecasting. The database loaders use a simpler rule for repeated timestamps so that each stored timestamp is unique.
- The API exposes whichever database is selected by the endpoint prefix. It does not copy or synchronise records between MySQL and MongoDB.
- The loaders clear the destination records before importing. Use them only when replacing the existing project dataset is intended.
- The forecast is for the next hour only. Its usefulness should be judged using the model evaluation in the notebook as well as individual example predictions.
