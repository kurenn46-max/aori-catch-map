import json, os, urllib.parse, urllib.request, ssl, re, traceback
from pathlib import Path
P=Path("depth-probe");P.mkdir(exist_ok=True)
ctx=ssl.create_default_context()
UA={"User-Agent":"OkaShoreMapResearch/1.0 (bathymetry prototype)","Accept":"*/*"}
def get(tag,url,timeout=42):
  entry={"tag":tag,"url":url}
  try:
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout,context=ctx) as r:
      data=r.read(14000000)
      entry.update({"status":r.status,"type":r.headers.get("Content-Type"),"bytes":len(data),"urlFinal":r.url,"preview":repr(data[:260])})
    ext="pdf" if data[:4]==b"%PDF" else "png" if data[:4]==b"\x89PNG" else "asc" if b"ncols" in data[:90].lower() else "txt"
    (P/(tag+"."+ext)).write_bytes(data)
    if ext=="asc":
      rows=data.decode("utf-8",errors="replace").splitlines()
      entry["lines"]=len(rows);entry["head"]=rows[:9]
      try:
        header={}
        for line in rows[:8]:
          s=line.split()
          if len(s)==2 and s[0].lower() in ("ncols","nrows","xllcorner","yllcorner","xllcenter","yllcenter","cellsize","nodata_value"):header[s[0].lower()]=float(s[1])
        entry["header"]=header
        ncols=int(header["ncols"]);nrows=int(header["nrows"])
        body=rows[len(header):];valid=[];nodata=header.get("nodata_value",-9999)
        for row in body:
          for val in row.split():
            try:
              v=float(val)
              if v!=nodata and -2000<v<3000: valid.append(v)
            except ValueError:pass
        entry["values"]={"num_valid":len(valid),"num_below_zero":sum(v<0 for v in valid),"min":min(valid) if valid else None,"max":max(valid) if valid else None,"sum_cells":ncols*nrows}
      except Exception as e:entry["parseError"]=str(e)
  except Exception as e:entry["error"]=repr(e)
  return entry
def go():
  bbox={"north":"35.663","south":"35.592","west":"135.792","east":"135.880"}
  base="https://www.gmrt.org/services/"
  q=urllib.parse.urlencode(dict(bbox,format="esriascii",mresolution="150"))
  queries=[
    ("gmrt_mask",base+"GridServer?"+q+"&layer=topo-mask"),
    ("gmrt_all",base+"GridServer?"+q+"&layer=topo"),
    ("gmrt_metadata",base+"GridServer/metadata?"+urllib.parse.urlencode(dict(bbox,format="esriascii",mresolution="150",mformat="json"))),
    ("jcg_2010","https://www1.kaiho.mlit.go.jp/KAN8/kisha/H22/100729.pdf"),
    ("gebco_cap","https://wms.gebco.net/mapserv?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0")
  ]
  sites={"tsunekami":[35.636976,135.820512],"miko":[35.622245,135.838593],"ogawa":[35.606744,135.844873],"yushi":[35.602463,135.856136]}
  for name,(lat,lon) in sites.items():
    for direction,dlat,dlon in [("N",.003,0),("W",0,-.003)]:
      queries.append((f"point_{name}_{direction}",base+"PointServer?"+urllib.parse.urlencode({"latitude":lat+dlat,"longitude":lon+dlon,"format":"json"})))
  report=[]
  for tag,url in queries:
    entry=get(tag,url);report.append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
  (P/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=="__main__":go()