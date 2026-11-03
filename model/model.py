# 2026 九合一縣市長預測模型（方法見網頁「方法」分頁）
import json, math, random, datetime as dt, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from inputs import *

WEEK = sys.argv[1] if len(sys.argv) > 1 else "2026-10-23"
TODAY = dt.date.fromisoformat(WEEK)
HALF_LIFE = 14
T1_MLD_END = "2026-07-01"  # 美麗島國政民調團隊更換時點（需驗證）
W_BASE = (0.4, 0.3, 0.3)            # 2022 縣市長, 2024 總統, 2024 區域立委
POLL_W = {"多": 0.80, "少": 0.60, "幾乎沒有": 0.30}
SD = {"多": 0.04, "少": 0.055, "幾乎沒有": 0.065}
INCUMB = 0.015
ENV_CAP = float(os.environ.get('ENV_CAP','0.05'))
random.seed(20261128)

def bloc_of(county, name):
    for n, p, b, inc in CANDS[county]:
        if n == name: return b
    return "O"

def baseline(c):
    reg, order, e22, t22, inv22, e24, g22, g24p, g24l = COUNTIES[c]
    parts = [(W_BASE[0], g22), (W_BASE[1], g24p), (W_BASE[2], g24l)]
    parts = [(w, v) for w, v in parts if v is not None]
    return sum(w * v for w, v in parts) / sum(w for w, _ in parts)

def poll_g(c, p, gb):
    county, org, date, n, sup, und, est, src = p
    if est is not None: return est
    g = sum(v for k, v in sup.items() if bloc_of(c, k) == "G")
    b = sum(v for k, v in sup.items() if bloc_of(c, k) == "B")
    if g + b == 0: return None
    # 未表態依結構盤比例分配，並修正機構偏差
    gg = g / (g + b)
    return gg - HOUSE.get(org, 0) / 200.0

def grade_of(county, org, date):
    # A：戴立安（×1.5）；B：震傳媒／山水（×1.2）；C：其他（×0.7）；D：無來源或不可信，不採計；不採計：使用者指定排除的機構
    if (county, org, date) in D_GRADE: return "D", D_GRADE[(county, org, date)]
    if org in EXCLUDE: return "不採計", "TVBS 只採封關民調"
    if (county, org) in EXCLUDE_PAIRS: return "不採計", "使用者指定此縣市不採計該機構"
    t = TIER.get(org, 0.7)
    if org == "美麗島電子報" and date >= T1_MLD_END: t = 0.7
    return ("A" if t >= 1.5 else "B" if t >= 1.2 else "C"), ""

def poll_weight(p):
    county, org, date, n, sup, und, est, src = p
    if org in EXCLUDE or (county, org) in EXCLUDE_PAIRS or (county, org, date) in D_GRADE: return 0.0
    age = (TODAY - dt.date.fromisoformat(date)).days
    has_recent = any(q[0] == county and (q[1] not in EXCLUDE and (q[0], q[1]) not in EXCLUDE_PAIRS and (q[0], q[1], q[2]) not in D_GRADE) and 0 <= (TODAY - dt.date.fromisoformat(q[2])).days <= 84 for q in POLLS)
    if age < 0 or age > (84 if has_recent else 224): return 0.0
    tier = TIER.get(org, 0.7)
    if org == "美麗島電子報" and date >= T1_MLD_END: tier = 0.7  # 戴立安離開後的美麗島民調不再列 T1
    return tier * 0.5 ** (age / HALF_LIFE) * math.sqrt(n / 1000)

def classify(c):
    recent = [p for p in POLLS if p[0] == c and (p[1] not in EXCLUDE and (p[0], p[1]) not in EXCLUDE_PAIRS and (p[0], p[1], p[2]) not in D_GRADE) and 0 <= (TODAY - dt.date.fromisoformat(p[2])).days <= 42]
    older = [p for p in POLLS if p[0] == c and (p[1] not in EXCLUDE and (p[0], p[1]) not in EXCLUDE_PAIRS and (p[0], p[1], p[2]) not in D_GRADE) and 42 < (TODAY - dt.date.fromisoformat(p[2])).days <= 84]
    if len(recent) >= 3: return "多"
    if len(recent) >= 1 or len(older) >= 1: return "少"
    return "幾乎沒有"

# 1) 結構盤與民調平均
info = {}
for c in COUNTIES:
    gb = baseline(c)
    ps = [(poll_weight(p), poll_g(c, p, gb), p) for p in POLLS if p[0] == c]
    ps = [(w, g, p) for w, g, p in ps if w > 0 and g is not None]
    gp = sum(w * g for w, g, _ in ps) / sum(w for w, _, _ in ps) if ps else None
    info[c] = dict(gb=gb, gp=gp, ps=ps, cls=classify(c))

# 2) 全國風向：有民調縣市「民調 − 結構盤」的加權平均，上限 ±3pp，只套用在結構盤部分
MACRO = {"北部": "北部", "中部": "中南部", "南部": "中南部", "東部": "東部離島", "離島": "東部離島"}
METRO = {"臺北市", "新北市", "基隆市", "桃園市", "臺中市", "臺南市", "高雄市"}
def swing(filter_fn):
    sw = [(sum(w for w, _, _ in v["ps"]), v["gp"] - v["gb"]) for c, v in info.items()
          if v["gp"] is not None and c not in MANUAL and filter_fn(c) and min((TODAY - dt.date.fromisoformat(p[2])).days for _, _, p in v["ps"]) <= 84]
    return sum(w * d for w, d in sw) / sum(w for w, _ in sw) if sw else None
nat = swing(lambda c: True)
REG_ENV = {}
for mac in set(MACRO.values()):
    e = swing(lambda c: MACRO[COUNTIES[c][0]] == mac)
    REG_ENV[mac] = e if e is not None else nat
SPILL = 0.025  # 近 12 週無民調縣市：採民進黨自估的外溢幅度 +2～3 個百分點
def has_recent_poll(c):
    return any(p[0] == c and (p[1] not in EXCLUDE and (p[0], p[1]) not in EXCLUDE_PAIRS and (p[0], p[1], p[2]) not in D_GRADE) and 0 <= (TODAY - dt.date.fromisoformat(p[2])).days <= 84 for p in POLLS)
def env_of(c):
    e = REG_ENV[MACRO[COUNTIES[c][0]]] if has_recent_poll(c) else SPILL
    cap = 0.075 if c in METRO else 0.05
    return max(-cap, min(cap, e))
raw_env = nat; env = nat

def inc_adj(c):
    for n, p, b, inc in CANDS[c]:
        if inc and b == "G": return INCUMB
        if inc and b == "B": return -INCUMB
    return 0.0

# 3) 混合 + 個別調整
out_c, out_k, out_p = [], [], []
NAT_SD = 0.015
SIMS = 20000
_trng = random.Random(20261129)   # 投票率抽樣另用一組亂數，不影響原本的抽樣順序
turn_draws = [_trng.gauss(0, TURN_SD * 100) for _ in range(SIMS)]

# 投票率的年齡結構模型：投票率每增加 1 個百分點，綠營兩黨占比的變化（turn_k）
def _logit(p): return math.log(p / (1 - p))
def _inv(x): return 1 / (1 + math.exp(-x))
def age_lean(c):
    nat = AGE_LEAN_NAT
    if c in AGE_LEAN_POLL: return [AGE_LEAN_SHRINK * a + (1 - AGE_LEAN_SHRINK) * b for a, b in zip(AGE_LEAN_POLL[c], nat)]
    return list(nat)
def turnout_effect(c, T, dT):
    # T、dT 為比例（0.62、+0.03）；回傳（新增選民的年齡傾向 A、綠營兩黨占比變化）
    s = AGE_POP[c]; tot = sum(s); lo, hi = -5.0, 5.0
    for _ in range(60):
        k = (lo + hi) / 2; v = sum(si * _inv(_logit(T) + o + k) for si, o in zip(s, LOCAL_TURNOUT_OFFSET)) / tot
        lo, hi = (k, hi) if v < T else (lo, k)
    p0 = [_inv(_logit(T) + o + k) for o in LOCAL_TURNOUT_OFFSET]
    w0 = [si * p for si, p in zip(s, p0)]
    dl = age_lean(c); mu = sum(w * d for w, d in zip(w0, dl)) / sum(w0); dl = [d - mu for d in dl]
    lam = dT * tot / sum(si * i / 100 for si, i in zip(s, TURNOUT_INC))
    p1 = [min(0.98, max(0.05, p + lam * i / 100)) for p, i in zip(p0, TURNOUT_INC)]
    add = [si * (b - a) for si, a, b in zip(s, p0, p1)]
    A = sum(a * d for a, d in zip(add, dl)) / sum(add)
    return A, sum(add) * (A + MOBIL_B) / sum(si * b for si, b in zip(s, p1))
SIMCAMP = {}  # 每縣市每次模擬的勝選陣營，用來算席次機率分布
def camp_of(county, name):
    b = bloc_of(county, name)
    return ("白" if name in WHITE else "藍") if b == "B" else {"G": "綠", "O": "其他"}[b]
nat_draws = [random.gauss(0, NAT_SD) for _ in range(SIMS)]

for c, v in info.items():
    reg, order, e22, t22, inv22, e24, *_ = COUNTIES[c]
    cls = v["cls"]
    adjs = ADJ.get(c, [])
    # 派系調整是在補結構盤，依結構盤權重換算：結構盤 40% 時取原值，20% 時取一半
    def adj_total(wp):
        return sum(a * ((1 - wp) / 0.4 if k == "派系" else 1) for a, _, k in adjs) / 100
    cands = CANDS[c]
    # 選舉人數：(2022 選舉人數 × 1.02 與 2024 總統選舉人數 × 1.005) 平均
    elect = round((e22 * 1.02 + e24 * 1.005) / 2)
    inv = inv22 / 100
    # 投票率敏感度：以 2022 投票率加 2 個百分點為基準，±3 個百分點取平均斜率（每 1 個百分點）
    _tb = TURNOUT_BASE_OVERRIDE.get(c, t22) / 100 + 0.02
    _Au, _up = turnout_effect(c, _tb, 0.03); _Ad, _dn = turnout_effect(c, _tb, -0.03)
    turn_k = (_up - _dn) / 6; turn_A = (_Au + _Ad) / 2
    if c in MANUAL:
        mean = {k: s / 100 for k, s in MANUAL[c].items()}
        sd_c = SD[cls]
        wins = {k: 0 for k in mean}
        simw = []
        for i in range(SIMS):
            draw = {k: max(0.001, m + random.gauss(0, sd_c * math.sqrt(m / 0.35))) for k, m in mean.items()}
            wk = max(draw, key=draw.get); wins[wk] += 1; simw.append(wk)
        SIMCAMP[c] = [camp_of(c, n) for n in simw]
        shares = mean
        gfinal = None
        intervals = {k: (max(0, m - 1.2816 * sd_c * math.sqrt(m / 0.35)), m + 1.2816 * sd_c * math.sqrt(m / 0.35)) for k, m in mean.items()}
        winp = {k: w / SIMS for k, w in wins.items()}
        wp = POLL_W[cls] if v["gp"] is not None else 0
    else:
        wp = POLL_W[cls] if v["gp"] is not None else 0
        struct = v["gb"] + env_of(c) + inc_adj(c)
        adj = adj_total(wp)
        gfinal = wp * (v["gp"] or 0) + (1 - wp) * struct + adj
        other = {k: s / 100 for k, s in OTHER_SHARE.get(c, {}).items()}
        rest = 1 - sum(other.values())
        # 民調間分歧度納入誤差
        if len(v["ps"]) >= 2:
            tw = sum(w for w, _, _ in v["ps"]); spread = math.sqrt(sum(w * (g - v["gp"]) ** 2 for w, g, _ in v["ps"]) / tw)
        else: spread = 0.0
        sd_c = math.hypot(SD[cls], spread)
        gsim = [gfinal + nat_draws[i] + random.gauss(0, sd_c) + turn_k * turn_draws[i] > 0.5 for i in range(SIMS)]
        gwin = sum(gsim) / SIMS
        bwc = next((camp_of(c, n) for n, p, b, i in cands if b == "B"), "其他")
        SIMCAMP[c] = ["綠" if x else bwc for x in gsim]
        shares, intervals, winp = {}, {}, {}
        for n, p, b, inc in cands:
            if b == "G": m = gfinal * rest
            elif b == "B": m = (1 - gfinal) * rest
            else: m = other.get(n, 0.0)
            shares[n] = m
            half = 1.2816 * math.hypot(sd_c, NAT_SD) * rest if b != "O" else 1.2816 * 0.3 * m
            intervals[n] = (max(0, m - half), m + half)
            winp[n] = gwin if b == "G" else (1 - gwin) if b == "B" else 0.0
    # 投票率
    lead = max(winp.values())
    rating = "穩" if lead > 0.9 else "傾向" if lead > 0.75 else "微幅" if lead > 0.6 else "拉鋸"
    tb = TURNOUT_BASE_OVERRIDE.get(c, t22)
    t_adj = 2.0 + {"拉鋸": 2.5, "微幅": 1.5, "傾向": 0.5, "穩": 0.0}[rating]
    turnout = round(tb + t_adj, 1)
    votes = round(elect * turnout / 100)
    valid = round(votes * (1 - inv))
    leader = max(winp, key=winp.get)
    lb = next(b for n, p, b, i in cands if n == leader)
    bw = [n for n, p, b, i in cands if b == "B"]
    gw = [n for n, p, b, i in cands if b == "G"]
    out_c.append(dict(week=WEEK, county=c, region=reg, order=order, population=POPULATION[c], leader_share=round(shares[leader], 4), electorate=elect, turnout=turnout / 100,
        turnout_lo=(turnout - 3) / 100, turnout_hi=(turnout + 3) / 100, votes=votes, valid=valid,
        rating=rating, leader=leader, leader_bloc={"B": "藍白", "G": "綠", "O": "其他"}[lb], leader_win=round(lead, 3),
        win_bw=round(sum(winp[n] for n in bw), 3), win_g=round(sum(winp[n] for n in gw), 3),
        win_other=round(1 - sum(winp[n] for n in bw + gw), 3),
        bw_share=round(sum(shares[n] for n in bw), 4), g_share=round(sum(shares[n] for n in gw), 4),
        bw_votes=round(sum(shares[n] for n in bw) * valid), g_votes=round(sum(shares[n] for n in gw) * valid),
        bw_mobil=round(sum(shares[n] for n in bw) * valid / elect, 4), g_mobil=round(sum(shares[n] for n in gw) * valid / elect, 4),
        bw_name="、".join(bw) or "未提名", g_name="、".join(gw) or "未提名",
        bw_camp=("白" if bw and bw[0] in WHITE else "藍") if bw else "",
        leader_camp=("白" if leader in WHITE else "藍") if lb == "B" else {"G": "綠", "O": "其他"}[lb],
        poll_class=cls, poll_weight=round(wp, 2), n_polls=len(v["ps"]),
        g_two=None if gfinal is None else round(gfinal, 4), sd=round(sd_c, 4), turn_k=round(turn_k, 5), turn_A=round(turn_A, 4), turn_B=MOBIL_B, manual=c in MANUAL, g24p=round(COUNTIES[c][7], 4),
        w22_name=RESULT22[c][0], w22_camp=RESULT22[c][1], g22=None if COUNTIES[c][6] is None else round(COUNTIES[c][6], 4),
        base_g=round(v["gb"], 4), poll_g=None if v["gp"] is None else round(v["gp"], 4), env=round(env_of(c), 4),
        adj_note="；".join(f"{t}（{a * ((1 - wp) / 0.4 if k == '派系' else 1):+.1f}）" for a, t, k in adjs if a) or "",
        note=NOTES.get(c, "")))
    for n, p, b, inc in cands:
        sh = shares[n]
        out_k.append(dict(week=WEEK, county=c, name=n, party=p, bloc={"B": "藍白", "G": "綠", "O": "其他"}[b], camp=("白" if n in WHITE else "藍") if b == "B" else {"G": "綠", "O": "其他"}[b], incumbent=bool(inc),
            share=round(sh, 4), share_lo=round(intervals[n][0], 4), share_hi=round(intervals[n][1], 4),
            votes=round(sh * valid), mobil=round(sh * valid / elect, 4), win=round(winp[n], 3)))
    for w, g, p in v["ps"]:
        county, org, date, n, sup, und, est, src = p
        out_p.append(dict(week=WEEK, county=c, pollster=org, date=date, sample=n, tier=TIER.get(org, 0.7), grade=grade_of(c, org, date)[0], grade_note=grade_of(c, org, date)[1],
            house=HOUSE.get(org, 0), support="、".join(f"{k} {s:g}%" for k, s in sup.items()), undecided=und / 100,
            g_two=round(g, 4), weight=round(w / sum(x for x, _, _ in v["ps"]), 3), source=src))
    # 未採計的民調也列出（例如 TVBS 非封關、超過 12 週）
for p in POLLS:
    county, org, date, n, sup, und, est, src = p
    if poll_weight(p) == 0:
        out_p.append(dict(week=WEEK, county=county, pollster=org, date=date, sample=n, tier=TIER.get(org, 0.7), grade=grade_of(county, org, date)[0], grade_note=grade_of(county, org, date)[1],
            house=HOUSE.get(org, 0), support="、".join(f"{k} {s:g}%" for k, s in sup.items()), undecided=und / 100,
            g_two=None, weight=0.0, source=src))

# 席次機率分布：同一次模擬裡各縣市的勝選陣營加總（全國誤差共用，所以各縣市會一起偏）
seat_dist = {}
for camp in ["藍", "白", "綠", "其他", "藍白"]:
    hist = [0] * (len(COUNTIES) + 1)
    for i in range(SIMS):
        hist[sum(1 for c in COUNTIES if SIMCAMP[c][i] in (("藍", "白") if camp == "藍白" else (camp,)))] += 1
    seat_dist[camp] = [round(h / SIMS, 4) for h in hist]
json.dump(dict(env=env, counties=out_c, candidates=out_k, polls=out_p, seat_dist=seat_dist), open(sys.argv[2] if len(sys.argv) > 2 else "out.json", "w"), ensure_ascii=False, indent=1)
print("全國風向", round(nat*100,1), {k: round(v*100,1) for k, v in REG_ENV.items()}, "無近期民調縣市外溢", SPILL*100)
for r in sorted(out_c, key=lambda r: r["order"]):
    print(f"{r['county']} {r['poll_class']:4} base {r['base_g']:.3f} poll {r['poll_g'] if r['poll_g'] is not None else '-':>6} | 藍白 {r['bw_name']} {r['bw_share']*100:5.1f}%  綠 {r['g_name']} {r['g_share']*100:5.1f}% | 領先 {r['leader']} {r['leader_win']*100:.0f}% {r['rating']} | 投票率 {r['turnout']*100:.1f}% 選舉人 {r['electorate']:,}")
