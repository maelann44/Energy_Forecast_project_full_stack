import requests
import os
from datetime import datetime
from datetime import timedelta

import pandas as pd
from dotenv import load_dotenv


load_dotenv()


def get_required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante: {name}")
    return value

url_token = "https://digital.iservices.rte-france.com/token/oauth/"

client_id = get_required_env("RTE_CLIENT_ID")
client_secret = get_required_env("RTE_CLIENT_SECRET")

data = {
    "grant_type": "client_credentials"
}

response = requests.post(
    url_token,
    data=data,
    auth=(client_id, client_secret)
)

print(response.status_code)
print(response.text)

token = response.json().get("access_token")
print(token)



base_url = "https://digital.iservices.rte-france.com/open_api/consumption/v1/short_term"

headers = {


    "Host" : "digital.iservices.rte-france.com",
    "Authorization" : f"Bearer {token}"

}



def daterange(start_date,end_date, delta):
    current_date = start_date
    while current_date < end_date:
        next_date = current_date + delta
        yield current_date,min(next_date, end_date)
        current_date = next_date


# on ne peux aps recuperer 4 ans en une requetes donc on sepâre le code, on separe en bloque de 6 mois
start_date = datetime(2020,1,1)
end_date = datetime(2024,10,1)
six_month = timedelta( days = 6*30)



# le code %2B02:00 sert pour le fuseau horaire


# on veut stocker les données

all_start_date = []
all_values = []     



for start, end in daterange(start_date,end_date,six_month):

    url = f"{base_url}?type=REALISED&start_date={start.isoformat()}%2B02:00&end_date={end.isoformat()}%2B02:00"

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        for entry in response.json()['short_term'][0]['values'] :
            all_start_date.append(entry['start_date'])
            all_values.append(entry['value'])

            #print(entry['value'])

        #print(response.json()['short_term'][0]['values'])


    else :
        print("request failed")



df = pd.DataFrame({'start_date': all_start_date , 'value' : all_values})
print(df)

# pour l'algo de prévisions ont veut des donénes horaire donc on vas faire une moyenne par heure des values

df['start_date'] = pd.to_datetime(df['start_date'], utc=True)
df['date_column'] = df['start_date'].dt.date
df['hour_column'] = df['start_date'].dt.hour
df['min_column'] = df['start_date'].dt.minute

def consumption_avg(group):
    if len(group) < 4 :
        return None

    return ((group['value'].sum())/4)

avg_value = df.groupby(['date_column' , 'hour_column']).apply(consumption_avg).reset_index(name = 'avg_value_hourly')

df = pd.merge(avg_value,df, on=['date_column' , 'hour_column'] , how='inner')

df = df[df['min_column']==0]

df = df[['start_date','date_column','hour_column','avg_value_hourly']]

df.to_csv('consumption_data_avg_hourly.csv', index=False)
print("Data saved")



