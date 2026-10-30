# Electricity Time-Series Data Pipeline

This formative project explores hourly electricity consumption and production, prepares the data for analysis, stores it in both MySQL and MongoDB, and exposes the stored records through a FastAPI service. It also includes a shared preprocessing pipeline and a one-hour-ahead consumption forecaster.

The dataset covers **2019-01-01 through 2024-03-31**. `Consumption` is the proposed forecasting target. The CSV contains a timestamp, total consumption and production, and generation readings for seven sources.

## Project contents

| Path | Purpose |
| --- | --- |
| `Formative1_TimeSeries_Electricity_Data_Exploration_Preprocessing.ipynb` | Dataset exploration, data-quality checks, analysis, visualizations, and time-series feature engineering. The notebook is written for Google Colab and reads the dataset from Google Drive. |
| `sql/Electricity.csv` | Hourly electricity dataset used by the database loaders. |
| `data/Electricity.csv` | CSV used for offline forecasts and back-tests. |
| `sql/schema.sql` | Creates the MySQL database, normalized tables, source lookup data, and a wide view. |
| `sql/load_data.py` | Cleans and loads the CSV into MySQL. |
| `sql/queries.sql` | Example analytical SQL queries. |
| `mongo/load_mongo.py` | Cleans and loads the CSV into MongoDB. |
| `mongo/queries_mongo.js` | Equivalent example aggregations and queries for MongoDB. |
| `api/` | FastAPI application with corresponding MySQL and MongoDB record endpoints. |
| `src/preprocessing.py` | Shared data cleaning and feature-generation pipeline used for training and serving forecasts. |
| `predict_forecast.py` | Fetches history from the API or a CSV and predicts the next hour's consumption. |
| `models/best_model.joblib` | Trained model bundle used by the forecaster. |
| `tests/test_pipeline_parity.py` | Checks that serving-time features match the training pipeline. |
| `requirements.txt` | Python dependencies for the loaders and API; see below for optional forecasting and test dependencies. |

## Data model

Each observation represents an hourly timestamp. The generation sources are `nuclear`, `wind`, `hydroelectric`, `oil_and_gas`, `coal`, `solar`, and `biomass`.

- **MySQL:** `energy_records` stores timestamp, consumption, and production; `generation` stores one reading per source and timestamp; `energy_sources` identifies each source and its renewable classification. The `v_energy_wide` view pivots source readings into columns.
- **MongoDB:** each `energy_records` document stores timestamp, consumption, production, and a nested `generation` object.

Both loaders remove exact duplicate rows and repeated timestamps (keeping the first occurrence), then sort the records by timestamp. The loaders clear their destination records before loading, so re-running them replaces the existing dataset.

## Requirements

- Python 3.10 or later
- MySQL 8 or later, if using the SQL database or SQL API routes
- MongoDB, if using the document database or MongoDB API routes

Install the Python dependencies from the repository root:

```bash
python -m venv .venv
```

Activate the virtual environment, then install:

```bash
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate it with:

```powershell
.\.venv\Scripts\Activate.ps1
```

The base requirements cover the loaders and API. To run the forecaster or tests, install their additional dependencies:

```bash
python -m pip install requests joblib scikit-learn pytest
```

## Set up MySQL

From the repository root, run `sql/schema.sql` using MySQL Workbench or the MySQL command-line client:

```bash
mysql -u root -p < sql/schema.sql
```

> **Warning:** `schema.sql` drops and recreates the project tables and view. Running it removes existing project data.

Load the CSV from the `sql` directory so the default CSV path resolves:

```bash
cd sql
python load_data.py
cd ..
```

The loader asks for the MySQL password if `MYSQL_PASSWORD` is not set. You can also specify connection options, for example:

```bash
python load_data.py --host localhost --port 3306 --user root --database electricity_db
```

Use `--csv path/to/file.csv` to load a different CSV. The input must have a `DateTime` column and the consumption, production, and seven generation-source columns used by this project.

Run the example SQL analysis from the repository root:

```bash
mysql -u root -p < sql/queries.sql
```

## Set up MongoDB

Start a MongoDB server, then run the loader from the `mongo` directory:

```bash
cd mongo
python load_mongo.py
```

The default connection is `mongodb://localhost:27017`; you can override it and the target database or collection:

```bash
python load_mongo.py --uri "mongodb://localhost:27017" --database electricity_db --collection energy_records
```

The loader deletes all documents in the selected collection before importing and creates a unique ascending index on `timestamp`. To run the examples from the repository root, use MongoDB Compass's mongosh panel or:

```bash
mongosh "mongodb://localhost:27017" mongo/queries_mongo.js
```

## Run the API

Configure database connections with environment variables. Defaults are shown below; set only the values that differ for your local setup. A `.env` file can be used and should not be committed.

| Variable | Default | Description |
| --- | --- | --- |
| `MYSQL_HOST` | `localhost` | MySQL server host |
| `MYSQL_PORT` | `3306` | MySQL server port |
| `MYSQL_USER` | `root` | MySQL user |
| `MYSQL_PASSWORD` | empty | MySQL password |
| `MYSQL_DATABASE` | `electricity_db` | MySQL database |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection URI |
| `MONGO_DATABASE` | `electricity_db` | MongoDB database |
| `MONGO_COLLECTION` | `energy_records` | MongoDB collection |

Start the application from the `api` directory:

```bash
cd api
uvicorn main:app --reload
```

The interactive API documentation is at <http://127.0.0.1:8000/docs>. The root route provides a basic status message, and `/health` checks connectivity to both databases.

### API routes

The MySQL and MongoDB routes provide the same operations under separate prefixes:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/sql/records` or `/mongo/records` | List records with `limit` and `offset` pagination. |
| `GET` | `/sql/records/latest` or `/mongo/records/latest` | Get the most recent record. |
| `GET` | `/sql/records/range` or `/mongo/records/range` | Filter records by required `start` and `end` timestamps; supports pagination. |
| `GET` | `/sql/records/{record_id}` or `/mongo/records/{record_id}` | Get one record. |
| `POST` | `/sql/records` or `/mongo/records` | Create a record. |
| `PUT` | `/sql/records/{record_id}` or `/mongo/records/{record_id}` | Update the supplied fields. |
| `DELETE` | `/sql/records/{record_id}` or `/mongo/records/{record_id}` | Delete a record. |

Records use this JSON shape; all seven generation values are required when creating a record:

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

The MySQL API returns an integer record ID; MongoDB returns a string ObjectId. Timestamp values are stored as naive UTC datetimes.

## Forecast next-hour consumption

The forecaster uses the shared cleaning and feature pipeline in `src/preprocessing.py` and the model bundle in `models/best_model.joblib`. It predicts one hour after the latest available record (or after the timestamp supplied with `--as-of`). At least 168 hours of usable history are needed; the script looks back 192 hours to allow for gaps. This is a one-hour-ahead forecast, not a long-range forecast.

For an offline forecast using the included CSV:

```bash
python predict_forecast.py --csv data/Electricity.csv
```

For an offline back-test at a specific time, the command also reports the actual next-hour value when it exists in the CSV:

```bash
python predict_forecast.py --csv data/Electricity.csv --as-of "2024-03-31 22:00"
```

To forecast using data served by the API, start the API and use one of its database backends:

```bash
python predict_forecast.py --api http://localhost:8000 --source sql
python predict_forecast.py --api http://localhost:8000 --source mongo
```

The forecast script's `RANGE_PATH` setting must match the API's date-range route. In this repository, set it to `"/{source}/records/range"` (the API routes are documented above); the script currently defaults to the collection-list route, which does not apply the requested `start` and `end` parameters. The API can also be pointed at another model bundle with `--model path/to/model.joblib`.

The notebook trains and saves a model bundle containing the estimator and its expected feature-column order. When retraining, put the resulting `best_model.joblib` in `models/` or pass its path with `--model`. The predictor uses the stored feature order to keep training and inference inputs aligned.

## Run tests

From the repository root, run the focused training/serving parity tests:

```bash
python -m pytest tests/
```

These tests verify that next-hour features generated from a recent history window match the training pipeline and that insufficient history is rejected.

## Notebook

The exploration notebook is configured for Google Colab and includes a Google Drive mount step. To run it in Colab, upload or place the CSV in the Drive location referenced by the notebook, then execute its cells in order. The same dataset is included locally at `sql/Electricity.csv`.

## Notes

- The renewable classification in `sql/schema.sql` is an explicit project assumption: wind, hydroelectric, solar, and biomass are marked renewable.
- SQL and MongoDB example analyses are in `sql/queries.sql` and `mongo/queries_mongo.js`, respectively.
- The API serves whichever database backend is selected by its route prefix; it does not copy data between MySQL and MongoDB.
