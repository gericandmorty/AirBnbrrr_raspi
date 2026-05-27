# AirBnBrrr: AI-Powered HVAC IoT Monitoring System

AirBnBrrr is an end-to-end IoT monitoring and proactive fault detection system designed specifically for Window-Type Air Conditioners. It ingests real-time telemetry from a Raspberry Pi sensor array and processes the data through a FastAPI backend to detect anomalies, generate explainable reports, and dispatch automated SMS alerts.

## Key Features

*   **IoT Telemetry Ingestion**: Receives real-time data from a custom Raspberry Pi sensor suite, including temperature, humidity, vibration, power consumption, voltage, and dust levels.
*   **Hybrid Diagnostic Pipeline**: A robust, three-layer approach to anomaly detection:
    1.  **Machine Learning (Isolation Forest)**: Analyzes historical data to detect statistical outliers in sensor readings.
    2.  **Deterministic Rule Engine**: A physics-based system that evaluates real-time data against hard-coded engineering thresholds (e.g., compressor overload, undervoltage) to provide verifiable, consistent findings.
    3.  **Generative AI (LLM)**: Analyzes the context of the triggered anomalies to provide a probabilistic expert opinion on current and potential future failures.
*   **Automated SMS Alerts**: Integrates with Traccar SMS Gateway to instantly notify maintenance staff when critical faults are detected.
*   **Responsive Web Dashboard**: A clean, user-friendly interface built with Tailwind CSS to visualize telemetry data, review detailed anomaly reports side-by-side, and manage system contacts.

## Technology Stack

*   **Backend**: Python, FastAPI
*   **Database**: PostgreSQL (Supabase)
*   **Machine Learning**: scikit-learn (Isolation Forest)
*   **Frontend**: HTML, Vanilla JavaScript, Tailwind CSS, Lucide Icons
*   **Integrations**: Traccar SMS Gateway, Generative AI APIs

## Installation and Setup

### Prerequisites
*   Python 3.9+
*   PostgreSQL database (or Supabase project)

### Environment Configuration
Create a `.env` file in the root directory with the following variables:
```env
SUPABASE_URL=postgresql://[user]:[password]@[host]:[port]/[db_name]
# Add any required API keys for the Generative AI service here
```

### Setup Steps

1.  **Clone the repository and enter the directory**:
    ```bash
    git clone https://github.com/gericandmorty/AirBnbrrr.git
    cd AirBnbrrr
    ```

2.  **Create and activate a virtual environment**:
    *   Windows:
        ```cmd
        python -m venv venv
        venv\Scripts\activate
        ```
    *   macOS/Linux:
        ```bash
        python -m venv venv
        source venv/bin/activate
        ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run database migrations**:
    Ensure your database has the required schema and auto-increment sequences initialized. Run the provided migration scripts if necessary:
    ```bash
    python fix_telemetry_id.py
    python fix_alerts_id.py
    python fix_contacts_id.py
    ```

## Running the Application

Start the FastAPI server using Uvicorn:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The web dashboard will be available at `http://127.0.0.1:8000`.

## Architecture Overview

1.  **Raspberry Pi** collects sensor data and sends a POST request to `/telemetry`.
2.  The backend stores the raw data and triggers the **Isolation Forest** model.
3.  If an anomaly is flagged, the data is passed to the **Rule Engine** for physics-based threshold verification.
4.  The system then queries the **LLM** for additional contextual analysis.
5.  A combined JSON report is saved, and an **SMS alert** containing a summary and a link to the detailed report is dispatched to authorized contacts.
