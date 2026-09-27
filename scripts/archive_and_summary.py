#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

JST=timezone(timedelta(hours=9))
AREAS=["越前","敦賀","若狭","舞鶴","丹後"]

def load(path, default):
    p=Path(path)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding="utf-8"))

def parse_day(s):
    return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=JST)

def iso_day(d):
    return d.strftime("%Y-%m-%d")

current=load("data/catches.json",{"catches":[]})
year=(max([x.get("date","") for x in current.get("catches",[]) if x.get("date")], default=str(datetime.now(JST).year)+"-01-01"))[:4]
archive_path=f"data/archive/{year}.json"
archive=load(archive_path,{"schema_version":1,"catches":[]})

by_id={x.get("id"):x for x in archive.get("catches",[]) if x.get("id")}
stamp=current.get("updated_at") or datetime.now(JST).isoformat(timespec="seconds")

for row in current.get("catches",[]):
    rid=row.get("id")
    if not rid: continue
    if rid in by_id:
        first=by_id[rid].get("first_seen_at",stamp)
        merged={**by_id[rid],**row,"first_seen_at":first,"last_seen_at":stamp}
    else:
        merged={**row,"first_seen_at":stamp,"last_seen_at":stamp}
    by_id[rid]=merged

records=sorted(by_id.values(),key=lambda x:(x.get("date",""),x.get("time",""),x.get("id","")),reverse=True)
Path("data/archive").mkdir(parents=True,exist_ok=True)
Path(archive_path).write_text(json.dumps({
    "updated_at":stamp,
    "schema_version":1,
    "note":"永久保存用。直近表示から消えた釣果も保持する。",
    "catches":records
},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

dates=sorted([x["date"] for x in records if x.get("date")])
ref=parse_day(dates[-1]) if dates else datetime.now(JST)
def rows_between(rows,a,b):
    return [x for x in rows if x.get("date") and a<=parse_day(x["date"])<=b]
def counts(rows):
    return {"total":len(rows),"shore":sum(x.get("type")=="shore" for x in rows),"boat":sum(x.get("type")=="boat" for x in rows)}

areas=[]
for area in AREAS:
    rs=[x for x in records if x.get("area")==area]
    l7=rows_between(rs,ref-timedelta(days=6),ref)
    p7=rows_between(rs,ref-timedelta(days=13),ref-timedelta(days=7))
    l30=rows_between(rs,ref-timedelta(days=29),ref)
    curr,prev=len(l7),len(p7)
    trend="none"; change=None
    if curr>0 and prev==0: trend="new"
    elif curr==0 and prev==0: trend="none"
    elif prev>0:
        change=round((curr-prev)/prev*100)
        trend="up" if curr>=prev*1.3 else ("down" if curr<=prev*0.7 else "flat")
    sizes=Counter(x.get("maxSize") for x in l30 if x.get("maxSize") not in (None,"","不明"))
    areas.append({
        "area":area,
        "latest_date":max([x.get("date","") for x in rs],default=None),
        "last7":counts(l7),"prev7":counts(p7),"last30":counts(l30),
        "season":counts([x for x in rs if x.get("date") and x.get("date") >= f"{ref.year}-08-01" and parse_day(x["date"]) <= ref]),
        "season_first_date":min([x.get("date") for x in rs if x.get("date") and x.get("date") >= f"{ref.year}-08-01"], default=None),
        "trend":trend,"change_pct":change,
        "source_count":len({x.get("source") for x in l30 if x.get("source")}),
        "size_top":sizes.most_common(1)[0][0] if sizes else "情報少"
    })

daily=[]
for i in range(13,-1,-1):
    day=iso_day(ref-timedelta(days=i))
    rs=[x for x in records if x.get("date")==day]
    daily.append({"date":day,**counts(rs)})

season_rows=[x for x in records if x.get("date") and x.get("date") >= f"{ref.year}-08-01" and parse_day(x["date"]) <= ref]
aug=[x for x in season_rows if x.get("date","").startswith(f"{ref.year}-08")]
sep=[x for x in season_rows if x.get("date","").startswith(f"{ref.year}-09")]
summary={
    "updated_at":stamp,
    "reference_date":iso_day(ref),
    "season_start":f"{ref.year}-08-01",
    "total_records":len(records),
    "source_count":len({x.get("source") for x in records if x.get("source")}),
    "note":"件数は公開Web上で確認できた釣果投稿/釣行記録。実際の資源量・総釣獲量そのものではない。",
    "season":{"total":counts(season_rows),"august":counts(aug),"september":counts(sep),"first_date":min([x.get("date") for x in season_rows],default=None)},
    "areas":areas,
    "daily14":daily
}
Path("data/summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"archive={len(records)} summary={len(areas)}")
