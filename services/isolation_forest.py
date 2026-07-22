import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import logging
from sqlalchemy import create_engine
from database import DB_URI

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AnomalyDetectorService:
    """
    A service class to train an Isolation Forest model on historical telemetry data
    and predict anomalies on new incoming data using Supabase PostgreSQL.
    """
    def __init__(self, db_path: str = None, contamination: float = 0.05, random_state: int = 42):
        # db_path parameter kept for backwards compatibility but we query Supabase directly
        self.contamination = contamination
        self.random_state = random_state
        
        # Define the exact columns the model expects
        self.sensor_columns = [
            'dust_sensor', 'dht_temp', 'dht_humidity', 'vibration',
            'ds18b20_temp1', 'ds18b20_temp2',
            'pzem_voltage', 'pzem_current', 'pzem_power', 'pzem_energy',
            'pzem_frequency', 'pzem_power_factor',
        ]
        
        self.model = None
        self.scaler = None
        self.pca = None
        self.training_means = None
        self._is_trained = False

        # Automatically train the model upon instantiation
        try:
            self.train()
        except Exception as e:
            logging.error(f"Initial model training failed on startup: {e}. Will attempt to train lazily on demand.")

    def train(self):
        """
        Connects to the Supabase database, extracts historical data from data_gathered table 
        (or telemetry table fallback), preprocesses it, and trains the Isolation Forest model and PCA 2D reducer.
        """
        logging.info("Connecting to Supabase PostgreSQL database for training...")
        df = pd.DataFrame()
        engine = None

        try:
            engine = create_engine(DB_URI)
            query = f"SELECT id, timestamp, ac_unit, {', '.join(self.sensor_columns)} FROM data_gathered ORDER BY id ASC"
            df = pd.read_sql_query(query, engine)
        except Exception as e:
            logging.warning(f"Could not load training data from data_gathered: {e}. Trying telemetry table...")

        if df.empty and engine is not None:
            try:
                query = f"SELECT id, timestamp, {', '.join(self.sensor_columns)} FROM telemetry ORDER BY id ASC"
                df = pd.read_sql_query(query, engine)
            except Exception as e:
                logging.error(f"Failed to load fallback data from telemetry: {e}")
                raise

        if engine is not None:
            engine.dispose()

        if df.empty:
            raise ValueError("Both data_gathered and telemetry tables are empty. Cannot train model.")

        logging.info(f"Loaded {len(df)} historical records. Preprocessing...")
        
        # Convert columns to numeric, coercing errors to NaN
        for col in self.sensor_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate and save the means for each column.
        self.training_means = df[self.sensor_columns].mean()
        
        # Fill missing values in the training set
        df_features = df[self.sensor_columns].fillna(self.training_means)

        # Initialize and fit the scaler and Isolation Forest model
        logging.info("Training Isolation Forest model & fitting 2D PCA...")
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(df_features)

        self.pca = PCA(n_components=2, random_state=self.random_state)
        self.pca.fit(X_scaled)

        self.model = IsolationForest(
            contamination=self.contamination, 
            random_state=self.random_state
        )
        self.model.fit(X_scaled)
        
        self._is_trained = True
        logging.info("Model training complete.")

    def is_anomaly(self, sensor_data: dict) -> bool:
        """
        Takes a dictionary of new sensor readings and returns True if it's an anomaly.
        """
        if not self._is_trained:
            try:
                logging.info("Model not trained yet. Attempting lazy training now...")
                self.train()
            except Exception as e:
                logging.error(f"Lazy model training failed: {e}. Falling back to safe default (no anomaly).")
                return False

        # Convert the incoming dictionary to a single-row DataFrame
        df_new = pd.DataFrame([sensor_data], columns=self.sensor_columns)

        # Convert to numeric
        for col in self.sensor_columns:
            df_new[col] = pd.to_numeric(df_new[col], errors='coerce')

        # Fill any missing values with the means learned during training
        df_new = df_new.fillna(self.training_means)

        # Scale & Predict (-1 is anomaly, 1 is normal)
        X_scaled = self.scaler.transform(df_new)
        prediction = self.model.predict(X_scaled)[0]
        
        return prediction == -1

    def get_scatter_data(self, ac_unit: str = None, limit: int = 500) -> dict:
        """
        Fetches historical telemetry data from data_gathered (or telemetry), calculates 2D PCA coordinates, 
        Isolation Forest decision scores, and returns scatter points formatted for real-time frontend visualization.
        """
        if not self._is_trained:
            self.train()

        df = pd.DataFrame()
        engine = None
        source_table = "data_gathered"

        try:
            engine = create_engine(DB_URI)
            where_clause = f"WHERE ac_unit = '{ac_unit}'" if ac_unit else ""
            query = f"""
                SELECT id, timestamp, ac_unit, {', '.join(self.sensor_columns)} 
                FROM data_gathered 
                {where_clause}
                ORDER BY id DESC 
                LIMIT {limit}
            """
            df = pd.read_sql_query(query, engine)
        except Exception as e:
            logging.warning(f"Failed to fetch scatter data from data_gathered: {e}. Falling back to telemetry...")

        if df.empty and engine is not None:
            try:
                source_table = "telemetry"
                query = f"""
                    SELECT id, timestamp, {', '.join(self.sensor_columns)} 
                    FROM telemetry 
                    ORDER BY id DESC 
                    LIMIT {limit}
                """
                df = pd.read_sql_query(query, engine)
            except Exception as e:
                logging.error(f"Failed to fetch scatter data from telemetry fallback: {e}")

        if engine is not None:
            engine.dispose()

        if df.empty:
            return {"points": [], "stats": {"total": 0, "regular": 0, "abnormal": 0, "contamination": self.contamination, "source_table": source_table}}

        # Reverse so points are in chronological order
        df = df.iloc[::-1].reset_index(drop=True)

        for col in self.sensor_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df_features = df[self.sensor_columns].fillna(self.training_means)

        # Scale and transform via PCA
        X_scaled = self.scaler.transform(df_features)
        coords_2d = self.pca.transform(X_scaled)
        scores = self.model.decision_function(X_scaled)
        predictions = self.model.predict(X_scaled)

        points = []
        regular_count = 0
        abnormal_count = 0

        # Mark older points as training, recent points as regular or abnormal
        n = len(df)
        training_cutoff = int(n * 0.7)

        for i in range(n):
            is_anom = bool(predictions[i] == -1)
            score = float(scores[i])
            x_val = round(float(coords_2d[i, 0]), 3)
            y_val = round(float(coords_2d[i, 1]), 3)

            if is_anom:
                category = "abnormal"
                abnormal_count += 1
            elif i < training_cutoff:
                category = "training"
                regular_count += 1
            else:
                category = "regular"
                regular_count += 1

            points.append({
                "id": int(df.at[i, "id"]) if pd.notnull(df.at[i, "id"]) else i,
                "timestamp": str(df.at[i, "timestamp"]) if pd.notnull(df.at[i, "timestamp"]) else "",
                "ac_unit": str(df.at[i, "ac_unit"]) if "ac_unit" in df.columns and pd.notnull(df.at[i, "ac_unit"]) else (ac_unit or "AC1"),
                "x": x_val,
                "y": y_val,
                "category": category,
                "is_anomaly": is_anom,
                "score": round(score, 4),
                "pzem_power": float(df.at[i, "pzem_power"]) if pd.notnull(df.at[i, "pzem_power"]) else 0,
                "dht_temp": float(df.at[i, "dht_temp"]) if pd.notnull(df.at[i, "dht_temp"]) else 0,
                "pzem_voltage": float(df.at[i, "pzem_voltage"]) if pd.notnull(df.at[i, "pzem_voltage"]) else 0,
                "vibration": float(df.at[i, "vibration"]) if pd.notnull(df.at[i, "vibration"]) else 0,
                "dust_sensor": float(df.at[i, "dust_sensor"]) if pd.notnull(df.at[i, "dust_sensor"]) else 0,
            })

        explained_var = [round(float(v), 4) for v in self.pca.explained_variance_ratio_]

        return {
            "points": points,
            "stats": {
                "total": len(points),
                "regular": regular_count,
                "abnormal": abnormal_count,
                "contamination": self.contamination,
                "pca_variance": explained_var,
                "source_table": source_table,
            }
        }