from binance.client import Client
from datetime import datetime

client = Client()
klines = client.get_klines(symbol='BTCUSDT', interval='1h', limit=10)

print("\n--- BTCUSDT 1-Hour Chart (Last 10 Hours) ---")
for k in klines:
    dt = datetime.fromtimestamp(k[0]/1000).strftime('%Y-%m-%d %H:%M')
    o = float(k[1])
    h = float(k[2])
    l = float(k[3])
    c = float(k[4])
    print(f"{dt} | Open: {o:.2f} | High: {h:.2f} | Low: {l:.2f} | Close: {c:.2f}")
