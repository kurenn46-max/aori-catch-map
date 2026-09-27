#!/usr/bin/env python3
import json, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST=timezone(timedelta(hours=9))
YEAR=datetime.now(JST).year
STATIONS={
  "ZG":{"name":"三国","areas":["越前"]},
  "XM":{"name":"敦賀","areas":["敦賀","若狭"]},
  "MZ":{"name":"舞鶴","areas":["舞鶴"]},
  "T2":{"name":"宮津","areas":["丹後"]},
}
BASE="https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station}.txt"
UA={"User-Agent":"Mozilla/5.0 (AoriCatchMap/1.0; tide-cache)"}

def n(s):
    s=s.strip()
    if not s or s in ("9999","999"): return None
    try:return int(s)
    except:return None

def parse_line(line):
    line=line.rstrip("\n")
    if len(line)<136:return None
    hourly=[]
    for i in range(24):
        v=n(line[i*3:(i+1)*3])
        hourly.append(v)
    yy=n(line[72:74]); mm=n(line[74:76]); dd=n(line[76:78])
    if yy is None or mm is None or dd is None:return None
    year=2000+yy
    station=line[78:80].strip()
    highs=[]; lows=[]
    for i in range(4):
        off=80+i*7
        t=line[off:off+4].strip(); h=n(line[off+4:off+7])
        if t!="9999" and h is not None and len(t)>=3:
            t=t.zfill(4); highs.append({"time":t[:2]+":"+t[2:],"height_cm":h})
    for i in range(4):
        off=108+i*7
        t=line[off:off+4].strip(); h=n(line[off+4:off+7])
        if t!="9999" and h is not None and len(t)>=3:
            t=t.zfill(4); lows.append({"time":t[:2]+":"+t[2:],"height_cm":h})
    return {"date":f"{year:04d}-{mm:02d}-{dd:02d}","station":station,"hourly_cm":hourly,"highs":highs,"lows":lows}

def main():
    out={"updated_at":datetime.now(JST).isoformat(timespec="seconds"),"source":"気象庁 潮位表（天文潮位）","source_url":"https://www.data.jma.go.jp/kaiyou/db/tide/suisan/","year":YEAR,"stations":{},"area_station":{"越前":"ZG","敦賀":"XM","若狭":"XM","舞鶴":"MZ","丹後":"T2"},"note":"若狭は代表値として敦賀潮位表を使用。地点ごとの局地差は含まない。実測潮位ではなく天文潮位。"}
    for code,meta in STATIONS.items():
        url=BASE.format(year=YEAR,station=code)
        r=requests.get(url,headers=UA,timeout=30);r.raise_for_status()
        days={}
        for line in r.text.splitlines():
            row=parse_line(line)
            if row and row["station"]==code:
                days[row["date"]]={"hourly_cm":row["hourly_cm"],"highs":row["highs"],"lows":row["lows"]}
        out["stations"][code]={"name":meta["name"],"url":url,"days":days}
        print(code,meta["name"],len(days))
    Path("data").mkdir(exist_ok=True)
    Path("data/tides.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
