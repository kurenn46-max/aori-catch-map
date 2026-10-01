#!/usr/bin/env python3
"""Build the four-zone Tsunekami map data from the official MSIL API and GMRT.
Only run in CI. Fails closed when expected official contours are unavailable.
"""
import json, math, os, urllib.parse, urllib.request
from pathlib import Path
from shapely.geometry import shape, mapping, box, Point
from shapely.affinity import scale
from shapely.ops import unary_union

OUT=Path("tsunekami-map");OUT.mkdir(exist_ok=True)
BBOX={"xmin":135.792,"ymin":35.592,"xmax":135.880,"ymax":35.663,"spatialReference":{"wkid":4326}}
BOUNDS=box(BBOX["xmin"],BBOX["ymin"],BBOX["xmax"],BBOX["ymax"])
TRIAL="0e83ad5d93214e04abf37c970c32b641"  # Official publicly posted trial key; not a private key
HEADERS={"Ocp-Apim-Subscription-Key":TRIAL,"User-Agent":"TsunekamiShoreMap/0.3"}
def download(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=60) as r:
        return r.read(10000000)

def official_contours():
    features=[];lengths={}
    for depth,layer in ((20,10),(50,11)):
        args={"where":"1=1","geometry":json.dumps(BBOX),"geometryType":"esriGeometryEnvelope","inSR":"4326","spatialRel":"esriSpatialRelIntersects","returnGeometry":"true","outFields":"*","resultRecordCount":"1000","f":"geojson","subscription-key":TRIAL}
        url=f"https://api.msil.go.jp/depth-contour/v2/MapServer/{layer}/query?"+urllib.parse.urlencode(args)
        src=json.loads(download(url))
        assert src.get("type")=="FeatureCollection",f"API failed depth={depth}: {str(src)[:280]}"
        count=0
        for ft in src["features"]:
            actual=int(ft["properties"].get("Depth",depth))
            if actual!=depth:continue
            g=shape(ft["geometry"]).intersection(BOUNDS)
            if g.is_empty:continue
            g=g.simplify(.000025,preserve_topology=True)
            if g.is_empty:continue
            def rounded(g): # GeoJSON, bounded and compact
                m=mapping(g)
                def r(x):
                    if isinstance(x,(tuple,list)):return [r(y) for y in x]
                    return round(float(x),6)
                m["coordinates"]=r(m["coordinates"]);return m
            features.append({"type":"Feature","properties":{"depth_m":depth,"source":"海しるAPI・等深線(v2)","objectid":ft["properties"].get("OBJECTID")},"geometry":rounded(g)})
            count+=1
        lengths[depth]=count
    assert lengths.get(20,0)>=1 and lengths.get(50,0)>=1,f"no official depth contour: {lengths}"
    fc={"type":"FeatureCollection","source":"海しるAPI depth-contour v2; government is not responsible for this app","bbox":[135.792,35.592,135.880,35.663],"features":features}
    (OUT/"contours.geojson").write_text(json.dumps(fc,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    ports={"常神":(35.636976,135.820512),"神子":(35.622245,135.838593),"小川":(35.606744,135.844873),"遊子":(35.602463,135.856136)}
    for dep in (20,50):
        union=unary_union([shape(f["geometry"]) for f in features if f["properties"]["depth_m"]==dep])
        m=scale(union,xfact=91200,yfact=111200,origin=(0,0))
        distances={n:round(m.distance(Point(lo*91200,la*111200))) for n,(la,lo) in ports.items()}
        print("official_depth",dep,"segments",lengths[dep],"nearest_m",json.dumps(distances,ensure_ascii=False))
    return lengths

def coarse_model():
    args={"north":"35.663","south":"35.592","west":"135.792","east":"135.880","format":"esriascii","mresolution":"150","layer":"topo"}
    content=download("https://www.gmrt.org/services/GridServer?"+urllib.parse.urlencode(args)).decode("ascii","replace").splitlines()
    h={}
    for line in content[:8]:
        s=line.split()
        if len(s)==2 and s[0].lower() in ("ncols","nrows","xllcorner","yllcorner","cellsize","nodata_value"):h[s[0].lower()]=float(s[1])
    assert all(x in h for x in ("ncols","nrows","xllcorner","yllcorner","cellsize","nodata_value")),"bad model grid"
    rows=[[float(s) for s in line.split()] for line in content[len(h):]]
    nr,nc=int(h["nrows"]),int(h["ncols"])
    assert len(rows)==nr and all(len(r)==nc for r in rows),"grid dimensions mismatch"
    # Every seventh native cell ~430m; NEVER claim 60-150m survey precision.
    nodes=[]
    for row in range(3,nr-3,7):
      for col in range(3,nc-3,7):
        v=rows[row][col]
        if v>=-5 or v==h["nodata_value"]:continue
        # Exclude coastline transitions: estimated depths very near land are unreliable.
        if any(rows[i][j]>0 for i in range(row-2,row+3) for j in range(col-2,col+3)):continue
        lat=h["yllcorner"]+(nr-row-.5)*h["cellsize"]
        lon=h["xllcorner"]+(col+.5)*h["cellsize"]
        nodes.append([round(lat,6),round(lon,6),int(round(-v/5)*5)])
    assert len(nodes)>30,"no coarse model coverage"
    (OUT/"coarse.json").write_text(json.dumps({"source":"GMRT 4.5, June 2026 unmasked; ocean cells not confirmed as high-resolution measured data","sample_spacing_m_approx":430,"value":"rounded model estimate, NOT soundings, unsafe for navigation","nodes":nodes},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("coarse_nodes",len(nodes),"depth_range_m",(min(x[2] for x in nodes),max(x[2] for x in nodes)))
if __name__=="__main__":
    official_contours();coarse_model()
