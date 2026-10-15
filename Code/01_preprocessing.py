# STEP 1 - PREPROCESSING
# Extracted and organized from the team's ACDT working notebook.


# ==================== ORIGINAL CELL 0 ====================
import pandas as pd
import numpy as np
import os
import re

# ============================================================
# 0. 파일 경로
# ============================================================

STOCK_FILE = "/content/data_2509.csv"

RENTAL_FILE = "/content/서울특별시 공공자전거 이용정보(시간대별)_202509.csv"

STATION_FILE = "/content/공공자전거 대여소 정보(25.6월 기준).xlsx"


# ============================================================
# 1. 파일 존재 확인
# ============================================================

for file in [STOCK_FILE, RENTAL_FILE, STATION_FILE]:
    print(file, "->", os.path.exists(file))


# ============================================================
# 2. CSV 인코딩 자동 읽기
# ============================================================

def read_csv_auto(path, **kwargs):

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp949",
        "euc-kr"
    ]

    for enc in encodings:
        try:
            df = pd.read_csv(
                path,
                encoding=enc,
                **kwargs
            )

            print(f"[OK] {os.path.basename(path)}")
            print(f"encoding = {enc}")

            return df

        except UnicodeDecodeError:
            continue

    raise ValueError(
        f"파일 인코딩을 읽지 못했습니다: {path}"
    )


# ============================================================
# 3. 컬럼명 자동 찾기 함수
# ============================================================

def normalize_col(x):

    return (
        str(x)
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .lower()
    )


def find_column(df, candidates):

    normalized = {
        normalize_col(col): col
        for col in df.columns
    }

    # 완전 일치
    for candidate in candidates:

        key = normalize_col(candidate)

        if key in normalized:
            return normalized[key]

    # 부분 일치
    for candidate in candidates:

        key = normalize_col(candidate)

        for ncol, original in normalized.items():

            if key in ncol:
                return original

    return None


# ============================================================
# 4. 데이터 읽기
# ============================================================

print("\n===== RENTAL DATA =====")

rental = read_csv_auto(
    RENTAL_FILE,
    low_memory=False
)

print(rental.columns.tolist())
print(rental.head())


print("\n===== STOCK DATA =====")

stock = read_csv_auto(
    STOCK_FILE,
    low_memory=False
)

print(stock.columns.tolist())
print(stock.head())


print("\n===== STATION DATA =====")

xls = pd.ExcelFile(STATION_FILE)

print("Sheets:", xls.sheet_names)

# 첫 번째 sheet 우선 사용
station = pd.read_excel(
    STATION_FILE,
    sheet_name=xls.sheet_names[0]
)

print(station.columns.tolist())
print(station.head())


# ============================================================
# 5. RENTAL DATA 컬럼 찾기
# ============================================================

rental_station_col = find_column(
    rental,
    [
        "대여소번호",
        "대여소 번호",
        "대여소ID"
    ]
)

rental_date_col = find_column(
    rental,
    [
        "대여일자",
        "대여일시",
        "대여날짜"
    ]
)

rental_hour_col = find_column(
    rental,
    [
        "대여시간",
        "대여 시간",
        "시간"
    ]
)

rental_count_col = find_column(
    rental,
    [
        "이용건수",
        "대여건수",
        "건수"
    ]
)


print("\n===== RENTAL COLUMNS FOUND =====")

print("station :", rental_station_col)
print("date    :", rental_date_col)
print("hour    :", rental_hour_col)
print("count   :", rental_count_col)


# ============================================================
# 6. Observed Demand 생성
# ============================================================

if rental_station_col is None:
    raise ValueError("대여량 데이터에서 대여소 번호 컬럼을 찾지 못함")

if rental_date_col is None:
    raise ValueError("대여량 데이터에서 날짜 컬럼을 찾지 못함")

if rental_count_col is None:
    raise ValueError("대여량 데이터에서 이용건수 컬럼을 찾지 못함")


rental[rental_date_col] = pd.to_datetime(
    rental[rental_date_col],
    errors="coerce"
)


# 날짜
rental["date"] = rental[rental_date_col].dt.date


# 시간
if rental_hour_col is not None:

    rental["hour"] = pd.to_numeric(
        rental[rental_hour_col],
        errors="coerce"
    )

else:

    rental["hour"] = rental[
        rental_date_col
    ].dt.hour


# 이용건수
rental["observed_demand"] = pd.to_numeric(
    rental[rental_count_col],
    errors="coerce"
).fillna(0)


observed = (
    rental
    .groupby(
        [
            rental_station_col,
            "date",
            "hour"
        ],
        as_index=False
    )["observed_demand"]
    .sum()
)


observed = observed.rename(
    columns={
        rental_station_col: "station_id"
    }
)


print("\n===== OBSERVED DEMAND =====")

print(observed.head())
print("rows =", len(observed))

# ============================================================
# 7~8. STOCK DATA 처리 - 실제 파일 컬럼 기준
# ============================================================

print("\n===== STOCK 실제 컬럼 =====")
print(stock.columns.tolist())


# ------------------------------------------------------------
# 실제 컬럼명 지정
# ------------------------------------------------------------

stock_station_col = "대여소번호"
stock_date_col = "일시"
stock_hour_col = "시간대"
stock_available_col = "거치대수량"


print("\n===== STOCK COLUMNS =====")
print("station   :", stock_station_col)
print("date      :", stock_date_col)
print("hour      :", stock_hour_col)
print("available :", stock_available_col)


# ============================================================
# 날짜 처리
# ============================================================

stock["date"] = pd.to_datetime(
    stock[stock_date_col],
    errors="coerce"
).dt.date


# ============================================================
# 시간 처리
# ============================================================

# 예:
# 8
# 08
# 8시
# 08시
# 모두 숫자 8로 변환
stock["hour"] = pd.to_numeric(
    stock[stock_hour_col]
    .astype(str)
    .str.extract(r"(\d{1,2})")[0],
    errors="coerce"
)


# ============================================================
# 대여가능 자전거 수
# ============================================================

stock["available_bikes"] = pd.to_numeric(
    stock[stock_available_col],
    errors="coerce"
)


# ============================================================
# Stockout proxy
# available bikes = 0 → stockout
# ============================================================

stock["stockout"] = (
    stock["available_bikes"] == 0
).astype(int)


# ============================================================
# station × date × hour 단위로 정리
# ============================================================

stock_hourly = (
    stock
    .groupby(
        [
            stock_station_col,
            "date",
            "hour"
        ],
        as_index=False
    )
    .agg(
        available_bikes=(
            "available_bikes",
            "mean"
        ),
        stockout=(
            "stockout",
            "max"
        )
    )
)


stock_hourly = stock_hourly.rename(
    columns={
        stock_station_col: "station_id"
    }
)


# ============================================================
# 확인
# ============================================================

print("\n===== STOCK HOURLY =====")
print(stock_hourly.head(10))

print("\n행 개수:")
print(len(stock_hourly))

print("\n날짜 범위:")
print(
    stock_hourly["date"].min(),
    "~",
    stock_hourly["date"].max()
)

print("\n시간 범위:")
print(
    stock_hourly["hour"].min(),
    "~",
    stock_hourly["hour"].max()
)

print("\nStockout 분포:")
print(
    stock_hourly["stockout"].value_counts()
)

print("\n결측치:")
print(
    stock_hourly.isna().sum()
)


# ============================================================
# 9. station_id 형식 통일
# ============================================================

def clean_station_id(series):

    return (
        series
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


observed["station_id"] = clean_station_id(
    observed["station_id"]
)

stock_hourly["station_id"] = clean_station_id(
    stock_hourly["station_id"]
)


# ============================================================
# 10. RENTAL + STOCK JOIN
# ============================================================

master = observed.merge(
    stock_hourly,
    on=[
        "station_id",
        "date",
        "hour"
    ],
    how="left"
)


print("\n===== RENTAL + STOCK =====")

print(master.head())

print(
    "stock match failure rate =",
    master["available_bikes"].isna().mean()
)


# ============================================================
# STATION FILE 헤더 복원
# ============================================================

import pandas as pd

xls = pd.ExcelFile(STATION_FILE)

print("시트:", xls.sheet_names)

# 우선 첫 번째 시트의 앞부분을 헤더 없이 확인
raw = pd.read_excel(
    STATION_FILE,
    sheet_name=xls.sheet_names[0],
    header=None,
    nrows=10
)

print("\n===== RAW FIRST 10 ROWS =====")
print(raw.to_string())

# ============================================================
# 14. 간단한 기본 통계
# ============================================================

print("\n===== BASIC STATISTICS =====")

print(
    master[
        [
            "observed_demand",
            "available_bikes",
            "stockout"
        ]
    ].describe()
)


print("\nStockout rate:")

print(
    master["stockout"].mean()
)


# ============================================================
# 15. CSV 저장
# ============================================================

OUTPUT_FILE = (
    "/content/ttareungi_202509_base.csv"
)

master.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)


print("\nSaved:")
print(OUTPUT_FILE)


# ==================== ORIGINAL CELL 1 ====================
# ============================================================
# 대여소 정보 정리 + master에 JOIN
# ============================================================

import re

def normalize_name(x):
    # 공백, 줄바꿈, 탭, _, - 전부 제거
    return re.sub(
        r'[\s_\-]+',
        '',
        str(x)
    ).lower()


def find_col(df, keyword_groups):

    for col in df.columns:

        normalized = normalize_name(col)

        for keywords in keyword_groups:

            if all(
                normalize_name(k) in normalized
                for k in keywords
            ):
                return col

    return None


# ============================================================
# 컬럼 다시 찾기
# ============================================================

station_id_col = find_col(
    station,
    [
        ["대여소", "번호"],
        ["대여소", "id"]
    ]
)

capacity_col = find_col(
    station,
    [
        ["거치대", "수"]
    ]
)

lat_col = find_col(
    station,
    [
        ["위도"],
        ["lat"]
    ]
)

lon_col = find_col(
    station,
    [
        ["경도"],
        ["lon"],
        ["longitude"]
    ]
)


print("===== STATION COLUMNS FOUND =====")
print("station_id :", repr(station_id_col))
print("capacity   :", repr(capacity_col))
print("lat        :", repr(lat_col))
print("lon        :", repr(lon_col))


print("\n===== 실제 전체 컬럼 =====")

for i, col in enumerate(station.columns):
    print(i, repr(col))


# ============================================================
# 필요한 대여소 정보 생성
# ============================================================

station_info = pd.DataFrame()

station_info["station_id"] = (
    station[station_id_col]
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)

station_info["lat"] = pd.to_numeric(
    station[lat_col],
    errors="coerce"
)

station_info["lon"] = pd.to_numeric(
    station[lon_col],
    errors="coerce"
)

if capacity_col is not None:
    station_info["capacity"] = pd.to_numeric(
        station[capacity_col],
        errors="coerce"
    )

station_info = (
    station_info
    .dropna(subset=["station_id", "lat", "lon"])
    .drop_duplicates(subset="station_id")
)


print("\n===== STATION INFO =====")
print(station_info.head())
print("대여소 수:", len(station_info))


# ============================================================
# master와 station_id 형식 통일
# ============================================================

master["station_id"] = (
    master["station_id"]
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)


# ============================================================
# JOIN
# ============================================================

master = master.merge(
    station_info,
    on="station_id",
    how="left"
)


print("\n===== FINAL MASTER =====")
print(master.head(10))

print("\n행 × 열:")
print(master.shape)

print("\n결측률:")
print(
    master.isna()
    .mean()
    .sort_values(ascending=False)
)


# ==================== ORIGINAL CELL 2 ====================
# ============================================================
# Ttareungi 2025-09 Base Dataset
#
# 1. 시간대별 대여량 -> observed_demand
# 2. 시간대별 대여가능 자전거수 -> available_bikes / stockout
# 3. 대여소 정보 -> lat / lon / capacity(가능한 경우)
#
# 최종 결과:
# /content/ttareungi_202509_base.csv
# ============================================================

import pandas as pd
import numpy as np
import os
import re
import gc


# ============================================================
# 0. 파일 경로
# ============================================================

STOCK_FILE = "/content/data_2509.csv"

RENTAL_FILE = (
    "/content/서울특별시 공공자전거 이용정보(시간대별)_202509.csv"
)

STATION_FILE = (
    "/content/공공자전거 대여소 정보(25.6월 기준).xlsx"
)

OUTPUT_FILE = (
    "/content/ttareungi_202509_base.csv"
)


# ============================================================
# 1. 파일 존재 확인
# ============================================================

print("===== FILE CHECK =====")

for f in [
    STOCK_FILE,
    RENTAL_FILE,
    STATION_FILE
]:

    exists = os.path.exists(f)

    print(
        os.path.basename(f),
        "->",
        exists
    )

    if not exists:
        raise FileNotFoundError(
            f"파일이 없습니다: {f}"
        )


# ============================================================
# 2. 공통 함수
# ============================================================

def normalize_name(x):

    return re.sub(
        r"[\s_\-\(\)]+",
        "",
        str(x)
    ).lower()


def find_col(df, keyword_groups):

    for col in df.columns:

        normalized = normalize_name(col)

        for keywords in keyword_groups:

            if all(
                normalize_name(k) in normalized
                for k in keywords
            ):
                return col

    return None


def clean_station_id(series):

    return (
        series
        .astype(str)
        .str.strip()
        .str.replace(
            r"\.0$",
            "",
            regex=True
        )
    )


def detect_encoding(path):

    for enc in [
        "utf-8-sig",
        "utf-8",
        "cp949",
        "euc-kr"
    ]:

        try:

            pd.read_csv(
                path,
                encoding=enc,
                nrows=5
            )

            print(
                f"[Encoding] "
                f"{os.path.basename(path)} "
                f"-> {enc}"
            )

            return enc

        except UnicodeDecodeError:
            continue

    raise ValueError(
        f"CSV 인코딩 확인 실패: {path}"
    )


def parse_date(series):

    s = (
        series
        .astype(str)
        .str.strip()
        .str.replace(
            r"\.0$",
            "",
            regex=True
        )
    )

    # 일반 날짜 형식
    result = pd.to_datetime(
        s,
        errors="coerce"
    )

    # 20250901 같은 형식
    mask = s.str.fullmatch(
        r"\d{8}"
    )

    if mask.any():

        result.loc[mask] = (
            pd.to_datetime(
                s.loc[mask],
                format="%Y%m%d",
                errors="coerce"
            )
        )

    return result


def parse_hour(series):

    extracted = (
        series
        .astype(str)
        .str.extract(
            r"(\d{1,2})"
        )[0]
    )

    return pd.to_numeric(
        extracted,
        errors="coerce"
    )


# ============================================================
# 3. CSV Encoding
# ============================================================

RENTAL_ENCODING = detect_encoding(
    RENTAL_FILE
)

STOCK_ENCODING = detect_encoding(
    STOCK_FILE
)


# ============================================================
# 4. RENTAL 파일 컬럼 확인
# ============================================================

rental_sample = pd.read_csv(
    RENTAL_FILE,
    encoding=RENTAL_ENCODING,
    nrows=10
)


print("\n===== RENTAL COLUMNS =====")

for i, col in enumerate(
    rental_sample.columns
):
    print(i, repr(col))


rental_station_col = find_col(
    rental_sample,
    [
        ["대여소", "번호"],
        ["대여소", "id"]
    ]
)


rental_date_col = find_col(
    rental_sample,
    [
        ["대여", "일자"],
        ["대여", "일시"],
        ["일자"],
        ["날짜"]
    ]
)


rental_hour_col = find_col(
    rental_sample,
    [
        ["시간대"],
        ["대여", "시간"],
        ["시간"]
    ]
)


rental_count_col = find_col(
    rental_sample,
    [
        ["이용", "건수"],
        ["대여", "건수"],
        ["건수"]
    ]
)


print("\n===== RENTAL COLUMNS FOUND =====")

print(
    "station :",
    repr(rental_station_col)
)

print(
    "date    :",
    repr(rental_date_col)
)

print(
    "hour    :",
    repr(rental_hour_col)
)

print(
    "count   :",
    repr(rental_count_col)
)


if rental_station_col is None:
    raise ValueError(
        "RENTAL 데이터에서 대여소번호를 찾지 못했습니다."
    )

if rental_date_col is None:
    raise ValueError(
        "RENTAL 데이터에서 날짜를 찾지 못했습니다."
    )

if rental_count_col is None:
    raise ValueError(
        "RENTAL 데이터에서 이용건수를 찾지 못했습니다."
    )


# ============================================================
# 5. RENTAL -> OBSERVED DEMAND
# ============================================================

print(
    "\n===== PROCESSING RENTAL DATA ====="
)


CHUNK_SIZE = 300000

rental_results = []


for chunk_num, chunk in enumerate(

    pd.read_csv(
        RENTAL_FILE,
        encoding=RENTAL_ENCODING,
        chunksize=CHUNK_SIZE,
        low_memory=False
    ),

    start=1
):

    dt = parse_date(
        chunk[rental_date_col]
    )


    if rental_hour_col is not None:

        hour = parse_hour(
            chunk[rental_hour_col]
        )

    else:

        hour = dt.dt.hour


    demand = pd.to_numeric(
        chunk[rental_count_col],
        errors="coerce"
    ).fillna(0)


    temp = pd.DataFrame({

        "station_id":
            clean_station_id(
                chunk[rental_station_col]
            ),

        "date":
            dt.dt.date,

        "hour":
            hour,

        "observed_demand":
            demand
    })


    temp = temp.dropna(
        subset=[
            "station_id",
            "date",
            "hour"
        ]
    )


    temp["hour"] = (
        temp["hour"]
        .astype(int)
    )


    grouped = (

        temp

        .groupby(
            [
                "station_id",
                "date",
                "hour"
            ],
            as_index=False
        )

        ["observed_demand"]

        .sum()

    )


    rental_results.append(
        grouped
    )


    print(
        f"Rental chunk "
        f"{chunk_num} 완료"
    )


observed = pd.concat(
    rental_results,
    ignore_index=True
)


observed = (

    observed

    .groupby(
        [
            "station_id",
            "date",
            "hour"
        ],
        as_index=False
    )

    ["observed_demand"]

    .sum()

)


del rental_results

gc.collect()


print(
    "\n===== OBSERVED DEMAND ====="
)

print(
    observed.head(10)
)

print(
    "행:",
    len(observed)
)

print(
    "대여소:",
    observed[
        "station_id"
    ].nunique()
)


# ============================================================
# 6. STOCK DATA
#
# 실제 네 파일에서 확인된 컬럼:
#
# 일시
# 대여소번호
# 대여소명
# 시간대
# 거치대수량
# ============================================================

stock_sample = pd.read_csv(
    STOCK_FILE,
    encoding=STOCK_ENCODING,
    nrows=10
)


print(
    "\n===== STOCK COLUMNS ====="
)

print(
    stock_sample.columns.tolist()
)


STOCK_DATE = "일시"
STOCK_STATION = "대여소번호"
STOCK_HOUR = "시간대"
STOCK_AVAILABLE = "거치대수량"


for col in [

    STOCK_DATE,
    STOCK_STATION,
    STOCK_HOUR,
    STOCK_AVAILABLE

]:

    if col not in stock_sample.columns:

        raise ValueError(
            f"STOCK 데이터에 "
            f"{col} 컬럼이 없습니다."
        )


# ============================================================
# 7. STOCK 처리
# ============================================================

print(
    "\n===== PROCESSING STOCK DATA ====="
)


stock_results = []


for chunk_num, chunk in enumerate(

    pd.read_csv(
        STOCK_FILE,
        encoding=STOCK_ENCODING,
        chunksize=CHUNK_SIZE,
        low_memory=False
    ),

    start=1
):

    dt = parse_date(
        chunk[STOCK_DATE]
    )


    hour = parse_hour(
        chunk[STOCK_HOUR]
    )


    available = pd.to_numeric(
        chunk[STOCK_AVAILABLE],
        errors="coerce"
    )


    temp = pd.DataFrame({

        "station_id":
            clean_station_id(
                chunk[STOCK_STATION]
            ),

        "date":
            dt.dt.date,

        "hour":
            hour,

        "available_bikes":
            available
    })


    temp = temp.dropna(
        subset=[
            "station_id",
            "date",
            "hour",
            "available_bikes"
        ]
    )


    temp["hour"] = (
        temp["hour"]
        .astype(int)
    )


    # 0대 = stockout
    temp["stockout"] = (
        temp["available_bikes"]
        == 0
    ).astype(int)


    # chunk 합칠 때 평균 계산용
    temp[
        "available_sum"
    ] = temp[
        "available_bikes"
    ]


    temp[
        "available_count"
    ] = 1


    grouped = (

        temp

        .groupby(
            [
                "station_id",
                "date",
                "hour"
            ],
            as_index=False
        )

        .agg(

            available_sum=(
                "available_sum",
                "sum"
            ),

            available_count=(
                "available_count",
                "sum"
            ),

            stockout=(
                "stockout",
                "max"
            )

        )

    )


    stock_results.append(
        grouped
    )


    print(
        f"Stock chunk "
        f"{chunk_num} 완료"
    )


stock_hourly = pd.concat(
    stock_results,
    ignore_index=True
)


stock_hourly = (

    stock_hourly

    .groupby(
        [
            "station_id",
            "date",
            "hour"
        ],
        as_index=False
    )

    .agg(

        available_sum=(
            "available_sum",
            "sum"
        ),

        available_count=(
            "available_count",
            "sum"
        ),

        stockout=(
            "stockout",
            "max"
        )

    )

)


stock_hourly[
    "available_bikes"
] = (

    stock_hourly[
        "available_sum"
    ]

    /

    stock_hourly[
        "available_count"
    ]

)


stock_hourly = stock_hourly[
    [
        "station_id",
        "date",
        "hour",
        "available_bikes",
        "stockout"
    ]
]


del stock_results

gc.collect()


print(
    "\n===== STOCK HOURLY ====="
)

print(
    stock_hourly.head(10)
)

print(
    "날짜:",
    stock_hourly[
        "date"
    ].min(),
    "~",
    stock_hourly[
        "date"
    ].max()
)

print(
    "시간:",
    stock_hourly[
        "hour"
    ].min(),
    "~",
    stock_hourly[
        "hour"
    ].max()
)


# ============================================================
# 8. STOCK + RENTAL JOIN
#
# stock 데이터 기준으로 LEFT JOIN
#
# 대여 기록 없는 시간은
# observed_demand = 0
# ============================================================

print(
    "\n===== JOIN STOCK + RENTAL ====="
)


master = stock_hourly.merge(

    observed,

    on=[
        "station_id",
        "date",
        "hour"
    ],

    how="left"

)


master[
    "observed_demand"
] = master[
    "observed_demand"
].fillna(0)


print(
    master.head(10)
)


print(
    "\n현재 행 수:",
    len(master)
)


# ============================================================
# 9. STATION EXCEL 원본으로 읽기
# ============================================================

print(
    "\n===== PROCESSING STATION DATA ====="
)


xls = pd.ExcelFile(
    STATION_FILE
)


# 가장 먼저 위도/경도 들어있는 시트를 찾음
raw = None
found_sheet = None
header_row = None


for sheet in xls.sheet_names:

    temp = pd.read_excel(
        STATION_FILE,
        sheet_name=sheet,
        header=None
    )


    for i in range(
        min(
            30,
            len(temp)
        )
    ):

        row_text = "".join(
            temp.iloc[i]
            .dropna()
            .astype(str)
            .tolist()
        )


        normalized = normalize_name(
            row_text
        )


        if (
            "위도" in normalized
            and
            "경도" in normalized
        ):

            raw = temp
            found_sheet = sheet
            header_row = i

            break


    if raw is not None:
        break


if raw is None:

    raise ValueError(
        "대여소 엑셀에서 "
        "위도/경도 헤더를 찾지 못했습니다."
    )


print(
    "사용 시트:",
    found_sheet
)

print(
    "헤더 행:",
    header_row
)


# ============================================================
# 10. STATION 헤더 복원
# ============================================================

upper_row = (

    raw.iloc[
        header_row - 1
    ]

    if header_row > 0

    else pd.Series(
        [None]
        *
        raw.shape[1]
    )

)


lower_row = raw.iloc[
    header_row
]


def clean_header(x):

    if pd.isna(x):
        return ""

    s = str(x).strip()

    if s.lower() == "nan":
        return ""

    return s


station_columns = []


for j in range(
    raw.shape[1]
):

    upper = clean_header(
        upper_row.iloc[j]
    )

    lower = clean_header(
        lower_row.iloc[j]
    )


    if upper and lower:

        if (
            normalize_name(upper)
            ==
            normalize_name(lower)
        ):

            name = lower

        else:

            name = (
                upper
                + " "
                + lower
            )


    elif lower:

        name = lower


    elif upper:

        name = upper


    else:

        name = (
            f"unknown_{j}"
        )


    station_columns.append(
        name
    )


# 헤더 다음 행부터 실제 데이터
station = raw.iloc[
    header_row + 1:
].copy()


station.columns = (
    station_columns
)


station = (
    station
    .reset_index(
        drop=True
    )
)


print(
    "\n===== STATION 복원 컬럼 ====="
)


for i, col in enumerate(
    station.columns
):

    print(
        i,
        repr(col)
    )


# ============================================================
# 11. 대여소 번호 컬럼 결정
#
# 자동 컬럼명이 계속 문제를 일으켰으므로
# 실제 파일 구조에 맞춰 첫 번째 열을 기본 사용
# ============================================================

station_id_col = (
    station.columns[0]
)


# 위도/경도는 이름으로 탐색
lat_col = find_col(
    station,
    [
        ["위도"],
        ["lat"]
    ]
)


lon_col = find_col(
    station,
    [
        ["경도"],
        ["lon"],
        ["longitude"]
    ]
)


if lat_col is None:

    raise ValueError(
        "대여소 파일에서 "
        "위도 컬럼을 찾지 못했습니다."
    )


if lon_col is None:

    raise ValueError(
        "대여소 파일에서 "
        "경도 컬럼을 찾지 못했습니다."
    )


print(
    "\n===== STATION COLUMN MAPPING ====="
)

print(
    "station_id:",
    repr(station_id_col)
)

print(
    "lat:",
    repr(lat_col)
)

print(
    "lon:",
    repr(lon_col)
)


print(
    "\n대여소번호 샘플:"
)

print(
    station[
        station_id_col
    ].head(10).tolist()
)


# ============================================================
# 12. capacity 컬럼 찾기
#
# LCD / QR 거치대수가 따로 있으면 둘을 합침
# ============================================================

capacity_candidates = []


for col in station.columns:

    n = normalize_name(
        col
    )

    if (
        "거치대" in n
        and
        "수" in n
    ):

        capacity_candidates.append(
            col
        )


print(
    "\n거치대 관련 컬럼:",
    capacity_candidates
)


# LCD / QR 형태를 우선 사용
specific_capacity_cols = [

    col

    for col in capacity_candidates

    if (
        "lcd"
        in normalize_name(col)

        or

        "qr"
        in normalize_name(col)
    )

]


if len(
    specific_capacity_cols
) > 0:

    capacity_columns = (
        specific_capacity_cols
    )

else:

    capacity_columns = (
        capacity_candidates
    )


# ============================================================
# 13. STATION INFO 생성
# ============================================================

station_info = pd.DataFrame()


station_info[
    "station_id"
] = clean_station_id(
    station[
        station_id_col
    ]
)


station_info[
    "lat"
] = pd.to_numeric(
    station[
        lat_col
    ],
    errors="coerce"
)


station_info[
    "lon"
] = pd.to_numeric(
    station[
        lon_col
    ],
    errors="coerce"
)


# capacity가 있으면 계산
if len(
    capacity_columns
) > 0:

    capacity_df = pd.DataFrame()


    for col in capacity_columns:

        capacity_df[col] = (
            pd.to_numeric(
                station[col],
                errors="coerce"
            )
            .fillna(0)
        )


    station_info[
        "capacity"
    ] = capacity_df.sum(
        axis=1
    )


    print(
        "capacity 계산에 사용:",
        capacity_columns
    )


else:

    print(
        "⚠️ 거치대수 컬럼을 "
        "찾지 못했습니다."
    )


# ============================================================
# 14. STATION INFO 정리
# ============================================================

station_info = (

    station_info

    .replace(
        {
            "nan": np.nan,
            "None": np.nan,
            "": np.nan
        }
    )

    .dropna(
        subset=[
            "station_id",
            "lat",
            "lon"
        ]
    )

    .drop_duplicates(
        subset="station_id"
    )

)


print(
    "\n===== STATION INFO ====="
)

print(
    station_info.head(10)
)

print(
    "대여소 수:",
    len(station_info)
)


# ============================================================
# 15. STATION JOIN
# ============================================================

master[
    "station_id"
] = clean_station_id(
    master[
        "station_id"
    ]
)


master = master.merge(

    station_info,

    on="station_id",

    how="left"

)


# ============================================================
# 16. 최종 검증
# ============================================================

print(
    "\n================================"
)

print(
    "FINAL CHECK"
)

print(
    "================================"
)


print(
    "\n행 × 열:",
    master.shape
)


print(
    "\n최종 컬럼:"
)

print(
    master.columns.tolist()
)


print(
    "\n앞 10행:"
)

print(
    master.head(10)
)


print(
    "\n위도 결측률:",
    master[
        "lat"
    ].isna().mean()
)


print(
    "경도 결측률:",
    master[
        "lon"
    ].isna().mean()
)


print(
    "위치정보 매칭률:",
    master[
        "lat"
    ].notna().mean()
)


if (
    "capacity"
    in master.columns
):

    print(
        "capacity 결측률:",
        master[
            "capacity"
        ].isna().mean()
    )


print(
    "\nObserved Demand:"
)

print(
    master[
        "observed_demand"
    ].describe()
)


print(
    "\nAvailable Bikes:"
)

print(
    master[
        "available_bikes"
    ].describe()
)


print(
    "\nStockout:"
)

print(
    master[
        "stockout"
    ].value_counts()
)


print(
    "\nStockout rate:"
)

print(
    master[
        "stockout"
    ].mean()
)


# ============================================================
# 17. 이상값 간단 확인
# ============================================================

print(
    "\n===== DATA QUALITY CHECK ====="
)


print(
    "날짜 범위:",
    master[
        "date"
    ].min(),
    "~",
    master[
        "date"
    ].max()
)


print(
    "시간 범위:",
    master[
        "hour"
    ].min(),
    "~",
    master[
        "hour"
    ].max()
)


print(
    "대여소 수:",
    master[
        "station_id"
    ].nunique()
)


print(
    "Observed demand 음수:",
    (
        master[
            "observed_demand"
        ]
        < 0
    ).sum()
)


print(
    "Available bikes 음수:",
    (
        master[
            "available_bikes"
        ]
        < 0
    ).sum()
)


# ============================================================
# 18. 저장
# ============================================================

master.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)


print(
    "\n================================"
)

print(
    "✅ 기본 분석 데이터 생성 완료"
)

print(
    OUTPUT_FILE
)

print(
    "================================"
)


# ==================== ORIGINAL CELL 3 ====================
# ============================================================
# 2025년 9월 생활인구 30일 전처리 - 오류 대응 버전
#
# /content/Local_people_202509/
#     일별 CSV 30개
#
# 필요한 것만 추출:
# - 시간대구분
# - 집계구코드
# - 총생활인구수
#
# 성별 / 연령별 컬럼은 읽지 않음
#
# 최종:
# 집계구 × 날짜
# ============================================================

import pandas as pd
import numpy as np
import os
import re
import csv
import gc


# ============================================================
# 1. 폴더 찾기
# ============================================================

FOLDER = "/content/Local_people_202509"

if not os.path.isdir(FOLDER):

    # 대소문자가 다를 경우 자동 탐색
    FOLDER = None

    for name in os.listdir("/content"):

        path = os.path.join("/content", name)

        if (
            os.path.isdir(path)
            and
            "localpeople202509"
            in re.sub(r"[\s_\-]", "", name.lower())
        ):
            FOLDER = path
            break


if FOLDER is None:

    raise FileNotFoundError(
        "Local_people_202509 폴더를 찾지 못했습니다."
    )


print("생활인구 폴더:")
print(FOLDER)


# ============================================================
# 2. CSV 30개 찾기
# ============================================================

FILES = []

for root, dirs, filenames in os.walk(FOLDER):

    for filename in filenames:

        if filename.lower().endswith(".csv"):

            FILES.append(
                os.path.join(
                    root,
                    filename
                )
            )


FILES = sorted(FILES)


print("\nCSV 파일 수:", len(FILES))

for f in FILES[:5]:
    print(os.path.basename(f))


if len(FILES) == 0:

    raise FileNotFoundError(
        "CSV 파일이 없습니다."
    )


# ============================================================
# 3. 공통 함수
# ============================================================

def normalize(x):

    x = str(x)

    # 따옴표 제거
    x = x.replace('"', "")
    x = x.replace("'", "")

    # 공백 등 제거
    x = re.sub(
        r"[\s_\-\(\)]",
        "",
        x
    )

    return x.lower()


def detect_encoding(path):

    for enc in [
        "utf-8-sig",
        "utf-8",
        "cp949",
        "euc-kr"
    ]:

        try:

            pd.read_csv(
                path,
                encoding=enc,
                nrows=1,
                quoting=csv.QUOTE_NONE
            )

            return enc

        except Exception:
            continue

    raise ValueError(
        f"Encoding 확인 실패: {path}"
    )


def find_index(columns, keyword_groups):

    for index, col in enumerate(columns):

        c = normalize(col)

        for group in keyword_groups:

            if all(
                normalize(k) in c
                for k in group
            ):

                return index

    return None


# ============================================================
# 4. 시간대 평균 함수
# ============================================================

def time_average(
    df,
    start_hour,
    end_hour,
    output_name
):

    result = (

        df[
            df["hour"].between(
                start_hour,
                end_hour
            )
        ]

        .groupby(
            "area_id",
            as_index=False
        )

        ["population"]

        .mean()

        .rename(
            columns={
                "population":
                    output_name
            }
        )

    )

    return result


# ============================================================
# 5. 전체 날짜 처리
# ============================================================

ALL_DAYS = []

SUCCESS_DAYS = []

FAILED_FILES = []


for file_number, file_path in enumerate(
    FILES,
    start=1
):

    filename = os.path.basename(
        file_path
    )


    # --------------------------------------------------------
    # 날짜 추출
    # --------------------------------------------------------

    match = re.search(
        r"202509\d{2}",
        filename
    )


    if match is None:

        print(
            "⚠️ 날짜 추출 실패:",
            filename
        )

        FAILED_FILES.append(filename)

        continue


    current_date = pd.to_datetime(
        match.group(),
        format="%Y%m%d"
    )


    print(
        f"\n[{file_number:02d}/{len(FILES)}] "
        f"{current_date.date()} 처리 중..."
    )


    try:

        # ====================================================
        # 6. 파일마다 Encoding 확인
        # ====================================================

        encoding = detect_encoding(
            file_path
        )


        # ====================================================
        # 7. 헤더만 읽기
        #
        # QUOTE_NONE을 쓰되
        # 여기서는 실제 컬럼명 대신 위치를 확인
        # ====================================================

        header_df = pd.read_csv(
            file_path,
            encoding=encoding,
            nrows=0,
            quoting=csv.QUOTE_NONE
        )


        raw_columns = list(
            header_df.columns
        )


        # ----------------------------------------------------
        # 필요한 컬럼 위치 탐색
        # ----------------------------------------------------

        hour_idx = find_index(
            raw_columns,
            [
                ["시간대구분"],
                ["시간대"],
                ["시간"]
            ]
        )


        area_idx = find_index(
            raw_columns,
            [
                ["집계구코드"],
                ["집계구", "코드"],
                ["집계구"]
            ]
        )


        pop_idx = find_index(
            raw_columns,
            [
                ["총생활인구수"],
                ["총", "생활인구"],
                ["생활인구수"]
            ]
        )


        print(
            "  시간 컬럼:",
            hour_idx,
            repr(
                raw_columns[hour_idx]
                if hour_idx is not None
                else None
            )
        )

        print(
            "  집계구 컬럼:",
            area_idx,
            repr(
                raw_columns[area_idx]
                if area_idx is not None
                else None
            )
        )

        print(
            "  인구 컬럼:",
            pop_idx,
            repr(
                raw_columns[pop_idx]
                if pop_idx is not None
                else None
            )
        )


        if (
            hour_idx is None
            or
            area_idx is None
            or
            pop_idx is None
        ):

            raise ValueError(
                "필요한 컬럼 위치를 찾지 못함"
            )


        # ====================================================
        # 8. 컬럼 이름 대신 '번호'로 읽기
        #
        # 여기서 usecols 오류를 방지
        # ====================================================

        use_indices = [
            hour_idx,
            area_idx,
            pop_idx
        ]


        HOURLY_PARTS = []


        reader = pd.read_csv(
            file_path,

            encoding=encoding,

            usecols=use_indices,

            chunksize=200000,

            low_memory=False,

            quoting=csv.QUOTE_NONE,

            on_bad_lines="skip"
        )


        # ====================================================
        # 9. Chunk 처리
        # ====================================================

        for chunk in reader:

            # 선택된 컬럼 순서가 원본 순서를 따르므로
            # 위치에 따라 다시 실제 컬럼을 찾아냄

            chunk_columns = list(
                chunk.columns
            )


            # 따옴표를 포함한 실제 컬럼명 대응

            hour_col = None
            area_col = None
            pop_col = None


            for col in chunk_columns:

                c = normalize(col)


                if (
                    hour_col is None
                    and
                    (
                        "시간대구분" in c
                        or
                        "시간대" in c
                    )
                ):
                    hour_col = col


                if (
                    area_col is None
                    and
                    "집계구" in c
                ):
                    area_col = col


                if (
                    pop_col is None
                    and
                    "생활인구" in c
                    and
                    (
                        "총" in c
                        or
                        c == "생활인구수"
                    )
                ):
                    pop_col = col


            if (
                hour_col is None
                or
                area_col is None
                or
                pop_col is None
            ):

                raise ValueError(
                    "Chunk에서 컬럼 매칭 실패"
                )


            temp = pd.DataFrame()


            # ----------------------------------------------
            # 시간
            # ----------------------------------------------

            temp["hour"] = pd.to_numeric(

                chunk[hour_col]
                .astype(str)
                .str.replace(
                    '"',
                    '',
                    regex=False
                )
                .str.extract(
                    r"(\d{1,2})"
                )[0],

                errors="coerce"

            )


            # ----------------------------------------------
            # 집계구 코드
            # ----------------------------------------------

            temp["area_id"] = (

                chunk[area_col]
                .astype(str)
                .str.replace(
                    '"',
                    '',
                    regex=False
                )
                .str.strip()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True
                )

            )


            # ----------------------------------------------
            # 총생활인구
            # ----------------------------------------------

            temp["population"] = pd.to_numeric(

                chunk[pop_col]
                .astype(str)
                .str.replace(
                    '"',
                    '',
                    regex=False
                )
                .str.strip(),

                errors="coerce"

            )


            # ----------------------------------------------
            # 결측 제거
            # ----------------------------------------------

            temp = temp.dropna(
                subset=[
                    "hour",
                    "area_id",
                    "population"
                ]
            )


            temp["hour"] = (
                temp["hour"]
                .astype(int)
            )


            # 0~23만
            temp = temp[
                temp["hour"].between(
                    0,
                    23
                )
            ]


            # ----------------------------------------------
            # 동일 집계구 × 시간 중복 압축
            # ----------------------------------------------

            temp = (

                temp

                .groupby(
                    [
                        "area_id",
                        "hour"
                    ],
                    as_index=False
                )

                ["population"]

                .sum()

            )


            HOURLY_PARTS.append(
                temp
            )


        # ====================================================
        # 10. 해당 날짜 전체 합치기
        # ====================================================

        if len(HOURLY_PARTS) == 0:

            raise ValueError(
                "읽힌 데이터가 없음"
            )


        day_hourly = pd.concat(
            HOURLY_PARTS,
            ignore_index=True
        )


        day_hourly = (

            day_hourly

            .groupby(
                [
                    "area_id",
                    "hour"
                ],
                as_index=False
            )

            ["population"]

            .sum()

        )


        # ====================================================
        # 11. 필요한 시간대만 계산
        # ====================================================

        # 출근 07~09
        morning = time_average(
            day_hourly,
            7,
            9,
            "morning_population"
        )


        # 낮 10~16
        daytime = time_average(
            day_hourly,
            10,
            16,
            "daytime_population"
        )


        # 퇴근/저녁 17~20
        evening = time_average(
            day_hourly,
            17,
            20,
            "evening_population"
        )


        # 야간 21~23
        night = time_average(
            day_hourly,
            21,
            23,
            "night_population"
        )


        # ====================================================
        # 12. 07~23 평균
        #
        # 새벽 시간은 제외
        # ====================================================

        daily_avg = (

            day_hourly[
                day_hourly["hour"].between(
                    7,
                    23
                )
            ]

            .groupby(
                "area_id",
                as_index=False
            )

            ["population"]

            .mean()

            .rename(
                columns={
                    "population":
                        "daily_avg_population_07_23"
                }
            )

        )


        # ====================================================
        # 13. 결합
        # ====================================================

        day_result = (

            daily_avg

            .merge(
                morning,
                on="area_id",
                how="left"
            )

            .merge(
                daytime,
                on="area_id",
                how="left"
            )

            .merge(
                evening,
                on="area_id",
                how="left"
            )

            .merge(
                night,
                on="area_id",
                how="left"
            )

        )


        day_result.insert(
            1,
            "date",
            current_date
        )


        ALL_DAYS.append(
            day_result
        )


        SUCCESS_DAYS.append(
            current_date
        )


        print(
            f"  ✅ 완료: "
            f"{len(day_result):,}개 집계구"
        )


        del HOURLY_PARTS
        del day_hourly

        gc.collect()


    except Exception as e:

        print(
            "  ❌ 처리 실패:"
        )

        print(
            "  ",
            type(e).__name__,
            ":",
            e
        )

        FAILED_FILES.append(
            filename
        )


# ============================================================
# 14. 결과 확인
# ============================================================

print("\n================================")
print("처리 결과")
print("================================")

print(
    "성공 날짜:",
    len(SUCCESS_DAYS)
)

print(
    "실패 파일:",
    len(FAILED_FILES)
)


if FAILED_FILES:

    for f in FAILED_FILES:
        print(" -", f)


if len(ALL_DAYS) == 0:

    raise ValueError(
        "처리에 성공한 날짜가 없습니다."
    )


# ============================================================
# 15. 30일 합치기
# ============================================================

local_people_clean = pd.concat(
    ALL_DAYS,
    ignore_index=True
)


local_people_clean = (

    local_people_clean

    .sort_values(
        [
            "date",
            "area_id"
        ]
    )

    .reset_index(
        drop=True
    )

)


# ============================================================
# 16. 품질검사
# ============================================================

print("\n================================")
print("FINAL CHECK")
print("================================")


print(
    "날짜 수:",
    local_people_clean[
        "date"
    ].nunique()
)


print(
    "총 행:",
    len(local_people_clean)
)


print(
    "집계구 수:",
    local_people_clean[
        "area_id"
    ].nunique()
)


print(
    "\n날짜별 집계구 수:"
)


date_counts = (

    local_people_clean

    .groupby(
        "date"
    )

    ["area_id"]

    .nunique()

)


print(
    date_counts
)


print(
    "\n앞 10행:"
)

print(
    local_people_clean.head(10)
)


print(
    "\n결측률:"
)

print(
    local_people_clean
    .isna()
    .mean()
)


# ============================================================
# 17. 저장
# ============================================================

OUTPUT_FILE = (
    "/content/"
    "local_people_202509_preprocessed.csv"
)


local_people_clean.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)


print("\n================================")
print("✅ 전처리 완료")
print(OUTPUT_FILE)
print("================================")


# ==================== ORIGINAL CELL 4 ====================
#원본 데이터 점검
import os
import re
import pandas as pd

FOLDER = "/content/LOCAL_PEOPLE_202509"

result = []

for filename in sorted(os.listdir(FOLDER)):

    if not filename.lower().endswith(".csv"):
        continue

    path = os.path.join(FOLDER, filename)

    match = re.search(r"202509\d{2}", filename)

    if match is None:
        continue

    result.append({
        "date": match.group(),
        "size_MB": round(
            os.path.getsize(path) / 1024**2,
            2
        )
    })

size_check = pd.DataFrame(result)

print(size_check.to_string(index=False))


# ==================== ORIGINAL CELL 5 ====================
import pandas as pd

FILE = "/content/local_people_202509_preprocessed.csv"

df = pd.read_csv(
    FILE,
    dtype={"area_id": str}
)

df["date"] = pd.to_datetime(df["date"])

print("===== FINAL QUALITY CHECK =====")

print("\n총 행:", len(df))
print("날짜 수:", df["date"].nunique())
print("집계구 수:", df["area_id"].nunique())

print(
    "날짜 범위:",
    df["date"].min(),
    "~",
    df["date"].max()
)

# area_id + date 중복
dup = df.duplicated(
    ["area_id", "date"]
).sum()

print("\narea_id + date 중복:", dup)

# 결측치
print("\n컬럼별 결측치 수:")
print(
    df.isna().sum()
)

print("\n컬럼별 결측률:")
print(
    (df.isna().mean() * 100).round(4)
)

# 날짜별 행 수
print("\n날짜별 집계구 수:")
print(
    df.groupby("date")["area_id"]
      .nunique()
)

# 각 area_id가 며칠 등장하는지
print("\narea_id 등장 일수 분포:")
print(
    df.groupby("area_id")
      .size()
      .value_counts()
      .sort_index()
)


# ==================== ORIGINAL CELL 6 ====================
# ============================================================
# 생활인구 공간결합
#
# 집계구 × 날짜
#       ↓
# 따릉이 대여소 500m buffer
#       ↓
# 대여소 × 날짜 생활인구
#
# 이후 따릉이 일별 데이터와 JOIN
# ============================================================

!pip -q install geopandas pyogrio shapely

import pandas as pd
import numpy as np
import geopandas as gpd

import os
import glob
import gc
import math


# ============================================================
# 0. 파일
# ============================================================

POP_FILE = "/content/local_people_202509_preprocessed.csv"

BIKE_FILE = "/content/ttareungi_202509_base.csv"

OUTPUT_POP = (
    "/content/"
    "station_population_202509.csv"
)

OUTPUT_DAILY = (
    "/content/"
    "ttareungi_daily_with_population_202509.csv"
)

BUFFER_M = 500


# ============================================================
# 1. 파일 존재 확인
# ============================================================

for f in [
    POP_FILE,
    BIKE_FILE
]:

    if not os.path.exists(f):

        raise FileNotFoundError(
            f"파일 없음: {f}"
        )


# ============================================================
# 2. 생활인구 데이터
# ============================================================

print("\n================================")
print("1. 생활인구 데이터")
print("================================")


pop = pd.read_csv(
    POP_FILE,
    dtype={
        "area_id": str
    }
)


pop["date"] = pd.to_datetime(
    pop["date"]
)


pop["area_id"] = (
    pop["area_id"]
    .astype(str)
    .str.strip()
    .str.replace(
        r"\.0$",
        "",
        regex=True
    )
)


POP_COLS = [

    "daily_avg_population_07_23",

    "morning_population",

    "daytime_population",

    "evening_population",

    "night_population"

]


for col in POP_COLS:

    pop[col] = pd.to_numeric(
        pop[col],
        errors="coerce"
    )


print(
    "생활인구 행:",
    len(pop)
)

print(
    "집계구:",
    pop["area_id"].nunique()
)

print(
    "날짜:",
    pop["date"].nunique()
)

print(
    pop.head()
)


# ============================================================
# 3. 따릉이 데이터
# ============================================================

print("\n================================")
print("2. 따릉이 데이터")
print("================================")


bike = pd.read_csv(
    BIKE_FILE,
    dtype={
        "station_id": str
    },
    low_memory=False
)


bike["station_id"] = (
    bike["station_id"]
    .astype(str)
    .str.strip()
    .str.replace(
        r"\.0$",
        "",
        regex=True
    )
)


bike["date"] = pd.to_datetime(
    bike["date"]
)


bike["lat"] = pd.to_numeric(
    bike["lat"],
    errors="coerce"
)


bike["lon"] = pd.to_numeric(
    bike["lon"],
    errors="coerce"
)


# 대여소 위치만 1개씩 추출

stations = (

    bike[
        [
            "station_id",
            "lat",
            "lon"
        ]
    ]

    .dropna()

    .drop_duplicates(
        subset="station_id"
    )

    .copy()

)


print(
    "대여소 수:",
    len(stations)
)

print(
    stations.head()
)


# ============================================================
# 4. /content 안의 모든 SHP 찾기
# ============================================================

print("\n================================")
print("3. 집계구 SHP 자동 탐색")
print("================================")


SHP_FILES = glob.glob(

    "/content/집계구shp",

    recursive=True

)


print(
    "발견된 SHP:",
    len(SHP_FILES)
)


for f in SHP_FILES:

    print(
        "-",
        f
    )


if len(SHP_FILES) == 0:

    raise FileNotFoundError(
        """
집계구 SHP 파일이 없습니다.

.shp
.shx
.dbf
.prj

파일을 Colab에 올려주세요.
"""
    )


# ============================================================
# 5. 생활인구 area_id와 가장 잘 맞는 SHP 자동 탐색
# ============================================================

population_ids = set(
    pop["area_id"]
    .dropna()
    .unique()
)


best_shp = None
best_code_col = None
best_overlap = 0
best_match_rate = 0


for shp_path in SHP_FILES:

    print(
        "\n검사:",
        os.path.basename(shp_path)
    )

    try:

        # 속성만 읽음
        attr = gpd.read_file(
            shp_path,
            ignore_geometry=True
        )


        for col in attr.columns:

            values = (

                attr[col]

                .astype(str)

                .str.strip()

                .str.replace(
                    r"\.0$",
                    "",
                    regex=True
                )

            )


            shp_ids = set(
                values.dropna()
            )


            overlap = len(
                population_ids
                &
                shp_ids
            )


            rate = (
                overlap
                /
                len(population_ids)
            )


            if overlap > best_overlap:

                best_overlap = overlap

                best_match_rate = rate

                best_shp = shp_path

                best_code_col = col


    except Exception as e:

        print(
            "  읽기 실패:",
            str(e)[:100]
        )


print("\n================================")

print(
    "선택된 SHP:",
    best_shp
)

print(
    "집계구 코드 컬럼:",
    best_code_col
)

print(
    "일치 집계구:",
    best_overlap,
    "/",
    len(population_ids)
)

print(
    "매칭률:",
    round(
        best_match_rate * 100,
        3
    ),
    "%"
)

print("================================")


# ============================================================
# 매우 중요
#
# 다른 연도의 집계구 경계를 잘못 사용하면
# 여기서 멈춤
# ============================================================

if (
    best_shp is None
    or
    best_match_rate < 0.80
):

    raise ValueError(
        """
생활인구 area_id와 잘 맞는 집계구 SHP를 찾지 못했습니다.

생활인구 CSV와 집계구 경계의 기준연도가
다를 가능성이 있습니다.

매칭률을 확인하고 올바른 집계구 SHP를 사용해야 합니다.
"""
    )


# ============================================================
# 6. 집계구 SHP 실제 로드
# ============================================================

areas = gpd.read_file(
    best_shp
)


areas["area_id"] = (

    areas[
        best_code_col
    ]

    .astype(str)

    .str.strip()

    .str.replace(
        r"\.0$",
        "",
        regex=True
    )

)


# 생활인구에 실제 존재하는 집계구만 유지

areas = areas[
    areas["area_id"].isin(
        population_ids
    )
].copy()


areas = areas[
    [
        "area_id",
        "geometry"
    ]
]


# 동일 area_id가 SHP에 여러 개 있으면 하나로 병합

areas = areas.dissolve(

    by="area_id",

    as_index=False

)


print(
    "\nSHP 집계구:",
    len(areas)
)


# ============================================================
# 7. 좌표계 확인
# ============================================================

print(
    "원본 CRS:",
    areas.crs
)


if areas.crs is None:

    raise ValueError(
        """
집계구 SHP에 CRS 정보가 없습니다.
.prj 파일이 함께 업로드되었는지 확인하세요.
"""
    )


# 서울 미터 단위 좌표계
# EPSG:5179 사용

areas = areas.to_crs(
    epsg=5179
)


# geometry 오류 보정

try:

    areas["geometry"] = (
        areas.geometry.make_valid()
    )

except:

    pass


areas = areas[
    ~areas.geometry.is_empty
].copy()


areas[
    "area_size_m2"
] = areas.geometry.area


# ============================================================
# 8. 따릉이 좌표 → GeoDataFrame
# ============================================================

station_gdf = gpd.GeoDataFrame(

    stations.copy(),

    geometry=gpd.points_from_xy(

        stations["lon"],

        stations["lat"]

    ),

    crs="EPSG:4326"

)


station_gdf = station_gdf.to_crs(
    epsg=5179
)


# ============================================================
# 9. 500m BUFFER
# ============================================================

buffers = station_gdf[
    [
        "station_id",
        "geometry"
    ]
].copy()


buffers[
    "geometry"
] = buffers.geometry.buffer(
    BUFFER_M
)


buffers[
    "buffer_area_m2"
] = buffers.geometry.area


print(
    "\n500m buffer 생성 완료"
)

print(
    "대여소:",
    len(buffers)
)


# ============================================================
# 10. 집계구 × 대여소 BUFFER 교차
# ============================================================

print("\n================================")
print("4. 공간 교차 계산")
print("시간이 조금 걸릴 수 있음")
print("================================")


intersection = gpd.overlay(

    buffers,

    areas,

    how="intersection",

    keep_geom_type=False

)


intersection[
    "overlap_area_m2"
] = intersection.geometry.area


# ============================================================
# 11. 집계구 중 몇 %가 buffer에 들어오는지 계산
# ============================================================

intersection[
    "area_weight"
] = (

    intersection[
        "overlap_area_m2"
    ]

    /

    intersection[
        "area_size_m2"
    ]

)


# floating point 때문에 1을 아주 살짝 넘을 경우 방지

intersection[
    "area_weight"
] = intersection[
    "area_weight"
].clip(
    lower=0,
    upper=1
)


weights = intersection[
    [
        "station_id",
        "area_id",
        "area_weight",
        "overlap_area_m2",
        "buffer_area_m2"
    ]
].copy()


print(
    "대여소-집계구 교차 관계:",
    len(weights)
)


print(
    "\n한 대여소가 평균 몇 개 집계구와 겹치는가:"
)

print(
    weights
    .groupby("station_id")
    ["area_id"]
    .nunique()
    .describe()
)


# ============================================================
# 12. BUFFER 공간 커버리지 계산
#
# buffer 전체 중 집계구 polygon이
# 얼마나 덮는지 검사
# ============================================================

coverage = (

    weights

    .groupby(
        "station_id",
        as_index=False
    )

    .agg(

        covered_area_m2=(
            "overlap_area_m2",
            "sum"
        ),

        buffer_area_m2=(
            "buffer_area_m2",
            "first"
        )

    )

)


coverage[
    "buffer_coverage_ratio"
] = (

    coverage[
        "covered_area_m2"
    ]

    /

    coverage[
        "buffer_area_m2"
    ]

)


print(
    "\nBuffer coverage:"
)

print(
    coverage[
        "buffer_coverage_ratio"
    ].describe()
)


# ============================================================
# 13. 날짜별 생활인구를 대여소 단위로 변환
#
# 메모리를 아끼기 위해
# 30일을 하나씩 처리
# ============================================================

print("\n================================")
print("5. 날짜별 생활인구 공간 가중")
print("================================")


DATES = sorted(
    pop["date"].unique()
)


station_day_results = []


for i, date in enumerate(
    DATES,
    start=1
):

    print(
        f"[{i:02d}/{len(DATES)}] "
        f"{pd.Timestamp(date).date()}"
    )


    day_pop = pop[
        pop["date"] == date
    ][
        [
            "area_id"
        ]
        +
        POP_COLS
    ].copy()


    # 대여소 × 집계구 공간 weight 붙이기

    temp = weights.merge(

        day_pop,

        on="area_id",

        how="left"

    )


    # ========================================================
    # Weighted Population
    # ========================================================

    for col in POP_COLS:

        temp[
            "weighted_" + col
        ] = (

            temp[col]

            *

            temp[
                "area_weight"
            ]

        )


    weighted_cols = [
        "weighted_" + c
        for c in POP_COLS
    ]


    result = (

        temp

        .groupby(
            "station_id",
            as_index=False
        )

        [weighted_cols]

        .sum(
            min_count=1
        )

    )


    result = result.rename(
        columns={

            "weighted_" + c:
            c

            for c in POP_COLS

        }
    )


    result[
        "date"
    ] = pd.Timestamp(
        date
    )


    station_day_results.append(
        result
    )


    del day_pop
    del temp
    del result

    gc.collect()


# ============================================================
# 14. 대여소 × 날짜 생활인구 완성
# ============================================================

station_population = pd.concat(

    station_day_results,

    ignore_index=True

)


station_population = station_population.merge(

    coverage[
        [
            "station_id",
            "buffer_coverage_ratio"
        ]
    ],

    on="station_id",

    how="left"

)


station_population = (

    station_population

    .sort_values(
        [
            "station_id",
            "date"
        ]
    )

    .reset_index(
        drop=True
    )

)


print("\n================================")
print("6. STATION POPULATION CHECK")
print("================================")


print(
    station_population.head(20)
)


print(
    "\n행:",
    len(station_population)
)


print(
    "대여소:",
    station_population[
        "station_id"
    ].nunique()
)


print(
    "날짜:",
    station_population[
        "date"
    ].nunique()
)


print(
    "\n결측률:"
)

print(
    station_population
    .isna()
    .mean()
)


# ============================================================
# 15. 저장
# ============================================================

station_population.to_csv(

    OUTPUT_POP,

    index=False,

    encoding="utf-8-sig"

)


print(
    "\n✅ 대여소별 생활인구 저장:"
)

print(
    OUTPUT_POP
)


# ============================================================
# 16. 따릉이 시간별 → 일별 집계
# ============================================================

print("\n================================")
print("7. 따릉이 일별 집계")
print("================================")


daily_agg = {

    "daily_observed_rentals":
        (
            "observed_demand",
            "sum"
        ),

    "avg_available_bikes":
        (
            "available_bikes",
            "mean"
        ),

    "stockout_observations":
        (
            "stockout",
            "sum"
        ),

    "hours_observed":
        (
            "hour",
            "count"
        ),

    "lat":
        (
            "lat",
            "first"
        ),

    "lon":
        (
            "lon",
            "first"
        )

}


if "capacity" in bike.columns:

    daily_agg[
        "capacity"
    ] = (
        "capacity",
        "first"
    )


bike_daily = (

    bike

    .groupby(
        [
            "station_id",
            "date"
        ],
        as_index=False
    )

    .agg(
        **daily_agg
    )

)


bike_daily[
    "stockout_rate"
] = (

    bike_daily[
        "stockout_observations"
    ]

    /

    bike_daily[
        "hours_observed"
    ]

)


# ============================================================
# 17. 따릉이 + 생활인구 JOIN
# ============================================================

final = bike_daily.merge(

    station_population,

    on=[
        "station_id",
        "date"
    ],

    how="left"

)


print("\n================================")
print("8. FINAL CHECK")
print("================================")


print(
    final.head(10)
)


print(
    "\n행 × 열:",
    final.shape
)


print(
    "\n생활인구 결측률:"
)

print(

    final[
        POP_COLS
    ]

    .isna()

    .mean()

)


print(
    "\n생활인구가 붙은 비율:"
)

print(

    final[
        "daily_avg_population_07_23"
    ]

    .notna()

    .mean()

)


# ============================================================
# 18. 저장
# ============================================================

final.to_csv(

    OUTPUT_DAILY,

    index=False,

    encoding="utf-8-sig"

)


print("\n================================")

print(
    "✅ 생활인구 결합 완료"
)

print(
    OUTPUT_DAILY
)

print("================================")


# ==================== ORIGINAL CELL 7 ====================
import pandas as pd
import geopandas as gpd
import os

# ============================================================
# 파일 경로
# ============================================================

SHP_FILE = "/content/집계구 격자 shp/grid_다사_500M.shp"
BUSINESS_FILE = "/content/사업체/2024년_사업체_다사_500M.csv"


# ============================================================
# 1. SHP 읽기
# ============================================================

grid = gpd.read_file(SHP_FILE)

print("================================")
print("SHP 정보")
print("================================")

print("행 수:", len(grid))
print("CRS:", grid.crs)
print("컬럼:", grid.columns.tolist())

print("\n앞 5행:")
print(grid.head())


# ============================================================
# 2. SHP의 각 컬럼 샘플
# ============================================================

print("\n===== SHP 컬럼 샘플 =====")

for col in grid.columns:

    if col == "geometry":
        continue

    print(
        f"\n[{col}]",
        grid[col]
        .astype(str)
        .head(10)
        .tolist()
    )


# ============================================================
# 3. 사업체 CSV encoding 확인
# ============================================================

encoding = None

for enc in [
    "utf-8-sig",
    "utf-8",
    "cp949",
    "euc-kr"
]:

    try:

        test = pd.read_csv(
            BUSINESS_FILE,
            encoding=enc,
            header=None,
            nrows=10
        )

        encoding = enc
        break

    except:
        pass


if encoding is None:

    raise ValueError(
        "사업체 CSV encoding 확인 실패"
    )


print("\n================================")
print("사업체 CSV")
print("================================")

print("Encoding:", encoding)


# ============================================================
# 4. 사업체 CSV 읽기
# ============================================================

business = pd.read_csv(
    BUSINESS_FILE,
    encoding=encoding,
    header=None,
    low_memory=False
)

print("shape:", business.shape)

print("\n앞 10행:")
print(business.head(10))


# ============================================================
# 5. 4열 구조이면 이름 부여
# ============================================================

if business.shape[1] == 4:

    business.columns = [
        "year",
        "GRID_CD",
        "stat_code",
        "value"
    ]

else:

    print(
        "\n⚠️ 예상한 4열 구조가 아님."
    )

    print(
        "컬럼 수:",
        business.shape[1]
    )


print("\n컬럼:")
print(business.columns.tolist())


# ============================================================
# 6. 사업체 격자 ID 확인
# ============================================================

business["GRID_CD"] = (
    business["GRID_CD"]
    .astype(str)
    .str.strip()
)


business["stat_code"] = (
    business["stat_code"]
    .astype(str)
    .str.strip()
)


print("\n사업체 GRID 예시:")

print(
    business[
        "GRID_CD"
    ]
    .drop_duplicates()
    .head(20)
    .tolist()
)


print("\n통계 코드 종류:")

print(
    business[
        "stat_code"
    ]
    .value_counts()
    .head(30)
)


# ============================================================
# 7. SHP에서 GRID_CD와 가장 잘 맞는 컬럼 자동 탐색
# ============================================================

business_ids = set(
    business[
        "GRID_CD"
    ]
    .dropna()
    .unique()
)


best_col = None
best_match = 0


for col in grid.columns:

    if col == "geometry":
        continue

    shp_ids = set(
        grid[col]
        .astype(str)
        .str.strip()
    )

    matched = len(
        business_ids
        &
        shp_ids
    )

    print(
        f"{col}: "
        f"{matched:,}개 일치"
    )

    if matched > best_match:

        best_match = matched
        best_col = col


# ============================================================
# 8. 결과
# ============================================================

print("\n================================")
print("GRID MATCH CHECK")
print("================================")

print(
    "사업체 GRID 수:",
    len(business_ids)
)

print(
    "최적 SHP 컬럼:",
    best_col
)

print(
    "일치 GRID:",
    best_match
)

print(
    "매칭률:",
    round(
        best_match
        /
        len(business_ids)
        * 100,
        3
    ),
    "%"
)


# ==================== ORIGINAL CELL 8 ====================
import pandas as pd
import geopandas as gpd
import numpy as np
import os

# ============================================================
# 파일 설정
# ============================================================

BIKE_FILE = "/content/ttareungi_daily_with_population_202509.csv"
BUSINESS_FILE = "/content/사업체/2024년_사업체_다사_500M.csv"
GRID_SHP = "/content/집계구 격자 shp/grid_다사_500M.shp"


TARGET_STAT = "to_fa_010"
BUFFER_M = 500

OUTPUT_STATION = "/content/station_business_500m.csv"
OUTPUT_FINAL = "/content/ttareungi_daily_with_population_business_202509.csv"


# ============================================================
# 1. 기존 따릉이 + 생활인구 데이터
# ============================================================

bike = pd.read_csv(
    BIKE_FILE,
    dtype={"station_id": str},
    low_memory=False
)

bike["station_id"] = (
    bike["station_id"]
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)

bike["lat"] = pd.to_numeric(
    bike["lat"],
    errors="coerce"
)

bike["lon"] = pd.to_numeric(
    bike["lon"],
    errors="coerce"
)

print("================================")
print("1. 따릉이")
print("================================")
print("station-day 행:", len(bike))
print("대여소:", bike["station_id"].nunique())


# 좌표 있는 대여소만 공간계산 가능
stations = (
    bike[
        ["station_id", "lat", "lon"]
    ]
    .dropna(subset=["lat", "lon"])
    .drop_duplicates("station_id")
    .copy()
)

print("좌표 있는 대여소:", len(stations))


# ============================================================
# 2. 사업체 CSV 읽기
# ============================================================

encoding = None

for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
    try:
        pd.read_csv(
            BUSINESS_FILE,
            encoding=enc,
            header=None,
            nrows=10
        )
        encoding = enc
        break
    except:
        pass

if encoding is None:
    raise ValueError("사업체 CSV 인코딩 확인 실패")

business = pd.read_csv(
    BUSINESS_FILE,
    encoding=encoding,
    header=None,
    names=[
        "year",
        "GRID_CD",
        "stat_code",
        "value"
    ],
    low_memory=False
)

business["GRID_CD"] = (
    business["GRID_CD"]
    .astype(str)
    .str.strip()
)

business["stat_code"] = (
    business["stat_code"]
    .astype(str)
    .str.strip()
)

business["year"] = pd.to_numeric(
    business["year"],
    errors="coerce"
)

business["value"] = pd.to_numeric(
    business["value"],
    errors="coerce"
)

# 2024년만
business = business[
    business["year"] == 2024
].copy()


print("\n================================")
print("2. 사업체")
print("================================")

print("통계코드 상위:")
print(
    business["stat_code"]
    .value_counts()
    .head(20)
)

print(
    "\nTARGET_STAT 존재 여부:",
    TARGET_STAT in business["stat_code"].unique()
)


if TARGET_STAT not in business["stat_code"].unique():
    raise ValueError(
        f"{TARGET_STAT} 코드가 없습니다. "
        "위 통계코드 목록을 확인하세요."
    )


# ============================================================
# 3. 사용할 사업체 통계항목
# ============================================================

business_target = (
    business[
        business["stat_code"] == TARGET_STAT
    ]
    .copy()
)

# 혹시 동일 grid 중복이 있으면 합계
business_grid = (
    business_target
    .groupby(
        "GRID_CD",
        as_index=False
    )
    ["value"]
    .sum(min_count=1)
    .rename(
        columns={
            "value": "business_count"
        }
    )
)

print(
    "\n사업체 통계가 있는 GRID:",
    business_grid["GRID_CD"].nunique()
)

print(
    "\n사업체 수 기초통계:"
)

print(
    business_grid["business_count"].describe()
)


# ============================================================
# 4. 500m 격자 SHP
# ============================================================

grid = gpd.read_file(
    GRID_SHP
)

print("\n================================")
print("3. GRID SHP")
print("================================")

print("CRS:", grid.crs)
print("격자 수:", len(grid))
print("컬럼:", grid.columns.tolist())


grid["GRID_CD"] = (
    grid["GRID_CD"]
    .astype(str)
    .str.strip()
)

# 필요한 컬럼만
grid = grid[
    ["GRID_CD", "geometry"]
].copy()


# ============================================================
# 5. CRS → EPSG:5179
# ============================================================

if grid.crs is None:
    raise ValueError("GRID SHP에 CRS가 없습니다.")

grid = grid.to_crs(
    epsg=5179
)

grid["grid_area_m2"] = (
    grid.geometry.area
)


# ============================================================
# 6. GRID + 사업체 결합
# ============================================================

grid = grid.merge(
    business_grid,
    on="GRID_CD",
    how="left"
)

print(
    "\nGRID에 사업체 값이 붙은 비율:",
    round(
        grid["business_count"]
        .notna()
        .mean() * 100,
        3
    ),
    "%"
)


# 주의:
# 사업체 CSV에 아예 행이 없는 GRID를 무조건 0으로
# 만들지는 않고 일단 NaN 유지
# 실제 데이터 커버리지 확인 후 판단
# ============================================================


# ============================================================
# 7. 따릉이 대여소 → 공간데이터
# ============================================================

station_gdf = gpd.GeoDataFrame(
    stations.copy(),
    geometry=gpd.points_from_xy(
        stations["lon"],
        stations["lat"]
    ),
    crs="EPSG:4326"
)

station_gdf = station_gdf.to_crs(
    epsg=5179
)


# ============================================================
# 8. 대여소 500m BUFFER
# ============================================================

buffers = station_gdf[
    ["station_id", "geometry"]
].copy()

buffers["geometry"] = (
    buffers.geometry.buffer(
        BUFFER_M
    )
)

buffers["buffer_area_m2"] = (
    buffers.geometry.area
)

print(
    "\n대여소 buffer:",
    len(buffers)
)


# ============================================================
# 9. BUFFER × GRID 교차
# ============================================================

print("\n================================")
print("4. 공간교차 시작")
print("================================")

inter = gpd.overlay(
    buffers,
    grid,
    how="intersection",
    keep_geom_type=False
)

inter["overlap_area_m2"] = (
    inter.geometry.area
)


# ============================================================
# 10. 격자 면적비
#
# 예:
# 한 격자의 30%가 station buffer에 들어오면
# 그 격자 사업체의 30%를 배정
# ============================================================

inter["grid_weight"] = (
    inter["overlap_area_m2"]
    /
    inter["grid_area_m2"]
)

inter["grid_weight"] = (
    inter["grid_weight"]
    .clip(0, 1)
)


# ============================================================
# 11. 면적가중 사업체 수
# ============================================================

inter["weighted_business"] = (
    inter["business_count"]
    *
    inter["grid_weight"]
)


# ============================================================
# 12. 대여소별 집계
# ============================================================

station_business = (
    inter
    .groupby(
        "station_id",
        as_index=False
    )
    .agg(
        business_count_500m=(
            "weighted_business",
            "sum"
        ),
        covered_area_m2=(
            "overlap_area_m2",
            "sum"
        ),
        buffer_area_m2=(
            "buffer_area_m2",
            "first"
        )
    )
)


# ============================================================
# 13. Coverage
# ============================================================

station_business[
    "business_buffer_coverage_ratio"
] = (
    station_business["covered_area_m2"]
    /
    station_business["buffer_area_m2"]
)

station_business[
    "business_buffer_coverage_ratio"
] = (
    station_business[
        "business_buffer_coverage_ratio"
    ]
    .clip(0, 1)
)


# ============================================================
# 14. 사업체 밀도
#
# covered area 기준으로 계산
# ============================================================

station_business[
    "covered_area_km2"
] = (
    station_business["covered_area_m2"]
    /
    1_000_000
)

station_business[
    "business_density_per_km2"
] = (
    station_business["business_count_500m"]
    /
    station_business["covered_area_km2"]
)


# ============================================================
# 15. 결과 확인
# ============================================================

print("\n================================")
print("5. 대여소별 사업체 결과")
print("================================")

print(
    station_business.head(20)
)

print(
    "\n사업체수:"
)

print(
    station_business[
        "business_count_500m"
    ].describe()
)

print(
    "\n사업체 밀도:"
)

print(
    station_business[
        "business_density_per_km2"
    ].describe()
)

print(
    "\n사업체 buffer coverage:"
)

print(
    station_business[
        "business_buffer_coverage_ratio"
    ].describe()
)


# ============================================================
# 16. 기존 데이터에 JOIN
#
# 사업체는 2024년 고정값이므로
# 같은 station의 모든 날짜에 같은 값이 들어감
# ============================================================

final = bike.merge(
    station_business[
        [
            "station_id",
            "business_count_500m",
            "business_density_per_km2",
            "business_buffer_coverage_ratio"
        ]
    ],
    on="station_id",
    how="left"
)


# ============================================================
# 17. 최종 품질검사
# ============================================================

print("\n================================")
print("6. FINAL CHECK")
print("================================")

print("행 수:", len(final))
print("대여소:", final["station_id"].nunique())

print(
    "\n사업체수 결측률:",
    round(
        final[
            "business_count_500m"
        ]
        .isna()
        .mean() * 100,
        3
    ),
    "%"
)

print(
    "사업체밀도 결측률:",
    round(
        final[
            "business_density_per_km2"
        ]
        .isna()
        .mean() * 100,
        3
    ),
    "%"
)


print("\n사업체 정보가 없는 대여소:")

print(
    final.loc[
        final[
            "business_count_500m"
        ].isna(),
        "station_id"
    ]
    .drop_duplicates()
    .tolist()
)


# ============================================================
# 18. 저장
# ============================================================

station_business.to_csv(
    OUTPUT_STATION,
    index=False,
    encoding="utf-8-sig"
)

final.to_csv(
    OUTPUT_FINAL,
    index=False,
    encoding="utf-8-sig"
)


print("\n================================")
print("✅ 사업체 공간결합 완료")
print(OUTPUT_STATION)
print(OUTPUT_FINAL)
print("================================")


# ==================== ORIGINAL CELL 9 ====================
print("to_fa_010 GRID 수:",
      business_target["GRID_CD"].nunique())

print("전체 사업체 GRID 수:",
      business["GRID_CD"].nunique())

print("to_fa_010 값 결측:",
      business_target["value"].isna().sum())


# ==================== ORIGINAL CELL 10 ====================
#지하철 파일 내용 확인
import pandas as pd

FILE = "/content/전체_도시철도역사정보_20260630.xlsx"

xls = pd.ExcelFile(FILE)

print("시트:")
print(xls.sheet_names)

for sheet in xls.sheet_names:
    print("\n==============================")
    print("시트:", sheet)
    print("==============================")

    df = pd.read_excel(
        FILE,
        sheet_name=sheet
    )

    print("행 × 열:", df.shape)

    print("\n컬럼:")
    print(df.columns.tolist())

    print("\n앞 5행:")
    print(df.head().to_string())


# ==================== ORIGINAL CELL 11 ====================
# ============================================================
# 따릉이 대여소 → 가장 가까운 도시철도역 거리 계산
# ============================================================

import pandas as pd
import geopandas as gpd
import numpy as np

from scipy.spatial import cKDTree


# ============================================================
# 0. 파일
# ============================================================

BIKE_FILE = (
    "/content/"
    "ttareungi_daily_with_population_business_202509.csv"
)

SUBWAY_FILE = (
    "/content/"
    "전체_도시철도역사정보_20260630.xlsx"
)

OUTPUT_FILE = (
    "/content/"
    "ttareungi_daily_with_population_business_subway_202509.csv"
)

STATION_OUTPUT = (
    "/content/"
    "station_nearest_subway.csv"
)


# ============================================================
# 1. 기존 따릉이 데이터
# ============================================================

bike = pd.read_csv(
    BIKE_FILE,
    dtype={"station_id": str},
    low_memory=False
)

bike["station_id"] = (
    bike["station_id"]
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)

bike["lat"] = pd.to_numeric(
    bike["lat"],
    errors="coerce"
)

bike["lon"] = pd.to_numeric(
    bike["lon"],
    errors="coerce"
)


print("================================")
print("1. 따릉이 데이터")
print("================================")

print("station-day:", len(bike))
print("대여소:", bike["station_id"].nunique())


# 같은 대여소는 좌표 한 번만 사용
stations = (
    bike[
        [
            "station_id",
            "lat",
            "lon"
        ]
    ]
    .dropna(
        subset=["lat", "lon"]
    )
    .drop_duplicates(
        subset="station_id"
    )
    .copy()
)

print(
    "좌표 있는 대여소:",
    len(stations)
)


# ============================================================
# 2. 도시철도 역사정보
# ============================================================

subway = pd.read_excel(
    SUBWAY_FILE,
    sheet_name="표준데이터 역사"
)


print("\n================================")
print("2. 도시철도 역사정보")
print("================================")

print("원본 행:", len(subway))

print(
    subway[
        [
            "역번호",
            "역사명",
            "노선명",
            "역위도",
            "역경도"
        ]
    ].head()
)


# ============================================================
# 3. 좌표 정리
# ============================================================

subway["역위도"] = pd.to_numeric(
    subway["역위도"],
    errors="coerce"
)

subway["역경도"] = pd.to_numeric(
    subway["역경도"],
    errors="coerce"
)


subway = subway.dropna(
    subset=[
        "역위도",
        "역경도"
    ]
).copy()


# 이상 좌표 제거
subway = subway[
    subway["역위도"].between(
        33,
        39
    )
    &
    subway["역경도"].between(
        124,
        132
    )
].copy()


print(
    "좌표 정상 역사 행:",
    len(subway)
)


# ============================================================
# 4. 같은 물리적 역 중복 정리
#
# 환승역은 노선별로 여러 행일 수 있음.
# 역사명 + 좌표가 동일하면 하나의 역으로 묶음.
# 노선명은 '/'로 합침.
# ============================================================

subway_unique = (
    subway
    .groupby(
        [
            "역사명",
            "역위도",
            "역경도"
        ],
        as_index=False
    )
    .agg(
        노선명=(
            "노선명",
            lambda x:
            "/".join(
                sorted(
                    set(
                        x.dropna()
                        .astype(str)
                    )
                )
            )
        )
    )
)


print(
    "중복 정리 후 물리적 역사:",
    len(subway_unique)
)


# ============================================================
# 5. GeoDataFrame 변환
#
# 위경도 EPSG:4326
# → 거리 계산용 EPSG:5179
# ============================================================

station_gdf = gpd.GeoDataFrame(
    stations.copy(),
    geometry=gpd.points_from_xy(
        stations["lon"],
        stations["lat"]
    ),
    crs="EPSG:4326"
)

subway_gdf = gpd.GeoDataFrame(
    subway_unique.copy(),
    geometry=gpd.points_from_xy(
        subway_unique["역경도"],
        subway_unique["역위도"]
    ),
    crs="EPSG:4326"
)


station_gdf = station_gdf.to_crs(
    epsg=5179
)

subway_gdf = subway_gdf.to_crs(
    epsg=5179
)


# ============================================================
# 6. KDTree 생성
#
# 모든 station × 모든 subway를 직접 계산하지 않고
# 가장 가까운 역을 빠르게 탐색
# ============================================================

subway_xy = np.column_stack(
    [
        subway_gdf.geometry.x,
        subway_gdf.geometry.y
    ]
)

station_xy = np.column_stack(
    [
        station_gdf.geometry.x,
        station_gdf.geometry.y
    ]
)


tree = cKDTree(
    subway_xy
)


distance,nearest_index = tree.query(
    station_xy,
    k=1
)


# ============================================================
# 7. 최근접 역사 붙이기
# ============================================================

nearest_subway = (
    subway_gdf
    .iloc[nearest_index]
    .reset_index(drop=True)
)


station_result = pd.DataFrame(
    {
        "station_id":
            station_gdf[
                "station_id"
            ].values,

        "nearest_subway_station":
            nearest_subway[
                "역사명"
            ].values,

        "nearest_subway_line":
            nearest_subway[
                "노선명"
            ].values,

        "subway_distance_m":
            distance
    }
)


# ============================================================
# 8. 거리 품질검사
# ============================================================

print("\n================================")
print("3. 지하철 거리 결과")
print("================================")


print(
    station_result.head(20)
)


print(
    "\n거리 기초통계:"
)

print(
    station_result[
        "subway_distance_m"
    ].describe(
        percentiles=[
            .01,
            .05,
            .25,
            .50,
            .75,
            .95,
            .99
        ]
    )
)


print(
    "\n가장 가까운 10개:"
)

print(
    station_result
    .sort_values(
        "subway_distance_m"
    )
    .head(10)
)


print(
    "\n가장 먼 20개:"
)

print(
    station_result
    .sort_values(
        "subway_distance_m",
        ascending=False
    )
    .head(20)
)


# ============================================================
# 9. 이상치 확인
# ============================================================

print(
    "\n2km보다 먼 대여소:",
    (
        station_result[
            "subway_distance_m"
        ] > 2000
    ).sum()
)


print(
    "3km보다 먼 대여소:",
    (
        station_result[
            "subway_distance_m"
        ] > 3000
    ).sum()
)


# ============================================================
# 10. 기존 데이터에 JOIN
# ============================================================

final = bike.merge(
    station_result,
    on="station_id",
    how="left"
)


# ============================================================
# 11. JOIN 검사
# ============================================================

print("\n================================")
print("4. FINAL CHECK")
print("================================")

print(
    "조인 전 행:",
    len(bike)
)

print(
    "조인 후 행:",
    len(final)
)


print(
    "\n지하철 거리 결측률:",
    round(
        final[
            "subway_distance_m"
        ]
        .isna()
        .mean()
        * 100,
        3
    ),
    "%"
)


print(
    "\n지하철 거리가 없는 대여소:"
)

print(
    final.loc[
        final[
            "subway_distance_m"
        ].isna(),
        "station_id"
    ]
    .drop_duplicates()
    .tolist()
)


# ============================================================
# 12. 저장
# ============================================================

station_result.to_csv(
    STATION_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

final.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)


print("\n================================")
print("✅ 지하철 접근성 결합 완료")
print("================================")

print(STATION_OUTPUT)
print(OUTPUT_FILE)


# ==================== ORIGINAL CELL 12 ====================
# ============================================================
# FINAL REGRESSION DATASET PREPARATION
# Group 19 - Ttareungi Demand Model
# ============================================================

import pandas as pd
import numpy as np


# ============================================================
# 0. FILE PATH
# ============================================================

INPUT_FILE = (
    "/content/"
    "ttareungi_daily_with_population_business_subway_202509.csv"
)

MASTER_OUTPUT = (
    "/content/"
    "ttareungi_regression_master_202509.csv"
)

TRAIN_OUTPUT = (
    "/content/"
    "ttareungi_regression_train_202509.csv"
)


# ============================================================
# 1. LOAD DATA
# ============================================================

df = pd.read_csv(
    INPUT_FILE,
    dtype={"station_id": str},
    low_memory=False
)

print("====================================")
print("1. ORIGINAL DATA")
print("====================================")

print("전체 행:", len(df))
print("전체 대여소:", df["station_id"].nunique())
print("컬럼 수:", len(df.columns))


# ============================================================
# 2. CHECK REQUIRED COLUMNS
# ============================================================

required_cols = [

    # ID
    "station_id",
    "date",

    # Y
    "daily_observed_rentals",

    # X
    "daily_avg_population_07_23",
    "business_density_per_km2",
    "subway_distance_m",

    # stockout information
    "stockout_observations",
    "stockout_rate",

    # quality control
    "hours_observed",
    "buffer_coverage_ratio",
    "business_buffer_coverage_ratio"
]


missing_cols = [
    col
    for col in required_cols
    if col not in df.columns
]


if missing_cols:

    raise ValueError(
        f"❌ 필요한 컬럼이 없습니다: {missing_cols}"
    )

else:

    print("\n✅ 필요한 컬럼 전부 존재")


# ============================================================
# 3. BASIC CLEANING
# ============================================================

# station_id 정리
df["station_id"] = (
    df["station_id"]
    .astype(str)
    .str.strip()
    .str.replace(
        r"\.0$",
        "",
        regex=True
    )
)


# 날짜 변환
df["date"] = pd.to_datetime(
    df["date"],
    errors="coerce"
)


# 숫자형으로 확실하게 변환
numeric_cols = [

    "daily_observed_rentals",

    "daily_avg_population_07_23",
    "business_density_per_km2",
    "subway_distance_m",

    "stockout_observations",
    "stockout_rate",

    "hours_observed",

    "buffer_coverage_ratio",
    "business_buffer_coverage_ratio"
]


for col in numeric_cols:

    df[col] = pd.to_numeric(
        df[col],
        errors="coerce"
    )


# coverage에서 아주 작은 floating point 오차 제거
df["buffer_coverage_ratio"] = (
    df["buffer_coverage_ratio"]
    .clip(0, 1)
)

df["business_buffer_coverage_ratio"] = (
    df["business_buffer_coverage_ratio"]
    .clip(0, 1)
)


# ============================================================
# 4. DATE VARIABLES
# ============================================================

# 월요일 = 0
# 화요일 = 1
# ...
# 일요일 = 6

df["day_of_week"] = (
    df["date"]
    .dt.dayofweek
)


# 토/일 = 1
# 월~금 = 0

df["weekend"] = (
    df["day_of_week"] >= 5
).astype("Int64")


# 보기 편한 요일 변수도 추가
day_names = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
    5: "Sat",
    6: "Sun"
}

df["day_name"] = (
    df["day_of_week"]
    .map(day_names)
)


# ============================================================
# 5. STOCKOUT FLAG
# ============================================================

# 하루 중 한 번이라도
# available bikes = 0으로 관측됐으면 1

df["stockout_day"] = (
    df["stockout_observations"] > 0
).astype(int)


# 정상공급 학습 후보
df["no_stockout_day"] = (
    df["stockout_observations"] == 0
).astype(int)


# ============================================================
# 6. QUALITY FLAGS
# ============================================================

# 최소 23시간 이상 관측
df["quality_hours"] = (
    df["hours_observed"] >= 23
)


# 생활인구 buffer coverage >= 80%
df["quality_population"] = (

    df["daily_avg_population_07_23"].notna()

    &

    (
        df["buffer_coverage_ratio"]
        >= 0.80
    )

)


# 사업체 자료
df["quality_business"] = (

    df[
        "business_density_per_km2"
    ].notna()

    &

    (
        df[
            "business_buffer_coverage_ratio"
        ]
        >= 0.90
    )

)


# 지하철 거리
df["quality_subway"] = (
    df["subway_distance_m"]
    .notna()
)


# Y
df["quality_y"] = (
    df[
        "daily_observed_rentals"
    ].notna()
)


# 날짜
df["quality_date"] = (
    df["date"].notna()
)


# ============================================================
# 7. FINAL ANALYSIS QUALITY FLAG
# ============================================================

df["regression_eligible"] = (

    df["quality_hours"]

    & df["quality_population"]

    & df["quality_business"]

    & df["quality_subway"]

    & df["quality_y"]

    & df["quality_date"]

)


# ============================================================
# 8. TRAINING FLAG
#
# 회귀 학습에 사용할 Y:
#
# daily_observed_rentals
#
# 단:
# stockout_observations == 0
# ============================================================

df["train_for_demand_model"] = (

    df["regression_eligible"]

    &

    (
        df["stockout_observations"]
        == 0
    )

)


# ============================================================
# 9. DUPLICATE CHECK
#
# station_id × date 하나당 1행이어야 함
# ============================================================

duplicate_count = (
    df
    .duplicated(
        subset=[
            "station_id",
            "date"
        ]
    )
    .sum()
)


print("\n====================================")
print("2. DUPLICATE CHECK")
print("====================================")

print(
    "station_id + date 중복:",
    duplicate_count
)


if duplicate_count == 0:

    print("✅ 중복 없음")

else:

    print("⚠️ 중복 확인 필요")


# ============================================================
# 10. VALUE CHECK
# ============================================================

print("\n====================================")
print("3. DATA QUALITY SUMMARY")
print("====================================")


print(
    "전체 행:",
    len(df)
)


print(
    "23시간 이상 관측:",
    df["quality_hours"].sum()
)


print(
    "생활인구 조건 통과:",
    df["quality_population"].sum()
)


print(
    "사업체 조건 통과:",
    df["quality_business"].sum()
)


print(
    "지하철 거리 있음:",
    df["quality_subway"].sum()
)


print(
    "\n최종 regression eligible:",
    df[
        "regression_eligible"
    ].sum()
)


print(
    "제외된 행:",
    (
        ~df[
            "regression_eligible"
        ]
    ).sum()
)


# ============================================================
# 11. STOCKOUT DISTRIBUTION
# ============================================================

eligible = df[
    df["regression_eligible"]
].copy()


print("\n====================================")
print("4. STOCKOUT STATUS")
print("====================================")


print(
    "분석 가능 전체:",
    len(eligible)
)


print(
    "Stockout 없음:",
    (
        eligible[
            "stockout_observations"
        ] == 0
    ).sum()
)


print(
    "Stockout 있음:",
    (
        eligible[
            "stockout_observations"
        ] > 0
    ).sum()
)


print(
    "Stockout 발생 비율:",
    round(
        (
            eligible[
                "stockout_observations"
            ] > 0
        ).mean()
        * 100,
        2
    ),
    "%"
)


# ============================================================
# 12. FINAL MASTER DATASET
#
# 아직 stockout 발생 행도 남겨둔다.
# 이후 회귀 예측값을 붙일 때 필요함.
# ============================================================

master_cols = [

    # --------------------------------
    # Identification
    # --------------------------------
    "station_id",
    "date",
    "day_of_week",
    "day_name",
    "weekend",

    # --------------------------------
    # Y
    # --------------------------------
    "daily_observed_rentals",

    # --------------------------------
    # X1
    # --------------------------------
    "daily_avg_population_07_23",

    # --------------------------------
    # X2
    # --------------------------------
    "business_density_per_km2",

    # --------------------------------
    # X3
    # --------------------------------
    "subway_distance_m",

    # --------------------------------
    # Stockout information
    # --------------------------------
    "stockout_observations",
    "stockout_rate",
    "stockout_day",
    "no_stockout_day",

    # --------------------------------
    # Observation quality
    # --------------------------------
    "hours_observed",
    "buffer_coverage_ratio",
    "business_buffer_coverage_ratio",

    # --------------------------------
    # Reference information
    # --------------------------------
    "lat",
    "lon",
    "nearest_subway_station",
    "nearest_subway_line",

    # --------------------------------
    # Analysis flags
    # --------------------------------
    "regression_eligible",
    "train_for_demand_model"
]


# 혹시 선택 컬럼 일부가 없다면 자동 제외
master_cols = [
    col
    for col in master_cols
    if col in df.columns
]


master = (

    df.loc[
        df["regression_eligible"],
        master_cols
    ]

    .copy()

    .sort_values(
        [
            "station_id",
            "date"
        ]
    )

    .reset_index(
        drop=True
    )
)


# ============================================================
# 13. REGRESSION TRAINING DATA
#
# 여기 있는 daily_observed_rentals가
# 실제 회귀분석의 Y
# ============================================================

train = (

    master[
        master[
            "train_for_demand_model"
        ]
    ]

    .copy()

    .reset_index(
        drop=True
    )
)


# ============================================================
# 14. REGRESSION-ONLY CLEAN TABLE
#
# 실제 regression 코드에서 바로 사용하기 편한
# 최소 변수 버전
# ============================================================

regression_columns = [

    "station_id",
    "date",

    # Y
    "daily_observed_rentals",

    # X
    "daily_avg_population_07_23",
    "business_density_per_km2",
    "subway_distance_m",
    "weekend"
]


regression_train = (
    train[
        regression_columns
    ]
    .copy()
)


# ============================================================
# 15. FINAL VALIDATION
# ============================================================

print("\n====================================")
print("5. FINAL REGRESSION DATA")
print("====================================")


print(
    "MASTER 행:",
    len(master)
)


print(
    "TRAIN 행:",
    len(train)
)


print(
    "TRAIN 대여소:",
    train[
        "station_id"
    ].nunique()
)


print(
    "\nY 기초통계:"
)

print(
    train[
        "daily_observed_rentals"
    ].describe()
)


print(
    "\nX 기초통계:"
)

print(
    train[
        [
            "daily_avg_population_07_23",
            "business_density_per_km2",
            "subway_distance_m",
            "weekend"
        ]
    ].describe()
)


# ============================================================
# 16. MISSING VALUE FINAL CHECK
# ============================================================

print("\n====================================")
print("6. FINAL MISSING VALUE CHECK")
print("====================================")


print(
    regression_train[
        [
            "daily_observed_rentals",
            "daily_avg_population_07_23",
            "business_density_per_km2",
            "subway_distance_m",
            "weekend"
        ]
    ]
    .isna()
    .sum()
)


# ============================================================
# 17. SAVE
# ============================================================

master.to_csv(
    MASTER_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)


train.to_csv(
    TRAIN_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)


regression_train.to_csv(
    "/content/"
    "ttareungi_regression_train_simple_202509.csv",
    index=False,
    encoding="utf-8-sig"
)


print("\n====================================")
print("✅ FINAL DATASET COMPLETE")
print("====================================")


print("\n[전체 분석용]")
print(MASTER_OUTPUT)


print("\n[회귀 학습용]")
print(TRAIN_OUTPUT)


print("\n[회귀 최소 변수 버전]")
print(
    "/content/"
    "ttareungi_regression_train_simple_202509.csv"
)
