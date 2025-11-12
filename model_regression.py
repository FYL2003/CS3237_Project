# -*- coding: utf-8 -*-
"""
Banana Age Prediction using Nonlinear Regression (Random Forest)
---------------------------------------------------------------
Simplified version:
 - Trains model
 - Saves model (.pkl) and scaler
 - Predicts external testdata_banana_1to5.xlsx
 - Prints predicted banana days clearly
"""

import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# === Load dataset ===
df = pd.read_excel("dataset3 app.xlsx")

# === Add noise to temperature & humidity (to suppress unreliable influence) ===
temp_noise_std = 10.0   # ±10°C variation
humid_noise_std = 25.0  # ±25% RH variation
df["temperature"] = df["temperature"] + np.random.normal(0, temp_noise_std, len(df))
df["humidity"] = df["humidity"] + np.random.normal(0, humid_noise_std, len(df))
df["temperature"] = df["temperature"].clip(15, 40)
df["humidity"] = df["humidity"].clip(10, 90)

# === Features & target ===
X = df.drop(columns=['day'])
y = df['day']

# === Split ===
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# === Scale ===
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# === Train model ===
rf = RandomForestRegressor(n_estimators=200, random_state=42)
rf.fit(X_train_scaled, y_train)

# === Evaluate model ===
y_pred = rf.predict(X_test_scaled)
mae = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
r2 = r2_score(y_test, y_pred)

print("=== Banana Age Prediction Results ===")
print(f"MAE: {mae:.3f}")
print(f"RMSE: {rmse:.3f}")
print(f"R²: {r2:.3f}")

# === Save model and scaler ===
joblib.dump(rf, "banana_regression_model.pkl")
joblib.dump(scaler, "banana_scaler.pkl")
print("\nModel and scaler saved as banana_regression_model.pkl & banana_scaler.pkl")

# === Predict on external test data ===
try:
    test_df = pd.read_excel("testdata_banana_1to5.xlsx")
    print("\n=== External Test Data Loaded ===")
    print(test_df)

    # Load saved model and scaler (optional)
    loaded_model = joblib.load("banana_regression_model.pkl")
    loaded_scaler = joblib.load("banana_scaler.pkl")

    # Scale features
    test_scaled = loaded_scaler.transform(test_df)

    # Predict banana age
    predictions = loaded_model.predict(test_scaled)

    # Combine with input data
    results_test = test_df.copy()
    results_test["Predicted_day"] = predictions.round(2)
    results_test["Predicted_day_rounded"] = results_test["Predicted_day"].round().astype(int)

    print("\n=== Predicted Banana Days (External Test) ===")
    print(results_test[["Predicted_day", "Predicted_day_rounded"]])

    # Save results
    results_test.to_excel("banana_external_predictions.xlsx", index=False)
    print("\nPredictions saved to banana_external_predictions.xlsx")

except Exception as e:
    print(f"\n[Warning] Could not run external test: {e}")
