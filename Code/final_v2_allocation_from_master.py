"""Group 19 - 최종 재분배 분석 (총량 고정 버전)
사용법: python3 -I final_v2_allocation_from_master.py <입력폴더(최종분석)> <출력폴더>
입력: ttareungi_FINAL_master_with_supply_202509.csv
주의: 이 저장소는 현재 이 intermediate master를 Step 03에서 만드는 연결 단계까지는 재현한다고 주장하지 않는다.
"""
import sys, os
import numpy as np, pandas as pd

IN, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

# ---- 파라미터 (README에 그대로 기록) ----
U_MIN, U_MAX_BASE = 0.5, 24.0      # 회전율(대/일) 하한, 기본 상한
EXTREME_RATIO = 3.0                # 중앙 재고/거치대 >= 3 -> 데이터 확인 필요, 배분 풀에서 제외
SOFT_RATIO = 1.2                   # 중앙 재고/거치대 > 1.2 -> 거치대 초과 플래그
MATERIAL = 2                       # '강한 권고' 최소 이동 대수
UB_Q = 0.95                        # 유효 상한 = max(거치대, min(재고 95퍼센타일, 1.5x거치대))
UB_MULT = 1.5

m = pd.read_csv(f"{IN}/ttareungi_FINAL_master_with_supply_202509.csv")
m["weekpart"] = np.where(m.weekend == 1, "Weekend", "Weekday")
m["ratio"] = m.bikes_at_00 / m.capacity

# ---- 대여소 단위 플래그 ----
sf = m.groupby("station_id").agg(
    med_ratio=("ratio", "median"),
    rentals=("observed_rentals_final", "sum"),
    maxbikes=("bikes_at_00", "max"))
sf["inactive"] = (sf.rentals == 0) & (sf.maxbikes == 0)
sf["extreme"] = (sf.med_ratio >= EXTREME_RATIO) & ~sf.inactive

# ---- 대여소 x 평일/주말 집계 ----
add30 = m.baseline_additional_demand_30min.fillna(0)
m["_add30"] = add30
g = m.groupby(["station_id", "weekpart"])
t = g.agg(
    station_name=("station_name", "first"), district=("district", "first"), address=("address", "first"),
    days_observed=("date", "size"),
    D=("predicted_daily_demand_final", "mean"),
    add30=("_add30", "mean"),
    B=("bikes_at_00", "mean"),
    p95=("bikes_at_00", lambda x: x.quantile(UB_Q)),
    cap=("capacity", "first"),
    u_raw=("starting_stock_utilization", "first"),
    stockout_rate=("stockout_rate", "mean"),
    normal_days=("normal_days_weekpart", "first"),
    demand_source=("predicted_demand_source", "first"),
    util_source=("utilization_source", "first"),
    med_ratio_wp=("ratio", "median"),
).reset_index()
t = t.merge(sf[["med_ratio", "inactive", "extreme"]], left_on="station_id", right_index=True)
t["extreme"] = (t.extreme | (t.med_ratio_wp >= EXTREME_RATIO)) & ~t.inactive   # 평일/주말 단위로도 판정
t["U"] = np.maximum(t.cap, np.minimum(np.ceil(t.p95), np.ceil(UB_MULT * t.cap)))   # 유효 상한(소프트)
t["depot"] = t.station_name.str.contains("공공자전거 상암센터|자전거 수리센터", na=False)
t["status"] = np.where(t.inactive, "INACTIVE", np.where(t.depot, "DEPOT_OR_REPAIR", np.where(t.extreme, "CHECK_DATA", "ALLOCATED")))


def waterfill(need, ub, N):
    """sum(min(ub, lam*need)) = N 을 만족하는 연속 배분."""
    need = np.asarray(need, float); ub = np.asarray(ub, float)
    if ub is None or np.isinf(ub).all():
        return N * need / need.sum()
    if ub.sum() < N:
        raise ValueError("상한 합계가 보유량보다 작음")
    lo, hi = 0.0, float((ub / need).max()) * 1.0001
    for _ in range(200):
        mid = (lo + hi) / 2
        if np.minimum(ub, mid * need).sum() < N: lo = mid
        else: hi = mid
    return np.minimum(ub, hi * need)


def round_to_total(x, N, ub=None):
    """합계 N을 유지하는 정수화(최대잉여법)."""
    x = np.asarray(x, float)
    base = np.floor(x + 1e-9).astype(int)
    rem = int(N - base.sum())
    frac = x - base
    order = np.argsort(-frac)
    i = 0
    while rem > 0 and i < 10 * len(x):
        j = order[i % len(x)]
        if ub is None or base[j] < ub[j]:
            base[j] += 1; rem -= 1
        i += 1
    return base


res = []
sys_rows = []
for wp, d in t.groupby("weekpart"):
    pool = d[d.status == "ALLOCATED"].copy()
    N_f = pool.B.sum(); N = int(round(N_f))
    cur_int = round_to_total(pool.B.values, N)
    pool["current_int"] = cur_int

    def variant(u_max=U_MAX_BASE, demand="base", bound=True):
        u = np.clip(pool.u_raw.values, U_MIN, u_max if u_max else np.inf)
        Dv = pool.D.values + (pool.add30.values if demand == "plus30" else 0)
        need = Dv / u
        ub = pool.U.values if bound else np.full(len(pool), np.inf)
        return need, waterfill(need, ub, N)

    need0, t0 = variant()
    pool["need_S10"] = need0
    pool["target_cont"] = t0
    pool["target_bikes"] = round_to_total(t0, N, ub=pool.U.values)
    pool["move"] = pool.target_bikes - pool.current_int
    # 민감도(연속 목표 - 현재 재고)
    pool["d_base"] = t0 - pool.B
    pool["d_u12"] = variant(u_max=12)[1] - pool.B
    pool["d_unone"] = variant(u_max=None)[1] - pool.B
    pool["d_plus30"] = variant(demand="plus30")[1] - pool.B
    pool["d_nobound"] = variant(bound=False)[1] - pool.B
    pool["d_h0"] = N * pool.D / pool.D.sum() - pool.B      # H0: 수요 비례(공통 회전율)
    pool["binding"] = pool.target_bikes >= pool.U
    sys_rows.append(dict(
        weekpart=wp, stations_total=len(d), inactive=int((d.status == "INACTIVE").sum()),
        check_data=int((d.status == "CHECK_DATA").sum()), depot_or_repair=int((d.status == "DEPOT_OR_REPAIR").sum()), allocated=len(pool),
        fleet_in_pool=N, need_at_safety_1_0=round(pool.need_S10.sum()),
        fleet_coverage_of_need=round(N / pool.need_S10.sum(), 3),
        sum_target=int(pool.target_bikes.sum()), sum_move=int(pool.move.sum()),
        bikes_to_move=int(pool.move.clip(lower=0).sum()),
        pct_fleet_moved=round(100 * pool.move.clip(lower=0).sum() / N, 1),
        n_add=int((pool.move > 0).sum()), n_remove=int((pool.move < 0).sum()), n_keep=int((pool.move == 0).sum()),
        n_capacity_binding=int(pool.binding.sum()),
        target_above_nominal_docks=int((pool.target_bikes > pool.cap).sum())))
    res.append(pool)

P = pd.concat(res)
excl = t[t.status != "ALLOCATED"].copy()

# ---- 민감도 기반 권고 강도 ----
dv = P[["d_base", "d_u12", "d_unone", "d_plus30", "d_nobound"]]
same_pos = (dv >= MATERIAL).all(axis=1)
same_neg = (dv <= -MATERIAL).all(axis=1)
agree_pos = (dv > 0).sum(axis=1)
agree_neg = (dv < 0).sum(axis=1)
P["strength"] = np.where(same_pos | same_neg, "STRONG",
                 np.where((agree_pos >= 4) | (agree_neg >= 4), "MODERATE", "WEAK"))
P["action"] = np.where(P.move > 0, "ADD", np.where(P.move < 0, "REMOVE", "KEEP"))

def flags(r):
    f = []
    if r.demand_source != "historical_baseline": f.append("DEMAND_FALLBACK")
    if r.util_source == "system_median": f.append("TURNOVER_SYSTEM_MEDIAN")
    if r.normal_days < 5: f.append("FEW_NORMAL_DAYS")
    if r.med_ratio > SOFT_RATIO: f.append("STOCK_EXCEEDS_DOCKS")
    if r.u_raw > U_MAX_BASE: f.append("TURNOVER_CLIPPED")
    if r.target_bikes > r.cap: f.append("TARGET_ABOVE_NOMINAL_DOCKS")
    return ";".join(f)
P["data_flags"] = P.apply(flags, axis=1)
bad = P.data_flags.str.contains("DEMAND_FALLBACK|SYSTEM_MEDIAN|FEW_NORMAL|STOCK_EXCEEDS|TARGET_ABOVE", regex=True)
P["confidence"] = np.where((P.strength == "STRONG") & ~bad, "HIGH",
                   np.where(P.strength.isin(["STRONG", "MODERATE"]), "MEDIUM", "LOW"))
P.loc[P.data_flags.str.contains("TURNOVER_CLIPPED"), "confidence"] = "LOW"   # 일중 재배치 거점 가능성

# ---- 출력: 대여소 단위 ----
cols = dict(station_id="station_id", station_name="station_name", district="district", address="address", weekpart="weekpart")
out = pd.DataFrame({
    "station_id": P.station_id, "station_name": P.station_name, "district": P.district, "address": P.address,
    "weekpart": P.weekpart, "status": "ALLOCATED", "action": P.action,
    "recommended_move_bikes": P.move.astype(int), "confidence": P.confidence, "strength": P.strength,
    "current_bikes_at_00_mean": P.B.round(1), "current_bikes_int": P.current_int.astype(int),
    "target_bikes": P.target_bikes.astype(int), "nominal_docks": P.cap.astype(int), "effective_upper_bound": P.U.astype(int),
    "capacity_binding": P.binding, "avg_predicted_daily_demand": P.D.round(1),
    "turns_per_bike_raw": P.u_raw.round(2), "turns_per_bike_used": np.clip(P.u_raw, U_MIN, U_MAX_BASE).round(2),
    "need_at_safety_1_0": P.need_S10.round(1), "stockout_rate_mean": P.stockout_rate.round(3),
    "days_observed": P.days_observed, "normal_days_weekpart": P.normal_days.astype("Int64"),
    "demand_source": P.demand_source, "turnover_source": P.util_source,
    "stock_to_docks_median": P.med_ratio.round(2), "data_flags": P.data_flags,
    "delta_base": P.d_base.round(1), "delta_turns_cap12": P.d_u12.round(1), "delta_turns_nocap": P.d_unone.round(1),
    "delta_demand_plus30min": P.d_plus30.round(1), "delta_no_dock_bound": P.d_nobound.round(1),
    "delta_H0_demand_proportional": P.d_h0.round(1)})
ex = pd.DataFrame({
    "station_id": excl.station_id, "station_name": excl.station_name, "district": excl.district, "address": excl.address,
    "weekpart": excl.weekpart, "status": excl.status, "action": "EXCLUDED",
    "recommended_move_bikes": pd.NA, "confidence": "N/A", "strength": "N/A",
    "current_bikes_at_00_mean": excl.B.round(1), "nominal_docks": excl.cap.astype(int),
    "avg_predicted_daily_demand": excl.D.round(1), "stockout_rate_mean": excl.stockout_rate.round(3),
    "days_observed": excl.days_observed, "stock_to_docks_median": excl.med_ratio.round(2),
    "data_flags": np.select([excl.status == "INACTIVE", excl.status == "DEPOT_OR_REPAIR"], ["ZERO_RENTALS_ZERO_BIKES_ALL_MONTH", "DEPOT_OR_REPAIR_CENTER"], "STOCK_GE_3X_DOCKS_VERIFY_INVENTORY_OR_DOCK_COUNT")})
final = pd.concat([out, ex], ignore_index=True)
final = final.sort_values(["weekpart", "status", "recommended_move_bikes"], ascending=[True, True, False], na_position="last")
final.to_csv(f"{OUT}/ttareungi_FINAL_recommendations_v2_202509.csv", index=False, encoding="utf-8-sig")

# ---- 시스템 점검 ----
S = pd.DataFrame(sys_rows)
S.to_csv(f"{OUT}/ttareungi_FINAL_system_check_v2_202509.csv", index=False, encoding="utf-8-sig")

# ---- 구별 요약 ----
dist = P.groupby(["weekpart", "district"]).agg(
    stations=("station_id", "size"), net_move=("move", "sum"),
    bikes_in=("move", lambda x: x.clip(lower=0).sum()), bikes_out=("move", lambda x: -x.clip(upper=0).sum()),
    n_add=("move", lambda x: (x > 0).sum()), n_remove=("move", lambda x: (x < 0).sum()),
    n_high_conf=("confidence", lambda x: (x == "HIGH").sum()), current_bikes=("current_int", "sum"),
    target_bikes=("target_bikes", "sum")).reset_index()
dist.to_csv(f"{OUT}/ttareungi_FINAL_district_summary_v2_202509.csv", index=False, encoding="utf-8-sig")
print(S.T.to_string())
print(P.groupby("weekpart").confidence.value_counts().unstack())
print(P.groupby(["weekpart", "action"]).size().unstack())
print(P.strength.value_counts())