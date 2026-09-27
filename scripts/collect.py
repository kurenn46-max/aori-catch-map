#!/usr/bin/env python3
import json, re, hashlib, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
MAX_DAYS = 30

SOURCES = [
    ("越前","越前海岸",35.914,135.991),
    ("敦賀","敦賀",35.645,136.055),
    ("若狭","常神半島",35.608,135.833),
    ("若狭","小浜",35.495,135.746),
    ("若狭","高浜",35.489,135.551),
    ("舞鶴","舞鶴",35.474,135.386),
    ("丹後","伊根",35.674,135.287),
    ("丹後","宮津",35.535,135.196),
    ("丹後","京丹後",35.650,135.060),
]

POINTS = {
    "越前海岸":(35.914,135.991),"越前岬":(35.980,135.958),"甲楽城":(35.827,136.020),
    "敦賀":(35.645,136.055),"敦賀湾":(35.681,136.049),
    "常神半島":(35.608,135.833),"小浜":(35.495,135.746),"小浜湾":(35.521,135.720),
    "高浜":(35.489,135.551),"舞鶴":(35.474,135.386),"舞鶴湾":(35.507,135.376),
    "伊根":(35.674,135.287),"宮津":(35.535,135.196),"京丹後":(35.650,135.060),
}

UA={"User-Agent":"Mozilla/5.0 (compatible; AoriCatchMap/1.0; +https://github.com/kurenn46-max/aori-catch-map)"}

def clean(s):
    return re.sub(r"\s+"," ",s or "").strip()

def infer_type(blob):
    if any(k in blob for k in ["ソルトオフショア","ティップラン","遊漁船","ボート","船釣り"]):
        return "boat"
    if any(k in blob for k in ["ソルト陸っぱり","陸っぱり","ショア","堤防","漁港","磯"]):
        return "shore"
    return None

def infer_method(blob):
    for k in ["ティップラン","ヤエン","エギング"]:
        if k in blob: return k
    return "不明"

def infer_count(blob):
    vals=[]
    for m in re.finditer(r"(?<!\d)(\d{1,3})\s*(?:杯|ハイ|匹|枚)",blob):
        n=int(m.group(1))
        if 0<n<=100: vals.append(n)
    return max(vals) if vals else 1

def infer_size(blob):
    m=re.search(r"胴長\s*(\d+(?:\.\d+)?)\s*cm",blob)
    if m: return "胴長"+m.group(1)+"cm"
    m=re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*kg",blob,re.I)
    if m: return m.group(1)+"kg"
    m=re.search(r"(?<!\d)(\d{2})\s*cm",blob)
    if m: return m.group(1)+"cm"
    return "不明"

def infer_source(blob):
    m=re.search(r"情報元:([^\n]+?)(?:\s+\d+\s*(?:POINT|Click)|$)",blob)
    return clean(m.group(1))[:50] if m else "魚速釣果検索"

def infer_place(blob, fallback):
    m=re.search(r"関連ポイント:(.*?)関連魚種:",blob)
    pts=clean(m.group(1)) if m else ""
    for p in POINTS:
        if p in pts or p in blob:
            return p, *POINTS[p]
    return fallback

def fetch_area(area, term, lat, lng):
    params={"er":"24.0","fn":"アオリイカ","lo":term}
    url="https://plus.uosoku.com/search?"+urlencode(params)
    r=requests.get(url,headers=UA,timeout=25)
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    lines=[clean(x) for x in soup.get_text("\n",strip=True).splitlines() if clean(x)]
    out=[]
    for i,line in enumerate(lines):
        m=re.match(r"^(20\d\d-\d\d-\d\d)\s+(.*)$",line)
        if not m: continue
        date=m.group(1)
        try: d=datetime.strptime(date,"%Y-%m-%d").replace(tzinfo=JST)
        except ValueError: continue
        age=(NOW-d).days
        if age<0 or age>MAX_DAYS: continue
        prev=" ".join(lines[max(0,i-2):i])
        blob=clean(prev+" "+line)
        if "アオリイカ" not in blob: continue
        typ=infer_type(blob)
        if not typ: continue
        place_info=infer_place(blob,(term,lat,lng))
        place,plat,plng=place_info
        title=clean(lines[i-1] if i else "")[:100]
        rid=hashlib.sha1((date+area+place+blob).encode()).hexdigest()[:14]
        out.append({
            "id":rid,"date":date,"area":area,"place":place,
            "lat":plat,"lng":plng,"type":typ,
            "method":infer_method(blob),"count":infer_count(blob),
            "maxSize":infer_size(blob),"time":"不明",
            "source":infer_source(blob),
            "url":url,"title":title,"demo":False,"precision":"area"
        })
    return out

def main():
    all_rows=[]
    seen=set()
    for area,term,lat,lng in SOURCES:
        try:
            rows=fetch_area(area,term,lat,lng)
            print(f"{term}: {len(rows)}")
            for x in rows:
                key=(x["date"],x["area"],x["place"],x["type"],x["title"])
                if key not in seen:
                    seen.add(key); all_rows.append(x)
        except Exception as e:
            print(f"WARN {term}: {e}",file=sys.stderr)
    if not all_rows:
        print("No fresh records found; existing data preserved.")
        return
    all_rows.sort(key=lambda x:(x["date"],x["area"],x["place"]),reverse=True)
    payload={
        "updated_at":NOW.isoformat(timespec="seconds"),
        "note":"公開釣果検索ページから自動収集。地点は投稿本文から特定できない場合、エリア概算位置です。",
        "catches":all_rows[:250]
    }
    p=Path("data/catches.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {len(all_rows[:250])} records")

if __name__=="__main__":
    main()
