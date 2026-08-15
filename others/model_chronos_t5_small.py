import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_percentage_error
import torch
from chronos import ChronosPipeline


df = pd.read_csv("consumption_data_avg_hourly.csv")
df_train = df[df['start_date'] < "2023-10-01"]
df_test = df[df['start_date'] >= "2023-10-01"]


pipeline = ChronosPipeline.from_pretrained(
    "amazon/chronos-t5-small",
    device_map="cpu",
    torch_dtype=torch.float32,
)

context = torch.tensor(df_test["avg_value_hourly"].values[0:512], dtype=torch.float32)
prediction_length = 48

forecast = pipeline.predict(
    context,
    prediction_length
)


# visualize the forecast
forecast_index = range(len(df), len(df) + prediction_length)
low, median, high = np.quantile(forecast[0].numpy(), [0.1, 0.5, 0.9], axis=0)

plt.figure(figsize=(8, 4))
plt.plot(df_test['avg_value_hourly'].values[512:512+48], color="royalblue", label="historical data")
plt.plot(median, color="tomato", label="median forecast")
plt.fill_between(list(range(48)), low, high, color="tomato", alpha=0.3, label="80% prediction interval")
plt.legend()
plt.grid()
plt.show()


error_mae = mean_absolute_percentage_error(df_test['avg_value_hourly'].values[512:512+48], median)
print(error_mae*100)
