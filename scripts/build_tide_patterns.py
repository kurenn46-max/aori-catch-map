#!/usr/bin/env python3
import json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter, defaultdict

JST=timezone(timedelta(hours=9))
AREAS=["越前","敦賀","若狭","舞鶴","丹後"]

def load(path,default):
    p=Path(path)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding="utf-8"))

def exact_time(s):
    s=(s or "").strip()
    m=re.fullmatch(r"(\d{1,2}):(\d{2})",s)
    if not m:return None
    h,mn=map(int,m.groups())
    if 0<=h<24 and 0<=mn<60:return h,mn
    return None

def dt(date,t):
    h,mn=t
    return datetime.strptime(date,"%Y-%m-%d").replace(hour=h,minute=mn,tzinfo=JST)

def neighboring_days(date):
    d=datetime.strptime(date,"%Y-%m-%d")
    return [(d+timedelta(days=i)).strftime("%Y-%m-%d") for i in (-1,0,1)]

def events_for(tides,station,date):
    st=tides.get("stations",{}).get(station,{})
    days=st.get("days",{})
    out=[]
    for day in neighboring_days(date):
        obj=days.get(day,{})
        for x in obj.get("highs",[]):
            try: out.append((dt(day,exact_time(x.get("time"))),"high",x.get("height_cm")))
            except: pass
        for x in obj.get("lows",[]):
            try: out.append((dt(day,exact_time(x.get("time"))),"low",x.get("height_cm")))
            except: pass
    return sorted(out,key=lambda x:x[0])

def phase_at(tides,area,date,time_s):
    tm=exact_time(time_s)
    if not tm:return None
    station=tides.get("area_station",{}).get(area)
    if not station:return None
    moment=dt(date,tm)
    ev=events_for(tides,station,date)
    prev=None; nxt=None
    for e in ev:
        if e[0]<=moment: prev=e
        elif e[0]>moment and nxt is None:
            nxt=e;break
    if not prev or not nxt:return None
    if prev[1]=="low" and nxt[1]=="high": phase="rising"; jp="上げ"
    elif prev[1]=="high" and nxt[1]=="low": phase="falling"; jp="下げ"
    else:return None
    total=(nxt[0]-prev[0]).total_seconds()
    elapsed=(moment-prev[0]).total_seconds()
    if total<=0:return None
    progress=max(0,min(10,elapsed/total*10))
    lo=int(progress//2)*2
    if lo>=10:lo=8
    hi=lo+2
    key=f"{phase}_{lo}_{hi}"
    return {
      "station":station,
      "station_name":tides.get("stations",{}).get(station,{}).get("name",station),
      "phase":phase,"phase_ja":jp,
      "progress":round(progress,1),
      "bin":key,"bin_label":f"{jp}{lo}〜{hi}分",
      "prev_event":{"time":prev[0].isoformat(),"type":prev[1],"height_cm":prev[2]},
      "next_event":{"time":nxt[0].isoformat(),"type":nxt[1],"height_cm":nxt[2]}
    }

archive=load("data/archive/2026.json",{"catches":[]})
tides=load("data/tides.json",{})
by_area=defaultdict(list)
seen_sessions=set()

def session_key(row):
    title=str(row.get("title") or "")
    who=title.split("さん /",1)[0].strip() if "さん /" in title else (row.get("angler") or row.get("id"))
    if row.get("source")=="エギCOM" and who:
        return (row.get("date"),row.get("area"),row.get("type"),str(who))
    return (row.get("id"),)

for row in archive.get("catches",[]):
    if row.get("type")!="shore":continue
    if row.get("result_status","catch")!="catch":continue
    area=row.get("area")
    if area not in AREAS:continue
    sk=session_key(row)
    if sk in seen_sessions:continue
    seen_sessions.add(sk)
    ph=phase_at(tides,area,row.get("date",""),row.get("time",""))
    if not ph:continue
    by_area[area].append({
      "id":row.get("id"),"date":row.get("date"),"time":row.get("time"),
      "place":row.get("place"),"source":row.get("source"),**ph
    })

areas={}
for area in AREAS:
    samples=by_area.get(area,[])
    counts=Counter(x["bin"] for x in samples)
    labels={x["bin"]:x["bin_label"] for x in samples}
    ranked=counts.most_common()
    top=[{"bin":k,"label":labels.get(k,k),"count":v,"share":round(v/len(samples),3) if samples else 0} for k,v in ranked[:3]]
    n=len(samples)
    reliability="high" if n>=8 else ("medium" if n>=4 else "low")
    rising=sum(x["phase"]=="rising" for x in samples)
    falling=sum(x["phase"]=="falling" for x in samples)
    areas[area]={
      "sample_count":n,
      "reliability":reliability,
      "phase_counts":{"rising":rising,"falling":falling},
      "bins":dict(counts),
      "top_patterns":top,
      "samples":samples
    }

out={
  "updated_at":datetime.now(JST).isoformat(timespec="seconds"),
  "source":"data/archive/2026.json × 気象庁天文潮位",
  "method":"実釣時刻がHH:MMで明確な陸っぱり釣果のみ。1釣行=1標本。満干潮間の時間進行を0〜10分として2分刻みで集計。",
  "areas":areas
}
Path("data/tide-patterns.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print({a:areas[a]["sample_count"] for a in AREAS})
