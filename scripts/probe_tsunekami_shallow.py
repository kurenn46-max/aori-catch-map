import json,urllib.request,urllib.parse,time
from pathlib import Path
O=Path("probe-shallow");O.mkdir(exist_ok=True)
KEY="0e83ad5d93214e04abf37c970c32b641"
BBOX={"xmin":135.785,"ymin":35.585,"xmax":135.89,"ymax":35.672,"spatialReference":{"wkid":4326}}
H={"Ocp-Apim-Subscription-Key":KEY,"User-Agent":"TsunekamiDepthResearch/0.4"}
def req(tag,url):
 x={"tag":tag,"url":url}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers=H),timeout=13) as r:
   body=r.read(1000000)
   x["status"]=r.status;x["size"]=len(body)
   try:
    d=json.loads(body);x["preview"]=str(d)[:700];x["layers"]=d.get("layers");x["count"]=d.get("count");x["features"]=len(d.get("features",[]));x["errors"]=d.get("error")
    if d.get("features"):x["sample"]=d["features"][:2]
    (O/(tag+".json")).write_text(json.dumps(d,ensure_ascii=False))
   except: x["preview"]=repr(body[:200])
 except Exception as e:x["error"]=repr(e)
 print(json.dumps(x,ensure_ascii=False),flush=True);return x
def query_url(base):
 args={"where":"1=1","geometry":json.dumps(BBOX),"geometryType":"esriGeometryEnvelope","inSR":"4326","spatialRel":"esriSpatialRelIntersects","returnGeometry":"true","outFields":"*","f":"geojson","resultRecordCount":"500","subscription-key":KEY}
 return base+"/query?"+urllib.parse.urlencode(args)
def run():
 results=[]
 bases=[
  ("v3_seabed_root","https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_nature/FeatureServer?f=pjson&subscription-key="+KEY),
  ("v3_seabed_0",query_url("https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_nature/FeatureServer/0")),
  ("v3_seabed_1",query_url("https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_nature/FeatureServer/1")),
  ("v3_seabed_2",query_url("https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_nature/FeatureServer/2")),
  ("v3_seabed_3",query_url("https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_nature/FeatureServer/3")),
  ("v3_seabed_4",query_url("https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_nature/FeatureServer/4")),
  ("v3_seabed_5",query_url("https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_nature/FeatureServer/5")),
  ("v3_obstacles_root","https://api.msil.go.jp/arcgis/rest/services/FeatureService/v3/seabed_obstacle/FeatureServer?f=pjson&subscription-key="+KEY),
  ("v2_depth_5",query_url("https://api.msil.go.jp/depth-contour/v2/MapServer/5")),
  ("v2_depth_9",query_url("https://api.msil.go.jp/depth-contour/v2/MapServer/9"))
 ]
 for tag,url in bases:results.append(req(tag,url))
 (O/"report.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=="__main__":run()