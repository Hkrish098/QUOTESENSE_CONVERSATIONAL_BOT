import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error

# 1. Load Data
df = pd.read_csv('data/cleaned_data_v2_no_leakage.csv')

# 2. Separate Features and Target
X = df.drop(columns=['rent_price_inr_per_month'])
y = df['rent_price_inr_per_month']

# 3. Train-Test Split (Same 80/20 split as before)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. Initialize and Train Linear Regression
lr_model = LinearRegression()
lr_model.fit(X_train, y_train)

# 5. Predict and Evaluate
lr_preds = lr_model.predict(X_test)

print("--- Linear Regression Results ---")
print(f"Accuracy (R2 Score): {r2_score(y_test, lr_preds):.4f}")
print(f"Average Error (MAE): ₹{mean_absolute_error(y_test, lr_preds):.2f}")

# 6. Show Coefficient logic (How Linear Regression 'thinks')
# It assigns a fixed weight to every feature
#coeff_df = pd.DataFrame({'Feature': X.columns, 'Weight': lr_model.coef_})
#print("\nTop 5 Weights (Linear coefficients):")
#print(coeff_df.sort_values(by='Weight', ascending=False).head(5))