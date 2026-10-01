import io,json,math,time,urllib.request,urllib.error,concurrent.futures
from pathlib import Path
from PIL import Image, ImageDraw
CENTER=(35+37/60+56.8585/3600,135+48/60+55.0728/3600)
DEST=Path("pdf-source"); DEST.mkdir(exist_ok=True)
HEAD={"User-Agent":"TsunekamiFishingResearchMap/1.0 (non-navigation report)","Accept":"image/avif,image/webp,image/png,image/jpeg,*/*"}
def pix(lat,lon,z):
 n=256*2**z
 x=(lon+180)/360*n
 y=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n
 return x,y
def ll(x,y,z):
 n=256*2**z
 return math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n)))),x/n*360-180
def tile(z,x,y):
 paths=[f"https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg",f"https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"]
 for typ,url in enumerate(paths):
  for i in range(2):
   try:
    rq=urllib.request.Request(url,headers=HEAD)
    with urllib.request.urlopen(rq,timeout=12) as r:data=r.read()
    im=Image.open(io.BytesIO(data));im.load()
    if im.size!=(256,256):raise ValueError('tile wrong size')
    return (z,x,y,im.convert("RGB"),"photo" if typ==0 else "standard",None)
   except Exception as e:
    last=str(e)
    time.sleep(.25)
 return (z,x,y,None,"missing",last)
def work(name,z,w,h):
 cx,cy=pix(*CENTER,z); x0=math.floor(cx-w/2);y0=math.floor(cy-h/2)
 xs=range(x0//256,(x0+w-1)//256+1);ys=range(y0//256,(y0+h-1)//256+1)
 jobs=[(z,x,y) for y in ys for x in xs]
 print('MAP',name,'zoom',z,'tiles',len(jobs),flush=True)
 mosaic=Image.new("RGB",(w,h),"#9fc9d8")
 tally={"photo":0,"standard":0,"missing":0};errors=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
  futs=[pool.submit(tile,*a) for a in jobs]
  for f in concurrent.futures.as_completed(futs):
   zz,x,y,im,kind,err=f.result();tally[kind]+=1
   if im is not None:mosaic.paste(im,(x*256-x0,y*256-y0))
   else:errors.append({"x":x,"y":y,"error":err})
 mosaic.save(DEST/(name+".jpg"),quality=92,subsampling=0)
 bbox=[ll(x0,y0+h,z)[1],ll(x0,y0+h,z)[0],ll(x0+w,y0,z)[1],ll(x0+w,y0,z)[0]]
 meta={"name":name,"zoom":z,"size":[w,h],"origin_px":[x0,y0],"center":CENTER,"bbox_W_S_E_N":bbox,"tiles":tally,"errors":errors}
 print('RESULT',name,json.dumps({k:v for k,v in meta.items() if k!="errors"}),flush=True)
 return meta
if __name__=="__main__":
 a=work("overview",16,1800,1320)
 b=work("detail",17,1800,1300)
 (DEST/"metadata.json").write_text(json.dumps([a,b],ensure_ascii=False,indent=2))
 # Fetch official 2010 PDF for visual verification only, if the site still allows it.
 u="https://www1.kaiho.mlit.go.jp/KAN8/kisha/H22/100729.pdf"
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers=HEAD),timeout=10) as r:data=r.read(12000000)
  if data[:4]==b"%PDF":(DEST/"2010_jcg_tsunekami.pdf").write_bytes(data);print("official_pdf downloaded",len(data),flush=True)
  else:print("official_pdf invalid",data[:80],flush=True)
 except Exception as e:print("official_pdf unavailable",str(e)[:350],flush=True)
 if (a["tiles"]["photo"]+a["tiles"]["standard"])<30 or (b["tiles"]["photo"]+b["tiles"]["standard"])<30:
  raise RuntimeError("Could not obtain enough georeferenced GSI tiles; abort PDF map backgrounds")
