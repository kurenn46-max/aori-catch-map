#!/usr/bin/env python3
import json, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST=timezone(timedelta(hours=9))
AREAS={"越前":(35.914,135.991),"敦賀":(35.681,136.049),"若狭":(35.555,135.760),"舞鶴":(35.507,135.376),"丹後":(35.674,135.287)}
VALID_TYPE={"shore","boat"}
VALID_STATUS={"catch","blank","chase_only","sighting_only"}
VALID_PREC={"area","place","exact"}

def load(path,default):
    p=Path(path)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding="utf-8"))

def parse_body(body):
    if not body.startswith("MANUAL_CATCH_V1"):
        raise ValueError("not manual catch payload")
    out={}
    for line in body.splitlines()[1:]:
        if "=" not in line: continue
        k,v=line.split("=",1)
        out[k.strip()]=v.strip()
    return out

def as_float(v):
    try:return float(v) if v not in ("",None) else None
    except:return None

def as_int(v):
    try:return int(v) if v not in ("",None) else None
    except:return None

event=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
issue=event["issue"]
data=parse_body(issue.get("body") or "")

date=data.get("date","")
datetime.strptime(date,"%Y-%m-%d")
area=data.get("area","")
if area not in AREAS: raise ValueError("invalid area")
typ=data.get("type","shore")
if typ not in VALID_TYPE: raise ValueError("invalid type")
status=data.get("result_status","catch")
if status not in VALID_STATUS: raise ValueError("invalid result_status")
precision=data.get("precision","area")
if precision not in VALID_PREC: precision="area"

default_lat,default_lng=AREAS[area]
lat=as_float(data.get("lat")); lng=as_float(data.get("lng"))
if lat is None or lng is None:
    lat,lng=default_lat,default_lng
    if precision=="exact": precision="area"

count=as_int(data.get("count"))
if status=="blank": count=0
if status in ("chase_only","sighting_only") and count is None: count=0

duration=as_float(data.get("duration_hours"))
anglers=as_int(data.get("angler_count"))
cpue=None; session_rate=None
if count is not None and duration and duration>0:
    session_rate=round(count/duration,2)
    if anglers and anglers>0:
        cpue=round(count/(duration*anglers),2)

stamp=datetime.now(JST).isoformat(timespec="seconds")
rid=f"manual-gh-{issue['number']}"
row={
  "id":rid,
  "date":date,
  "area":area,
  "place":data.get("place") or area,
  "lat":lat,"lng":lng,
  "type":typ,
  "method":data.get("method") or "不明",
  "count":count,
  "maxSize":data.get("maxSize") or "不明",
  "time":data.get("time") or "不明",
  "source":"ユーザー実釣",
  "url":issue.get("html_url"),
  "title":data.get("title") or f"{area} 手動釣果",
  "demo":False,
  "precision":precision,
  "result_status":status,
  "manual":True,
  "note":data.get("note") or "",
  "first_seen_at":stamp,
  "last_seen_at":stamp
}
if duration is not None: row["duration_hours"]=duration
if anglers is not None: row["angler_count"]=anglers
if cpue is not None: row["cpue"]=cpue
if session_rate is not None: row["session_rate"]=session_rate

# Current display DB: keep recent 30 days only, merge by id.
cur=load("data/catches.json",{"catches":[]})
today=datetime.now(JST).date()
day=datetime.strptime(date,"%Y-%m-%d").date()
if (today-day).days <= 30:
    by={x.get("id"):x for x in cur.get("catches",[]) if x.get("id")}
    by[rid]=row
    rows=sorted(by.values(),key=lambda x:(x.get("date",""),x.get("time",""),x.get("id","")),reverse=True)
    cur["updated_at"]=stamp
    cur["catches"]=rows
    Path("data/catches.json").write_text(json.dumps(cur,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

# Permanent archive
year=date[:4]
ap=Path(f"data/archive/{year}.json")
arc=load(ap,{"schema_version":1,"catches":[]})
by={x.get("id"):x for x in arc.get("catches",[]) if x.get("id")}
by[rid]=row
arc["updated_at"]=stamp
arc["catches"]=sorted(by.values(),key=lambda x:(x.get("date",""),x.get("time",""),x.get("id","")),reverse=True)
ap.parent.mkdir(parents=True,exist_ok=True)
ap.write_text(json.dumps(arc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"id":rid,"date":date,"area":area,"status":status,"count":count},ensure_ascii=False))
