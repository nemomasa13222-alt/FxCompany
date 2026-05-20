import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "japan_stocks")
from jquants import JQuantsClient

c  = JQuantsClient()
df = c.get_stock_list()
print("市場区分:", df["MktNm"].value_counts().to_dict())

prime = df[df["MktNm"].str.contains("プライム", na=False)]
print(f"プライム銘柄数: {len(prime)}")

secs = prime.groupby(["S33", "S33Nm"]).size().reset_index(name="count")
secs = secs.sort_values("S33")
print()
print("業種33一覧:")
for _, r in secs.iterrows():
    print(f"  {r['S33']}  {r['S33Nm']:20s}  {r['count']}銘柄")
