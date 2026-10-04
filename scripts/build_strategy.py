#!/usr/bin/env python3
import json, re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST=timezone(timedelta(hours=9))
AREAS=["越前","敦賀","若狭","舞鶴","丹後"]

def load(path, default):
    p=Path(path)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding="utf-8"))

def parse_day(s):
    try: return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=JST)
    except: return None

def exact_hour(s):
    m=re.fullmatch(r"(\d{1,2}):(\d{2})",(s or "").strip())
    if not m:return None
    h,mn=map(int,m.groups())
    if not (0<=h<24 and 0<=mn<60):return None
    return h+mn/60

def angler(row):
    if row.get("angler"): return str(row["angler"]).strip()
    title=str(row.get("title") or "")
    if "さん /" in title:return title.split("さん /",1)[0].strip()
    return None

def terrain(row):
    s=" ".join(str(row.get(k) or "") for k in ("reportPlace","terrain","place","title"))
    if "磯" in s:return "磯"
    if any(k in s for k in ("サーフ","砂浜","ゴロタ")):return "サーフ・ゴロタ"
    if any(k in s for k in ("防波堤","堤防","漁港","港内","港口")):return "港・堤防"
    if any(k in s for k in ("藻場","藻","シャロー")):return "藻場・シャロー"
    if any(k in s for k in ("ボート","船","ティップラン")):return "船"
    return "不明"

def time_bucket(hour):
    if hour is None:return None
    if 4<=hour<8:return "朝まずめ"
    if 8<=hour<15:return "日中"
    if 15<=hour<19:return "夕まずめ"
    if 19<=hour or hour<1:return "夜前半"
    return "深夜"

def size_rank(s):
    text=str(s or "")
    nums=[int(x) for x in re.findall(r"(\d+)g",text)]
    if nums:return max(nums)
    if "kg" in text:
        m=re.search(r"([0-9.]+)\s*kg",text)
        if m:return int(float(m.group(1))*1000)
    return -1

def session_key(row):
    a=angler(row)
    if a and row.get("source")=="エギCOM":
        return ("yamaria",row.get("date"),row.get("area"),a,row.get("type"))
    return ("record",row.get("id"))

def sessionize(rows):
    grouped=defaultdict(list)
    for row in rows:grouped[session_key(row)].append(row)
    out=[]
    for key,items in grouped.items():
        items=sorted(items,key=lambda x:(x.get("time") or ""))
        hours=[exact_hour(x.get("time")) for x in items]
        hours=[x for x in hours if x is not None]
        statuses=[x.get("result_status","catch") for x in items]
        status="catch" if "catch" in statuses else ("chase_only" if "chase_only" in statuses else ("sighting_only" if "sighting_only" in statuses else "blank"))
        tr=Counter(terrain(x) for x in items if terrain(x)!="不明")
        sizes=[x.get("maxSize") for x in items if x.get("maxSize") not in (None,"","不明")]
        best_size=max(sizes,key=size_rank) if sizes else None
        out.append({
          "key":"|".join(str(x) for x in key),
          "date":items[0].get("date"),"area":items[0].get("area"),"type":items[0].get("type"),
          "source":items[0].get("source"),"angler":angler(items[0]),
          "records":len(items),"status":status,
          "hour":sum(hours)/len(hours) if hours else None,
          "time_bucket":time_bucket(sum(hours)/len(hours)) if hours else None,
          "terrain":tr.most_common(1)[0][0] if tr else "不明",
          "maxSize":best_size
        })
    return out

archive=load("data/archive/2026.json",{"catches":[]})
intel=load("data/intel.json",{"items":[]})
records=archive.get("catches",[])
sessions=sessionize(records)
valid_dates=[parse_day(x.get("date","")) for x in records]
valid_dates=[x for x in valid_dates if x]
ref=max(valid_dates) if valid_dates else datetime.now(JST)

def in_days(s,days):
    d=parse_day(s.get("date",""))
    return bool(d and 0 <= (ref-d).days < days)

def between(s,start_days,end_days):
    d=parse_day(s.get("date",""))
    if not d:return False
    age=(ref-d).days
    return start_days<=age<end_days

def count_modes(items,field):
    c=Counter(x.get(field) for x in items if x.get(field) not in (None,"","不明"))
    return c.most_common()

areas=[]
for area in AREAS:
    ss=[x for x in sessions if x.get("area")==area]
    shore=[x for x in ss if x.get("type")=="shore"]
    c48=[x for x in shore if in_days(x,2) and x.get("status")=="catch"]
    l7=[x for x in shore if in_days(x,7)]
    p7=[x for x in shore if between(x,7,14)]
    l30=[x for x in shore if in_days(x,30)]
    catch30=[x for x in l30 if x.get("status")=="catch"]
    neg7=Counter(x.get("status") for x in l7 if x.get("status")!="catch")
    time_modes=count_modes(catch30,"time_bucket")
    terrain_modes=count_modes(catch30,"terrain")
    size_modes=count_modes(catch30,"maxSize")
    latest=max([x.get("date") for x in shore if x.get("date")],default=None)
    latest_dt=parse_day(latest) if latest else None
    age=(ref-latest_dt).days if latest_dt else 999
    sources=len({x.get("source") for x in l30 if x.get("source")})
    exact=sum(x.get("hour") is not None for x in catch30)
    time_quality=(exact/len(catch30)) if catch30 else 0

    recent_intel=[x for x in intel.get("items",[]) if x.get("area")==area and x.get("date") and (ref-parse_day(x["date"])).days<=14]
    bait=[x for x in recent_intel if x.get("category")=="bait" and x.get("shore_relevance") in ("high","medium")]
    pressure=[x for x in recent_intel if x.get("category")=="pressure"]
    local=[x for x in intel.get("items",[]) if x.get("area")==area and x.get("category")=="local" and x.get("active")]

    recency=30 if age==0 else 25 if age==1 else 20 if age==2 else 15 if age<=3 else 8 if age<=7 else 0
    sample=min(30,len(catch30)*3)
    diversity=min(20,sources*7)
    quality=round(time_quality*10)
    intel_bonus=min(10,len(bait)*3+len(pressure)*2)
    confidence=max(0,min(100,recency+sample+diversity+quality+intel_bonus))
    grade="A" if confidence>=75 else ("B" if confidence>=55 else "C")

    curr=len([x for x in l7 if x.get("status")=="catch"])
    prev=len([x for x in p7 if x.get("status")=="catch"])
    if curr>0 and prev==0:trend="new"
    elif curr==0 and prev==0:trend="none"
    elif prev>0 and curr>=prev*1.3:trend="up"
    elif prev>0 and curr<=prev*0.7:trend="down"
    else:trend="flat"

    areas.append({
      "area":area,"latest_date":latest,"confidence":confidence,"grade":grade,"trend":trend,
      "last48h_sessions":{"shore":len(c48)},
      "last7_sessions":{"shore":len(l7),"catch":sum(x.get("status")=="catch" for x in l7),"negative":sum(x.get("status")!="catch" for x in l7)},
      "prev7_sessions":{"shore":len(p7),"catch":sum(x.get("status")=="catch" for x in p7)},
      "last30_sessions":{"shore":len(l30),"catch":len(catch30)},
      "sources_30d":sources,
      "top_time":time_modes[0][0] if time_modes else None,
      "time_counts":dict(time_modes),
      "top_terrain":terrain_modes[0][0] if terrain_modes else None,
      "terrain_counts":dict(terrain_modes),
      "top_size":size_modes[0][0] if size_modes else None,
      "size_counts":dict(size_modes),
      "negative_7d":dict(neg7),
      "bait_recent":len(bait),
      "pressure_recent":len(pressure),
      "local_active":len(local),
      "raw_posts_30d":sum(x.get("records",1) for x in l30),
      "note":"同一投稿者・同日・同海域のエギCOM連投は1セッションに圧縮。件数より釣行単位を優先。"
    })

out={
  "updated_at":datetime.now(JST).isoformat(timespec="seconds"),
  "reference_date":ref.strftime("%Y-%m-%d"),
  "method":"直近48h=現況、7日=短期傾向、30日=時間帯/地形/サイズ学習。同一釣行の連投をセッション圧縮。",
  "areas":areas
}
Path("data/strategy.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print({x["area"]:(x["last48h_sessions"]["shore"],x["grade"]) for x in areas})
