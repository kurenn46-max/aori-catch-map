#!/usr/bin/env python3
import json, re, hashlib, html
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

JST=timezone(timedelta(hours=9))
NOW=datetime.now(JST)
MAX_DAYS=30
UA={"User-Agent":"Mozilla/5.0 (compatible; AoriCatchMap/1.2; +https://github.com/kurenn46-max/aori-catch-map)"}

YAMARIA=[
 ("越前","越前",86,35.914,135.991),
 ("敦賀","敦賀",85,35.645,136.055),
 ("若狭","小浜",84,35.495,135.746),
 ("舞鶴","舞鶴",114,35.474,135.386),
 ("丹後","丹後",115,35.650,135.150),
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

def age_ok(date):
    try:d=datetime.strptime(date,"%Y-%m-%d").replace(tzinfo=JST)
    except ValueError:return False
    return 0 <= (NOW-d).days <= MAX_DAYS

def yamaria_rows(area,place,city_id,lat,lng):
    url=f"https://www.yamaria.com/community/catch/egiou/cities/{city_id}"
    r=requests.get(url,headers=UA,timeout=25)
    r.raise_for_status()
    text=BeautifulSoup(r.text,"html.parser").get_text(" ",strip=True)
    # Each latest result contains HIT, user, date/time, size class, area and fishing-place type.
    pat=re.compile(
      r"(\d+)\s*HIT\s+(.+?)\s+さん\s+(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+"
      r"アオリイカ：\s*([^\s]+)\s+釣果場所：\s*([^\s]+)\s+([^\s]+)\s+釣り場所：\s*([^\s]+)"
    )
    rows=[]
    for m in pat.finditer(text):
        hits,user,date,tm,size,pref,reported_place,fish_place=m.groups()
        if not age_ok(date):continue
        typ="boat" if any(k in fish_place for k in ["ボート","船"]) else "shore"
        method="ティップラン" if typ=="boat" else "エギング"
        shown_place=reported_place if reported_place not in ["福井","京都"] else place
        plat,plng=POINTS.get(shown_place,(lat,lng))
        raw=m.group(0)
        rid=hashlib.sha1((url+raw).encode()).hexdigest()[:14]
        rows.append({
          "id":rid,"date":date,"area":area,"place":shown_place,
          "lat":plat,"lng":plng,"type":typ,"method":method,
          "count":None,"maxSize":size,"time":tm,
          "source":"エギCOM","url":url,"title":f"{user}さん / {fish_place}",
          "demo":False,"precision":"area","reportPlace":fish_place
        })
    print(f"エギCOM / {place}: {len(rows)}")
    return rows

def rss_items(query):
    q=quote_plus(query)
    feeds=[
      ("Google News",f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"),
      ("Bing News",f"https://www.bing.com/news/search?q={q}&format=rss&setlang=ja-jp")
    ]
    out=[]
    for provider,url in feeds:
        try:
            r=requests.get(url,headers=UA,timeout=25); r.raise_for_status()
            root=ET.fromstring(r.content)
            for item in root.findall(".//item"):
                source=item.find("source")
                out.append({
                  "provider":provider,"title":clean(item.findtext("title") or ""),
                  "desc":clean(item.findtext("description") or ""),
                  "link":clean(item.findtext("link") or ""),
                  "published":clean(item.findtext("pubDate") or ""),
                  "source":clean(source.text if source is not None else provider)
                })
        except Exception as e: print(f"WARN RSS {provider}: {e}")
    return out

def rss_rows():
    rows=[]
    queries=[
      ("越前","越前",35.914,135.991,"アオリイカ 越前 エギング 釣果"),
      ("敦賀","敦賀",35.645,136.055,"アオリイカ 敦賀 エギング 釣果"),
      ("若狭","小浜",35.495,135.746,"アオリイカ 小浜 エギング 釣果"),
      ("舞鶴","舞鶴",35.474,135.386,"アオリイカ 舞鶴 エギング 釣果"),
      ("丹後","丹後",35.650,135.150,"アオリイカ 丹後 ティップラン 釣果"),
    ]
    for area,place,lat,lng,q in queries:
      for it in rss_items(q):
        # High precision rule: Aori must be explicit in the headline.
        if "アオリ" not in it["title"]:continue
        try:d=parsedate_to_datetime(it["published"]).astimezone(JST)
        except Exception:continue
        if not (0 <= (NOW-d).days <= MAX_DAYS):continue
        title=it["title"]
        typ="boat" if any(k in title for k in ["ティップラン","船","ボート","沖"]) else "shore"
        method="ティップラン" if typ=="boat" else "エギング"
        rid=hashlib.sha1((it["link"]+area).encode()).hexdigest()[:14]
        rows.append({
          "id":rid,"date":d.date().isoformat(),"area":area,"place":place,
          "lat":lat,"lng":lng,"type":typ,"method":method,"count":None,
          "maxSize":"不明","time":"不明","source":it["source"] or it["provider"],
          "url":it["link"],"title":title[:120],"demo":False,"precision":"area"
        })
    return rows

def main():
    rows=[]; seen=set()
    for args in YAMARIA:
        try: batch=yamaria_rows(*args)
        except Exception as e:
            print(f"WARN エギCOM {args[1]}: {e}"); batch=[]
        for x in batch:
            k=(x["date"],x["area"],x["place"],x["type"],x["time"],x["title"])
            if k not in seen:seen.add(k);rows.append(x)
    for x in rss_rows():
        k=(x["url"],x["type"])
        if k not in seen:seen.add(k);rows.append(x)
    rows.sort(key=lambda x:(x["date"],x.get("time","")),reverse=True)
    if not rows:
        print("No fresh records found; existing data preserved.")
        return
    Path("data").mkdir(exist_ok=True)
    Path("data/catches.json").write_text(json.dumps({
      "updated_at":NOW.isoformat(timespec="seconds"),
      "note":"エギCOM公開最新釣果を主データに、公開ニュースRSSを補助データとして自動収集。地点はエリア概算。",
      "catches":rows[:300]
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {len(rows[:300])} records")

if __name__=="__main__":
    main()
