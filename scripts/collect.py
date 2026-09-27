#!/usr/bin/env python3
import json, re, hashlib, html
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
import requests

JST=timezone(timedelta(hours=9))
NOW=datetime.now(JST)
MAX_DAYS=30
UA={"User-Agent":"Mozilla/5.0 (compatible; AoriCatchMap/1.1; +https://github.com/kurenn46-max/aori-catch-map)"}

AREAS=[
 ("越前","越前",35.914,135.991),("敦賀","敦賀",35.645,136.055),
 ("若狭","若狭",35.555,135.760),("若狭","小浜",35.495,135.746),
 ("舞鶴","舞鶴",35.474,135.386),("丹後","丹後",35.650,135.150),
 ("丹後","伊根",35.674,135.287)
]
POINTS={
 "越前海岸":(35.914,135.991),"越前岬":(35.980,135.958),"甲楽城":(35.827,136.020),
 "敦賀湾":(35.681,136.049),"常神":(35.608,135.833),"常神半島":(35.608,135.833),
 "小浜":(35.495,135.746),"小浜湾":(35.521,135.720),"高浜":(35.489,135.551),
 "白杉":(35.500,135.337),"舞鶴":(35.474,135.386),"舞鶴湾":(35.507,135.376),
 "伊根":(35.674,135.287),"宮津":(35.535,135.196),"京丹後":(35.650,135.060)
}

def clean(s):
    s=html.unescape(re.sub(r"<[^>]+>"," ",s or ""))
    return re.sub(r"\s+"," ",s).strip()

def feeds_for(query):
    q=quote_plus(query)
    return [
      ("Google News",f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"),
      ("Bing News",f"https://www.bing.com/news/search?q={q}&format=rss&setlang=ja-jp")
    ]

def parse_date(s):
    try:
        d=parsedate_to_datetime(s)
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(JST)
    except Exception:
        return None

def infer_count(text):
    vals=[]
    for m in re.finditer(r"(?<!\d)(\d{1,3})\s*(?:杯|ハイ|匹|枚)",text):
        n=int(m.group(1))
        if 0<n<=100: vals.append(n)
    return max(vals) if vals else 1

def infer_size(text):
    m=re.search(r"胴長\s*(\d+(?:\.\d+)?)\s*cm",text)
    if m:return "胴長"+m.group(1)+"cm"
    m=re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*kg",text,re.I)
    if m:return m.group(1)+"kg"
    return "不明"

def infer_place(text,term,lat,lng):
    for p,(a,b) in POINTS.items():
        if p in text:return p,a,b
    return term,lat,lng

def read_feed(provider,url):
    r=requests.get(url,headers=UA,timeout=25)
    r.raise_for_status()
    root=ET.fromstring(r.content)
    out=[]
    for item in root.findall(".//item"):
        get=lambda tag: (item.findtext(tag) or "")
        source=item.find("source")
        out.append({
          "title":clean(get("title")),
          "desc":clean(get("description")),
          "link":clean(get("link")),
          "published":clean(get("pubDate")),
          "source":clean(source.text if source is not None else provider)
        })
    return out

def main():
    rows=[]; seen=set()
    for area,term,lat,lng in AREAS:
        for typ,extra,method in [
          ("shore","エギング","エギング"),
          ("boat","ティップラン","ティップラン")
        ]:
            query=f'アオリイカ {term} {extra} 釣果'
            for provider,url in feeds_for(query):
                try:
                    items=read_feed(provider,url)
                    print(f"{provider} / {term} / {typ}: {len(items)}")
                except Exception as e:
                    print(f"WARN {provider} {term}: {e}")
                    continue
                for it in items:
                    d=parse_date(it["published"])
                    if not d: continue
                    age=(NOW-d).days
                    if age<0 or age>MAX_DAYS: continue
                    blob=clean(it["title"]+" "+it["desc"])
                    if "アオリ" not in blob: continue
                    # Avoid obvious non-target fishing unless Aori is central in the title.
                    place,plat,plng=infer_place(blob,term,lat,lng)
                    key=(it["link"],typ)
                    if key in seen: continue
                    seen.add(key)
                    rid=hashlib.sha1((it["link"]+typ).encode()).hexdigest()[:14]
                    rows.append({
                      "id":rid,"date":d.date().isoformat(),"area":area,"place":place,
                      "lat":plat,"lng":plng,"type":typ,"method":method,
                      "count":infer_count(blob),"maxSize":infer_size(blob),"time":"不明",
                      "source":it["source"] or provider,"url":it["link"],
                      "title":it["title"][:120],"demo":False,"precision":"area"
                    })
    rows.sort(key=lambda x:(x["date"],x["area"],x["place"]),reverse=True)
    if not rows:
        print("No fresh RSS records found; existing data preserved.")
        return
    payload={
      "updated_at":NOW.isoformat(timespec="seconds"),
      "note":"公開RSS検索から自動収集。陸/ボートは検索条件で分類。場所が本文から特定できない場合はエリア概算位置。",
      "catches":rows[:250]
    }
    p=Path("data/catches.json")
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {len(rows[:250])} records")

if __name__=="__main__":
    main()
