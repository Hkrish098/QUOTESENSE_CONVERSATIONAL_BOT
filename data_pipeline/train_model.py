import pandas as pd
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor

# Option 1: Using the correct Mac slash (Best if you stay on Mac)
df = pd.read_csv('data/cleaned_data_v2_no_leakage.csv')

# Option 2: The "Universal" way (Safest)
import os
file_path = os.path.join('data', 'cleaned_data_v2_no_leakage.csv')
df = pd.read_csv(file_path)
X = df.drop(columns=['rent_price_inr_per_month'])
y = df['rent_price_inr_per_month']

# Split the data (80% training, 20% testing)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# ==========================================
# APPROACH 1: RANDOM FOREST (The Committee)
# ==========================================
rf_model = RandomForestRegressor(
    n_estimators=100,    # Number of trees in the forest
    max_depth=10,        # Limits tree growth to prevent overfitting
    random_state=42
)

rf_model.fit(X_train, y_train)
rf_preds = rf_model.predict(X_test)

print("--- Random Forest Results ---")
print(f"R2 Score: {r2_score(y_test, rf_preds):.4f}")
print(f"MAE: ₹{mean_absolute_error(y_test, rf_preds):.2f}")


# ==========================================
# APPROACH 2: GRADIENT BOOSTING (The Perfectionist)
# ==========================================
gb_model = GradientBoostingRegressor(
    n_estimators=300,    # More trees for boosting usually improves accuracy
    learning_rate=0.05,  # Smaller steps make the learning more precise
    max_depth=6,         # Slightly deeper trees to catch complex Bangalore trends
    random_state=42
)

gb_model.fit(X_train, y_train)
gb_preds = gb_model.predict(X_test)

print("\n--- Gradient Boosting Results ---")
print(f"R2 Score: {r2_score(y_test, gb_preds):.4f}")
print(f"MAE: ₹{mean_absolute_error(y_test, gb_preds):.2f}")


# ==========================================
# SAVING THE MODEL FOR DEPLOYMENT
# ==========================================

# 1. Define the target path (Go up one level, then into backend/models)
# This works on both Mac and Windows
target_dir = os.path.join('..', 'backend', 'models')

# 2. Create the directory if it doesn't exist (safety check)
os.makedirs(target_dir, exist_ok=True)

# 3. Save the Gradient Boosting model (The Brain)
model_path = os.path.join(target_dir, 'blr_rent_model.joblib')
joblib.dump(gb_model, model_path)

# 4. Save the column names (The Map)
features_path = os.path.join(target_dir, 'model_features.joblib')
joblib.dump(list(X.columns), features_path)

print(f"\n--- Deployment Files Ready ---")
print(f"1. Model saved to: {model_path}")
print(f"2. Features saved to: {features_path}")