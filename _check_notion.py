import sys, os, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOKEN  = os.environ.get("NOTION_TOKEN","")
PARENT = os.environ.get("NOTION_PARENT","")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
r = requests.get(f"https://api.notion.com/v1/pages/{PARENT}", headers=HEADERS)
print(f"status: {r.status_code}")
if r.status_code == 200:
    print("OK: アクセス権限あり")
else:
    print(r.text[:300])
