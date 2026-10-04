# %%
import databento as db
import plotly.graph_objects as go

df = db.DBNStore.from_file("data/raw/ES_mbp-1_2025-03-03.dbn.zst").to_df(tz="America/Chicago")

print(len(df), "rows")
print(df["symbol"].unique())
print(df["action"].value_counts())
print(df.loc[df["action"] == "T", "side"].value_counts())
print("crossed books:", (df["bid_px_00"] >= df["ask_px_00"]).sum())
print(df.index.min(), "->", df.index.max())

# %%
mid = ((df["bid_px_00"] + df["ask_px_00"]) / 2).resample("1s").last().ffill()
go.Figure(go.Scatter(x=mid.index, y=mid, mode="lines")).update_layout(
    template="plotly_white", title="ES mid-price, 2025-03-03"
).show()
