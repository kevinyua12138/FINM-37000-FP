# %% [markdown]
# # Throwaway prototype of #5 (shocks), #6 (labels) and the 2x2 table (#10)
# Not the real detector. It exists so the team can look at real numbers before the issues are built.
# Needs a few days of ES mbp-1 in `data/raw/` (see `src/data/download.py`).
# Choices marked PROTOTYPE are open design questions for #5, #6, #8 and #9.

# %%
import glob
import sys

import databento as db
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yaml

sys.path.insert(0, "src")
from events.labels import forward_return_labels  # noqa: E402

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)
TZ = cfg["session"]["timezone"]

WINDOW = pd.Timedelta("10s")
OBS = pd.Timedelta("3s")
LATENCY = pd.Timedelta("100ms")
COOLDOWN = pd.Timedelta("120s")
HORIZONS = [5, 30, 120]
PCTL = 0.995
HISTORY_DAYS = 5
N_DAYS = 6  # days to load; more days need more memory

# %% [markdown]
# ## Load quotes

# %%
def load_day(path):
    df = db.DBNStore.from_file(path).to_df(tz=TZ)
    df = df[["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00", "instrument_id"]]
    df = df[df["bid_px_00"] > 0]
    df = df[df["ask_px_00"] > df["bid_px_00"]]  # drop empty or crossed quotes
    df = df.assign(mid=(df["bid_px_00"] + df["ask_px_00"]) / 2)
    return df.sort_index()


files = sorted(glob.glob(f"{cfg['data']['raw_dir']}/ES_mbp-1_*.dbn.zst"))[:N_DAYS]
days = {pd.Timestamp(p.split("_")[-1].split(".")[0]).date(): load_day(p) for p in files}
print({d: len(q) for d, q in days.items()})

# %% [markdown]
# ## Shocks: M(t) = |mid(t) - mid(t-10s)| on a 1-second grid, threshold from the previous days only

# %%
def move_series(q):
    mid = q["mid"].resample("1s").last().ffill()
    return mid, (mid - mid.shift(10)).abs()


grid = {d: move_series(q) for d, q in days.items()}
dates = sorted(days)


def detect(day_idx):
    d = dates[day_idx]
    history = pd.concat([grid[x][1] for x in dates[max(0, day_idx - HISTORY_DAYS):day_idx]]).dropna()
    threshold = history.quantile(PCTL)
    mid, move = grid[d]
    events, last = [], None
    for t in move.index[move > threshold]:
        if last is None or t - last >= COOLDOWN:
            direction = int(np.sign(mid[t] - mid[t - WINDOW]))
            events.append({"t0": t, "date": d, "direction": direction, "size": move[t], "threshold": threshold})
            last = t
    return events


events = pd.DataFrame([e for i in range(1, len(dates)) for e in detect(i)])
print(len(events), "shocks")
events.head()

# %% [markdown]
# ## Features over the 3 second observation window
# PROTOTYPE: the eaten side is the ask after an up-shock and the bid after a down-shock.
# X is the best eaten-side price at t0-10s and D_pre its size. D(t) is the size at X: the best quote's
# size if X is still the best price, 0 if the best price has moved past X (nothing left at X), and D_pre
# if it came back through X (refilled at a better price). MBP-1 only shows the best level, so this is
# the closest same-price measure it allows (mbp-10 in #16 would show the real size at X).
# OFI follows Cont, Kukanov and Stoikov, scaled by the sum of absolute changes so it lies in [-1, 1].

# %%
def ofi_events(q):
    bp, ap, bs, a_s = q["bid_px_00"], q["ask_px_00"], q["bid_sz_00"], q["ask_sz_00"]
    bp0, ap0, bs0, as0 = bp.shift(), ap.shift(), bs.shift(), a_s.shift()
    e = (np.where(bp >= bp0, bs, 0) - np.where(bp <= bp0, bs0, 0)
         - np.where(ap <= ap0, a_s, 0) + np.where(ap >= ap0, as0, 0))
    return pd.Series(e, index=q.index).iloc[1:]


def last_at(q, ts):
    return q.iloc[q.index.searchsorted(ts, side="right") - 1]


def eaten_quote(row, direction):
    return (row["ask_px_00"], row["ask_sz_00"]) if direction > 0 else (row["bid_px_00"], row["bid_sz_00"])


def depth_at_x(px, sz, x, direction, d_pre):
    past = px > x if direction > 0 else px < x
    return np.where(px == x, sz, np.where(past, 0.0, d_pre))


rows = []
for ev in events.itertuples():
    q = days[ev.date]
    ofi = ofi_events(q)
    x, d_pre = eaten_quote(last_at(q, ev.t0 - WINDOW), ev.direction)
    # quote state at t0, then every update through t0 + 3s
    frame = pd.concat([last_at(q, ev.t0).to_frame().T.set_index(pd.DatetimeIndex([ev.t0])), q.loc[ev.t0:ev.t0 + OBS]])
    px, sz = eaten_quote(frame, ev.direction)
    depth = pd.Series(depth_at_x(px.to_numpy(float), sz.to_numpy(float), x, ev.direction, d_pre), index=frame.index)
    back = depth[depth >= 0.5 * d_pre]
    w = ofi[(ofi.index > ev.t0) & (ofi.index <= ev.t0 + OBS)]
    ofi_norm = w.sum() / w.abs().sum() if w.abs().sum() > 0 else 0.0
    rows.append({
        "refill_ratio": depth.iloc[-1] / d_pre,
        "half_life_s": (back.index[0] - ev.t0).total_seconds() if len(back) else np.nan,
        "ofi": ev.direction * ofi_norm,
    })

events = pd.concat([events, pd.DataFrame(rows)], axis=1)

# %% [markdown]
# ## Forward-return labels (issue #6): entry at t0 + 3.1s, y_h measured from the entry quote

# %%
labelled = [forward_return_labels(days[d], g) for d, g in events.groupby("date")]
labels = pd.concat(labelled)[["y_5s", "y_30s", "y_120s"]]
events = events.drop(columns=[c for c in labels.columns if c in events.columns]).join(labels)
events.head()

# %% [markdown]
# ## 2x2 regime table
# PROTOTYPE: refill is slow below the median ratio and pressure is strong above the median OFI.
# y_h is signed by the shock direction, so positive means the move continued.

# %%
slow = events["refill_ratio"] < events["refill_ratio"].median()
strong = events["ofi"] > events["ofi"].median()
events["regime"] = np.select(
    [slow & strong, ~slow & ~strong],
    ["follow (slow refill, strong pressure)", "fade (fast refill, weak pressure)"],
    default="no trade (signals disagree)",
)
print("refill median:", events["refill_ratio"].median(), " ofi median:", events["ofi"].median())
events.groupby("regime")[["y_5s", "y_30s", "y_120s"]].agg(["count", "mean"])

# %% [markdown]
# ## Chart 1: refill half-life over time
# Half-life is the seconds until the eaten side is back to half of its pre-shock size.
# Shocks that never get back within the 3 second window are drawn at the top as ">3s".

# %%
BLUE = "#2a6fdb"
hl = events.assign(censored=events["half_life_s"].isna(), y=events["half_life_s"].fillna(OBS.total_seconds()))
fig = go.Figure()
for censored, name, symbol in [(False, "recovered within 3s", "circle"), (True, "not recovered (>3s)", "circle-open")]:
    d = hl[hl["censored"] == censored]
    fig.add_trace(go.Scatter(x=d["t0"], y=d["y"], mode="markers", name=name,
                             marker=dict(color=BLUE, size=9, symbol=symbol, line=dict(width=2, color=BLUE))))
fig.update_layout(template="plotly_white", title="Refill half-life after each ES shock",
                  xaxis_title="shock time", yaxis_title="half-life (seconds)", yaxis_range=[-0.2, 3.4])
fig.show()

# %% [markdown]
# ## Chart 2: forward returns after a shock
# Mean of y_h over all shocks, in basis points, with one standard error. Positive means the move continued.

# %%
y = events[["y_5s", "y_30s", "y_120s"]] * 1e4
mean, se = y.mean(), y.std() / np.sqrt(y.count())
fig = go.Figure(go.Bar(x=["5s", "30s", "120s"], y=mean, error_y=dict(type="data", array=se),
                       marker_color=BLUE, showlegend=False))
fig.update_layout(template="plotly_white", title=f"Mean forward return after a shock (n={len(events)})",
                  xaxis_title="horizon after entry", yaxis_title="return in the shock direction (bp)")
fig.show()

# %% [markdown]
# ## Issue #6 figures
# Writes half-life, refill ratio and the three forward returns, each over shock time, to `figures/issue6/`.

# %%
from events.figures import make_issue6_figures  # noqa: E402

make_issue6_figures(events, "figures/issue6")
