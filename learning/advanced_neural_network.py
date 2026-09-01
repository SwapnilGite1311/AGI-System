"""
Advanced Neural Network - Enhanced AI/ML Features for Enterprise
Advanced predictive capabilities, ensemble methods, and deep learning models.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
import numpy as np
from loguru import logger

from core.config import load_config, data_dir

from core.atomic_io import write_json_atomic

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available - advanced neural features limited")


class AdvancedNeuralNetwork:
    """
    Advanced neural network capabilities for enterprise:
    - Ensemble methods
    - Predictive analytics
    - Time series forecasting
    - Anomaly detection
    - Deep learning models
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize advanced neural network system."""
        
        self.config = load_config(config_path)
        # Project-relative, not cwd-relative (audit M-5).
        self.models_path = data_dir(config_path) / "advanced_models"
        self.models_path.mkdir(parents=True, exist_ok=True)
        
        self.models = {}
        self.scalers = {}
        self.training_history = []
        
        logger.info("Advanced Neural Network initialized")

    def create_ensemble_model(
        self,
        model_type: str = "random_forest",
        input_features: int = 10,
        task_type: str = "classification"
    ) -> Dict[str, Any]:
        """Create an ensemble model for improved predictions."""
        
        try:
            if model_type == "random_forest":
                if task_type == "classification":
                    model = RandomForestClassifier(
                        n_estimators=100,
                        max_depth=10,
                        random_state=42
                    )
                else:
                    from sklearn.ensemble import RandomForestRegressor
                    model = RandomForestRegressor(
                        n_estimators=100,
                        max_depth=10,
                        random_state=42
                    )
            
            elif model_type == "gradient_boosting":
                if task_type == "classification":
                    model = GradientBoostingClassifier(
                        n_estimators=100,
                        learning_rate=0.1,
                        max_depth=5,
                        random_state=42
                    )
                else:
                    from sklearn.ensemble import GradientBoostingRegressor
                    model = GradientBoostingRegressor(
                        n_estimators=100,
                        learning_rate=0.1,
                        max_depth=5,
                        random_state=42
                    )
            
            else:
                return {
                    "success": False,
                    "error": f"Unsupported model type: {model_type}"
                }
            
            model_id = str(uuid.uuid4())
            self.models[model_id] = {
                "model": model,
                "model_type": model_type,
                "task_type": task_type,
                "input_features": input_features,
                "created_at": datetime.now().isoformat(),
                "trained": False
            }
            
            return {
                "success": True,
                "model_id": model_id,
                "model_type": model_type,
                "task_type": task_type,
                "message": f"Ensemble model created: {model_type}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create ensemble model: {str(e)}"
            }

    def train_predictive_model(
        self,
        model_id: str,
        training_data: List[List[float]],
        labels: List[Any],
        validation_split: float = 0.2
    ) -> Dict[str, Any]:
        """Train a predictive model with validation."""
        
        if model_id not in self.models:
            return {
                "success": False,
                "error": f"Model {model_id} not found"
            }
        
        try:
            X = np.array(training_data)
            y = np.array(labels)
            
            # Split data
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=validation_split, random_state=42
            )
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_val_scaled = scaler.transform(X_val)
            
            # Store scaler
            self.scalers[model_id] = scaler
            
            # Train model
            model = self.models[model_id]["model"]
            model.fit(X_train_scaled, y_train)
            
            # Evaluate
            train_score = model.score(X_train_scaled, y_train)
            val_score = model.score(X_val_scaled, y_val)
            
            # Update model status
            self.models[model_id]["trained"] = True
            self.models[model_id]["train_score"] = train_score
            self.models[model_id]["val_score"] = val_score
            self.models[model_id]["trained_at"] = datetime.now().isoformat()
            
            # Record training history
            self.training_history.append({
                "model_id": model_id,
                "train_score": train_score,
                "val_score": val_score,
                "training_samples": len(X_train),
                "validation_samples": len(X_val),
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "success": True,
                "model_id": model_id,
                "train_score": train_score,
                "val_score": val_score,
                "message": f"Model trained successfully. Validation score: {val_score:.3f}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Training failed: {str(e)}"
            }

    def make_prediction(
        self,
        model_id: str,
        features: List[float]
    ) -> Dict[str, Any]:
        """Make a prediction using a trained model."""
        
        if model_id not in self.models:
            return {
                "success": False,
                "error": f"Model {model_id} not found"
            }
        
        if not self.models[model_id]["trained"]:
            return {
                "success": False,
                "error": f"Model {model_id} is not trained"
            }
        
        try:
            model = self.models[model_id]["model"]
            scaler = self.scalers.get(model_id)
            
            X = np.array([features])
            if scaler:
                X_scaled = scaler.transform(X)
            else:
                X_scaled = X
            
            prediction = model.predict(X_scaled)[0]
            
            # Get prediction confidence if available
            if hasattr(model, "predict_proba"):
                probabilities = model.predict_proba(X_scaled)[0]
                confidence = max(probabilities)
            else:
                confidence = None
            
            return {
                "success": True,
                "prediction": prediction,
                "confidence": confidence,
                "model_id": model_id,
                "message": f"Prediction made: {prediction}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Prediction failed: {str(e)}"
            }

    def detect_anomalies(
        self,
        data: List[List[float]],
        threshold: float = 2.0,
        method: str = "statistical"
    ) -> Dict[str, Any]:
        """Detect anomalies in data using statistical or ML methods."""
        
        try:
            X = np.array(data)
            
            if method == "statistical":
                # Z-score based anomaly detection
                means = np.mean(X, axis=0)
                stds = np.std(X, axis=0)
                
                anomalies = []
                for i, sample in enumerate(X):
                    z_scores = np.abs((sample - means) / (stds + 1e-8))
                    if np.any(z_scores > threshold):
                        anomalies.append({
                            "index": i,
                            "sample": sample.tolist(),
                            "z_scores": z_scores.tolist(),
                            "anomaly_score": float(np.max(z_scores))
                        })
            
            elif method == "isolation_forest":
                from sklearn.ensemble import IsolationForest
                
                clf = IsolationForest(contamination=0.1, random_state=42)
                predictions = clf.fit_predict(X)
                
                anomalies = []
                for i, prediction in enumerate(predictions):
                    if prediction == -1:  # Anomaly
                        anomalies.append({
                            "index": i,
                            "sample": X[i].tolist(),
                            "anomaly_score": float(-clf.score_samples(X)[i])
                        })
            
            else:
                return {
                    "success": False,
                    "error": f"Unsupported anomaly detection method: {method}"
                }
            
            return {
                "success": True,
                "anomalies": anomalies,
                "total_anomalies": len(anomalies),
                "total_samples": len(data),
                "anomaly_rate": len(anomalies) / len(data),
                "method": method,
                "threshold": threshold
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Anomaly detection failed: {str(e)}"
            }

    def create_time_series_forecast(
        self,
        data: List[float],
        forecast_periods: int = 10,
        method: str = "moving_average"
    ) -> Dict[str, Any]:
        """Create time series forecasts for business metrics."""
        
        try:
            series = np.array(data)
            
            if method == "moving_average":
                window_size = min(5, len(series) // 2)
                forecasts = []
                
                for i in range(forecast_periods):
                    if len(series) >= window_size:
                        forecast = np.mean(series[-window_size:])
                    else:
                        forecast = np.mean(series)
                    forecasts.append(float(forecast))
                    series = np.append(series, forecast)  # Append for next iteration
            
            elif method == "exponential_smoothing":
                from statsmodels.tsa.holtwinters import SimpleExpSmoothing
                
                model = SimpleExpSmoothing(series, initialization_method="estimated").fit()
                forecast = model.forecast(forecast_periods)
                forecasts = forecast.tolist()
            
            elif method == "linear_trend":
                from sklearn.linear_model import LinearRegression
                
                X = np.arange(len(series)).reshape(-1, 1)
                model = LinearRegression()
                model.fit(X, series)
                
                future_X = np.arange(len(series), len(series) + forecast_periods).reshape(-1, 1)
                forecasts = model.predict(future_X).tolist()
            
            else:
                return {
                    "success": False,
                    "error": f"Unsupported forecasting method: {method}"
                }
            
            return {
                "success": True,
                "forecasts": forecasts,
                "forecast_periods": forecast_periods,
                "method": method,
                "historical_data_points": len(data),
                "message": f"Forecast generated using {method}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Forecasting failed: {str(e)}"
            }

    def create_deep_learning_model(
        self,
        model_type: str = "feedforward",
        input_size: int = 10,
        hidden_layers: Optional[List[int]] = None,  # not [64,32]: one list shared across all calls
        output_size: int = 1
    ) -> Dict[str, Any]:
        """Create a deep learning model using PyTorch."""

        # A [64, 32] default in the signature is one list shared by every
        # call; anything that mutated it would change the default for all
        # later callers (audit L-5).
        if hidden_layers is None:
            hidden_layers = [64, 32]

        if not TORCH_AVAILABLE:
            return {
                "success": False,
                "error": "PyTorch not available - cannot create deep learning models"
            }
        
        try:
            class FeedForwardNetwork(nn.Module):
                def __init__(self, input_size, hidden_layers, output_size):
                    super().__init__()
                    layers = []
                    prev_size = input_size
                    
                    for hidden_size in hidden_layers:
                        layers.append(nn.Linear(prev_size, hidden_size))
                        layers.append(nn.ReLU())
                        layers.append(nn.Dropout(0.2))
                        prev_size = hidden_size
                    
                    layers.append(nn.Linear(prev_size, output_size))
                    self.network = nn.Sequential(*layers)
                
                def forward(self, x):
                    return self.network(x)
            
            if model_type == "feedforward":
                model = FeedForwardNetwork(input_size, hidden_layers, output_size)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported deep learning model type: {model_type}"
                }
            
            model_id = str(uuid.uuid4())
            self.models[model_id] = {
                "model": model,
                "model_type": model_type,
                "framework": "pytorch",
                "input_size": input_size,
                "hidden_layers": hidden_layers,
                "output_size": output_size,
                "created_at": datetime.now().isoformat(),
                "trained": False
            }
            
            return {
                "success": True,
                "model_id": model_id,
                "model_type": model_type,
                "framework": "pytorch",
                "architecture": {
                    "input_size": input_size,
                    "hidden_layers": hidden_layers,
                    "output_size": output_size
                },
                "message": f"Deep learning model created: {model_type}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create deep learning model: {str(e)}"
            }

    def train_deep_learning_model(
        self,
        model_id: str,
        training_data: List[List[float]],
        labels: List[float],
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 0.001
    ) -> Dict[str, Any]:
        """Train a deep learning model with PyTorch."""
        
        if not TORCH_AVAILABLE:
            return {
                "success": False,
                "error": "PyTorch not available"
            }
        
        if model_id not in self.models:
            return {
                "success": False,
                "error": f"Model {model_id} not found"
            }
        
        try:
            model = self.models[model_id]["model"]
            
            X = torch.FloatTensor(training_data)
            y = torch.FloatTensor(labels).reshape(-1, 1)
            
            # Loss and optimizer
            criterion = nn.MSELoss()
            optimizer = optim.Adam(model.parameters(), lr=learning_rate)
            
            # Training loop
            losses = []
            for epoch in range(epochs):
                optimizer.zero_grad()
                outputs = model(X)
                loss = criterion(outputs, y)
                loss.backward()
                optimizer.step()
                losses.append(loss.item())
            
            # Update model status
            self.models[model_id]["trained"] = True
            self.models[model_id]["epochs_trained"] = epochs
            self.models[model_id]["final_loss"] = losses[-1]
            self.models[model_id]["trained_at"] = datetime.now().isoformat()
            
            return {
                "success": True,
                "model_id": model_id,
                "epochs_trained": epochs,
                "final_loss": losses[-1],
                "loss_history": losses,
                "message": f"Deep learning model trained for {epochs} epochs"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Deep learning training failed: {str(e)}"
            }

    def save_model(self, model_id: str) -> Dict[str, Any]:
        """Save a trained model to disk."""
        
        if model_id not in self.models:
            return {
                "success": False,
                "error": f"Model {model_id} not found"
            }
        
        try:
            model_data = self.models[model_id]
            framework = model_data.get("framework", "sklearn")
            
            if framework == "pytorch":
                model_path = self.models_path / f"{model_id}.pt"
                torch.save(model_data["model"].state_dict(), model_path)
                
                # Save metadata
                metadata = {
                    "model_id": model_id,
                    "model_type": model_data["model_type"],
                    "framework": framework,
                    "architecture": model_data.get("architecture", {}),
                    "trained": model_data["trained"],
                    "trained_at": model_data.get("trained_at"),
                    "epochs_trained": model_data.get("epochs_trained"),
                    "final_loss": model_data.get("final_loss")
                }
                
                metadata_path = self.models_path / f"{model_id}_metadata.json"
                write_json_atomic(metadata_path, metadata)
            
            else:
                import joblib
                model_path = self.models_path / f"{model_id}.joblib"
                joblib.dump(model_data["model"], model_path)
            
            # model_path is bound on both branches (.pt or .joblib). A model
            # file that cannot be read back is a training run silently thrown
            # away - nobody notices until the next load fails.
            if not model_path.exists() or model_path.stat().st_size == 0:
                return {
                    "success": False,
                    "model_id": model_id,
                    "error": (f"Model reported saved but {model_path} is "
                              "missing or empty"),
                }

            return {
                "success": True,
                "model_id": model_id,
                "saved_path": str(model_path),
                "verified": True,
                "message": f"Model {model_id} saved successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save model: {str(e)}"
            }

    def load_model(self, model_id: str) -> Dict[str, Any]:
        """Load a saved model from disk."""
        
        try:
            # Try PyTorch first
            model_path = self.models_path / f"{model_id}.pt"
            if model_path.exists():
                metadata_path = self.models_path / f"{model_id}_metadata.json"
                
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                # Recreate model architecture
                input_size = metadata["architecture"]["input_size"]
                hidden_layers = metadata["architecture"]["hidden_layers"]
                output_size = metadata["architecture"]["output_size"]
                
                class FeedForwardNetwork(nn.Module):
                    def __init__(self, input_size, hidden_layers, output_size):
                        super().__init__()
                        layers = []
                        prev_size = input_size
                        
                        for hidden_size in hidden_layers:
                            layers.append(nn.Linear(prev_size, hidden_size))
                            layers.append(nn.ReLU())
                            layers.append(nn.Dropout(0.2))
                            prev_size = hidden_size
                        
                        layers.append(nn.Linear(prev_size, output_size))
                        self.network = nn.Sequential(*layers)
                    
                    def forward(self, x):
                        return self.network(x)
                
                model = FeedForwardNetwork(input_size, hidden_layers, output_size)
                model.load_state_dict(torch.load(model_path))
                model.eval()
                
                self.models[model_id] = {
                    "model": model,
                    "model_type": metadata["model_type"],
                    "framework": "pytorch",
                    "trained": True,
                    "loaded_at": datetime.now().isoformat()
                }
                
                return {
                    "success": True,
                    "model_id": model_id,
                    "framework": "pytorch",
                    "message": f"PyTorch model {model_id} loaded successfully"
                }
            
            # Try sklearn/joblib
            model_path = self.models_path / f"{model_id}.joblib"
            if model_path.exists():
                import joblib
                model = joblib.load(model_path)
                
                self.models[model_id] = {
                    "model": model,
                    "framework": "sklearn",
                    "trained": True,
                    "loaded_at": datetime.now().isoformat()
                }
                
                return {
                    "success": True,
                    "model_id": model_id,
                    "framework": "sklearn",
                    "message": f"Sklearn model {model_id} loaded successfully"
                }
            
            return {
                "success": False,
                "error": f"No saved model found for {model_id}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to load model: {str(e)}"
            }

    def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get information about a specific model."""
        
        if model_id not in self.models:
            return {
                "success": False,
                "error": f"Model {model_id} not found"
            }
        
        model_data = self.models[model_id]
        
        return {
            "success": True,
            "model_id": model_id,
            "model_type": model_data.get("model_type"),
            "framework": model_data.get("framework", "sklearn"),
            "trained": model_data.get("trained", False),
            "created_at": model_data.get("created_at"),
            "trained_at": model_data.get("trained_at"),
            "architecture": model_data.get("architecture", {}),
            "performance": {
                "train_score": model_data.get("train_score"),
                "val_score": model_data.get("val_score"),
                "final_loss": model_data.get("final_loss"),
                "epochs_trained": model_data.get("epochs_trained")
            }
        }

    def list_models(self) -> Dict[str, Any]:
        """List all available models."""
        
        models_info = []
        for model_id, model_data in self.models.items():
            models_info.append({
                "model_id": model_id,
                "model_type": model_data.get("model_type"),
                "framework": model_data.get("framework", "sklearn"),
                "trained": model_data.get("trained", False),
                "created_at": model_data.get("created_at")
            })
        
        return {
            "success": True,
            "models": models_info,
            "total": len(models_info)
        }