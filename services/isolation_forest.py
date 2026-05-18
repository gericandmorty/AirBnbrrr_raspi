import pandas as pd
from sklearn.ensemble import IsolationForest
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
        self.training_means = None
        self._is_trained = False

        # Automatically train the model upon instantiation
        try:
            self.train()
        except Exception as e:
            logging.error(f"Initial model training failed on startup: {e}. Will attempt to train lazily on demand.")

    def train(self):
        """
        Connects to the Supabase database, extracts historical data, preprocesses it, 
        and trains the Isolation Forest model.
        """
        logging.info("Connecting to Supabase PostgreSQL database for training...")
        try:
            engine = create_engine(DB_URI)
            query = f"SELECT {', '.join(self.sensor_columns)} FROM telemetry"
            df = pd.read_sql_query(query, engine)
            engine.dispose()
        except Exception as e:
            logging.error(f"Failed to load data from database: {e}")
            raise

        if df.empty:
            raise ValueError("The telemetry table is empty. Cannot train the model.")

        logging.info(f"Loaded {len(df)} historical records. Preprocessing...")
        
        # Convert columns to numeric, coercing errors to NaN
        for col in self.sensor_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate and save the means for each column.
        # This is CRITICAL for filling missing values in future single-row predictions.
        self.training_means = df.mean()
        
        # Fill missing values in the training set
        df = df.fillna(self.training_means)

        # Initialize and fit the model
        logging.info("Training Isolation Forest model...")
        self.model = IsolationForest(
            contamination=self.contamination, 
            random_state=self.random_state
        )
        self.model.fit(df)
        
        self._is_trained = True
        logging.info("Model training complete.")

    def is_anomaly(self, sensor_data: dict) -> bool:
        """
        Takes a dictionary of new sensor readings and returns True if it's an anomaly.
        
        Args:
            sensor_data (dict): A dictionary containing sensor readings. 
                                Keys should match self.sensor_columns.
                                
        Returns:
            bool: True if the data is an anomaly, False if it is normal.
        """
        if not self._is_trained:
            try:
                logging.info("Model not trained yet. Attempting lazy training now...")
                self.train()
            except Exception as e:
                logging.error(f"Lazy model training failed: {e}. Falling back to safe default (no anomaly).")
                return False

        # Convert the incoming dictionary to a single-row DataFrame
        # Ensure we only use the columns the model expects, in the exact order
        df_new = pd.DataFrame([sensor_data], columns=self.sensor_columns)

        # Convert to numeric
        for col in self.sensor_columns:
            df_new[col] = pd.to_numeric(df_new[col], errors='coerce')

        # Fill any missing values with the means learned during training
        df_new = df_new.fillna(self.training_means)

        # Predict (-1 is anomaly, 1 is normal)
        prediction = self.model.predict(df_new)[0]
        
        return prediction == -1