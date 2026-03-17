# Sales Profit Analyzer (Streamlit + SQLite)

A Streamlit-based small business analytics app for tracking sales, expenses, products, and reports.

## Tech Stack

- Python 3.11
- Streamlit
- SQLite (`sales_profit_analyzer.db`)
- Docker

## Project Structure

- `app.py` — Main Streamlit application
- `db.py` — SQLite connection + schema initialization logic
- `init_db.py` — Runs database/table initialization at startup
- `requirements.txt` — Python dependencies
- `Dockerfile` — Container config for deployment

## Database

This project uses SQLite (file-based DB), which is compatible with Hugging Face Spaces Docker deployment.

- Database file: `sales_profit_analyzer.db`
- Tables are auto-created on app startup via `init_db.py`

## Run Locally

### 1) Create and activate virtual environment

**Windows PowerShell**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Start Streamlit app

```bash
streamlit run app.py
```

The app will open at:

- `http://localhost:8501`

## Run with Docker

### Build image

```bash
docker build -t sales-profit-analyzer .
```

### Run container

```bash
docker run -p 8501:8501 sales-profit-analyzer
```

## Deploy to Hugging Face Spaces (Docker)

1. Create a new **Space** and choose **Docker** SDK.
2. Push project files (including `Dockerfile`, `app.py`, `db.py`, `init_db.py`, `requirements.txt`).
3. Hugging Face builds and runs the container automatically.
4. Streamlit is exposed on port `8501` (already configured in `Dockerfile`).

## Notes

- `.gitignore` excludes `sales_profit_analyzer.db` and cache files so local DB data is not committed.
- Since SQLite is local file storage, data is ephemeral unless you configure persistent storage in your deployment environment.
