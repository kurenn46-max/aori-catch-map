#!/usr/bin/env python3
import json
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import requests
from bs4 import BeautifulSoup

HEADERS = {
  "User-Agent": "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141 Mobile Safari/537.36",
  "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.5",
}
QUERIES = [
  "丹後 アオリイカ ティップラン 遊漁船",
  "舞鶴 アオリイカ ティップラン 水深",
]
ENGINES = [
  ("bing_html", "https://www.bing.com/search?q={q}&cc=jp&setlang=ja-JP"),
  ("brave_html", "https://search.brave.com/search?q={q}&source=web"),
  ("mojeek_html", "https://www.mojeek.com/search?q={q}"),
  ("yahoo_jp", "https://search.yahoo.co.jp/search?p={q}"),
]
TARGETS = ("アオリ","ティップラン","遊漁船","釣果","水深","舞鶴","丹後")

def ext_links(html, engine_host):
    soup=BeautifulSoup(html,"html.parser")
    rows=[]
    seen=set()
    for a in soup.find_all("a", href=True):
        href=a.get("href","")
        text=" ".join(a.stripped_strings)
        if href.startswith("//"):
            href="https:"+href
        if not href.startswith("http"):
            continue
        host=(urlparse(href).hostname or "").lower()
        if not host or engine_host in host:
            continue
        # unwrap common redirects when obvious
        qs=parse_qs(urlparse(href).query)
        for key in ("url","u","target","uddg"):
            if qs.get(key):
                cand=unquote(qs[key][0])
                if cand.startswith("http"):
                    href=cand
                    host=(urlparse(href).hostname or "").lower()
                    break
        key=href.split("#",1)[0]
        if key in seen:
            continue
        seen.add(key)
        rows.append({"text":text[:160],"url":key,"host":host})
    return rows[:30]

out=[]
for query in QUERIES:
    for name,tpl in ENGINES:
        url=tpl.format(q=quote_plus(query))
        item={"query":query,"engine":name,"url":url}
        try:
            r=requests.get(url,headers=HEADERS,timeout=(7,20),allow_redirects=True)
            text=r.text
            host=(urlparse(r.url).hostname or "").lower()
            links=ext_links(text,host.split(".")[-2] if "." in host else host)
            item.update({
                "status":r.status_code,
                "bytes":len(r.content),
                "final_url":r.url,
                "title":(BeautifulSoup(text,"html.parser").title.get_text(" ",strip=True) if BeautifulSoup(text,"html.parser").title else "")[:180],
                "target_hits":{w:text.count(w) for w in TARGETS if w in text},
                "external_links":len(links),
                "samples":links[:8],
            })
        except Exception as e:
            item["error"]=f"{type(e).__name__}: {e}"[:240]
        out.append(item)
print(json.dumps(out,ensure_ascii=False,indent=2))
