import requests, keyring, json
key = keyring.get_password("FxCompany", "jquants_api_key")
h = {"x-api-key": key}

r1 = requests.get("https://api.jquants.com/v2/equities/master", headers=h)
d1 = r1.json()["data"]
print(f"stocks: {len(d1)}")
print(f"cols: {list(d1[0].keys())}")

r2 = requests.get("https://api.jquants.com/v2/equities/bars/daily", headers=h,
                  params={"code":"6118","from":"2025-01-06","to":"2025-01-10"})
d2 = r2.json()["data"]
print(f"price cols: {list(d2[0].keys()) if d2 else 'none'}")
print(f"sample: {d2[:1]}")
