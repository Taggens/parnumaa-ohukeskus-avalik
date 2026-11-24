"""KAIA official radar COMP data reader, georeferenced overlay, conservative echo masks.

KAIA supplies five-minute HDF5 ODIM COMP files merged from Harku/Sürgavere.
Only a verified RATE (mm/h) COMP product is accepted. No RainViewer fallback.
This module requires numpy, h5py, Pillow and pyproj (set up separately).
"""
from __future__ import annotations

import math
import base64
import datetime as dt
import io
import json
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path

API_URL = 'https://avaandmed.keskkonnaportaal.ee/api/lists/active/items/query'
ROOT_URL = 'https://avaandmed.keskkonnaportaal.ee/api/lists/active/items'
MAX_META_BYTES = 2_000_000
MAX_HDF_BYTES = 32_000_000
MAX_AGE = 35 * 60
CACHE_KEEP = 16
# The KEA public radar legend's precipitation intensity thresholds (mm/h).
LEVELS = [0.05, 0.1, 0.3, 0.5, 1, 2, 4, 8, 16, 50]
# Ohukeskus color representation; thresholds follow the official intensity legend.
COLORS = [
    (142, 221, 243), (85, 187, 240), (52, 147, 218), (30, 108, 199),
    (38, 166, 139), (75, 188, 86), (227, 212, 61), (253, 156, 48),
    (236, 65, 61), (184, 57, 171),
]


def _deps():
    try:
        import numpy as np
        import h5py
        from PIL import Image
        from pyproj import CRS, Transformer
    except ImportError as e:
        raise RuntimeError('KAIA radar vajab teeke numpy, h5py, Pillow ja pyproj. Käivita SEADISTA_KAIA_RADAR_WINDOWS.bat') from e
    return np, h5py, Image, CRS, Transformer


def _date_of(raw):
    if isinstance(raw, bytes): raw = raw.decode('ascii', 'strict')
    if isinstance(raw, str):
        d = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if d.tzinfo is None: raise ValueError('Puudub KAIA ajatemplil ajavöönd')
        return int(d.timestamp())
    raise ValueError('KAIA timestamp ei ole ISO-8601 tekst')


def query_body(now=None):
    now = time.time() if now is None else now
    cutoff = dt.datetime.fromtimestamp(now - 2 * 3600, dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    return {'filter':{'and':{'children':[
        {'isEqual':{'field':'$contentType','value':'0102FB01'}},
        {'isEqual':{'field':'Phenomenon','value':'COMP'}},
        {'greaterThan':{'field':'Timestamp','value':cutoff}},
    ]}},'pageSize':100,'includeFileMetadata':True,'fields':['Timestamp','Radar','Phenomenon']}


def _open(request, limit, timeout=18):
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200: raise ValueError(f'KAIA server: HTTP {response.status}')
        length = response.headers.get('Content-Length')
        if length and int(length)>limit: raise ValueError('KAIA vastuse maht ületas ohutuspiiri')
        raw = response.read(limit+1)
        if len(raw)>limit: raise ValueError('KAIA vastus ületas ohutuspiiri')
        return raw


def list_files(now=None, requester=None):
    now = time.time() if now is None else now
    requester = requester or _open
    body = query_body(now)
    result=[]
    seen=set()
    for _ in range(3):
        req=urllib.request.Request(API_URL, data=json.dumps(body).encode('utf-8'),method='POST',
              headers={'User-Agent':'Parnumaa-Ohukeskus/0.5.3', 'Content-Type':'application/json','Accept':'application/json'})
        response=json.loads(requester(req,MAX_META_BYTES))
        if not isinstance(response,dict) or not isinstance(response.get('documents'),list):
            raise ValueError('KAIA metaandmete vastus on vale kujuga')
        for document in response['documents']:
            if not isinstance(document,dict):continue
            meta=document.get('metadata') or {}
            if not isinstance(meta,dict):continue
            if meta.get('Phenomenon')!='COMP':continue
            try: stamp=_date_of(meta.get('Timestamp'))
            except (TypeError, ValueError):continue
            if not -300<=now-stamp<=MAX_AGE:continue
            item_id=document.get('id')
            if type(item_id)!=int or item_id<1:continue
            files=document.get('fileMetadata') or []
            if not files:continue
            f=files[0]
            file_id=f.get('id',0)
            size=f.get('size',0)
            if type(file_id)!=int or file_id<0 or type(size)!=int or size<0 or size>MAX_HDF_BYTES:continue
            name=f.get('name','')
            if name and not isinstance(name,str):continue
            # File-name checks are sanity checks only; the ODIM metadata is authoritative.
            if name and not name.lower().endswith(('.h5','.hdf5')):continue
            if stamp in seen:continue
            seen.add(stamp)
            result.append({'time':stamp,'url':f'{ROOT_URL}/{item_id}/files/{file_id}',
                           'name':name,'bytes':size})
        bookmark=response.get('nextBookmark')
        if not isinstance(bookmark,str) or not bookmark:break
        body['bookmark']=bookmark
    return sorted(result,key=lambda x:x['time'])


def fetch_one(frame,cache:Path,requester=None):
    cache=Path(cache);cache.mkdir(exist_ok=True,parents=True)
    file=cache / f'{int(frame["time"])}.h5'
    if file.exists() and 256 < file.stat().st_size <= MAX_HDF_BYTES:
        # HDF5 content is still validated before display.
        return file
    requester=requester or _open
    req=urllib.request.Request(frame['url'],headers={'User-Agent':'Parnumaa-Ohukeskus/0.5.3','Accept':'application/octet-stream'})
    raw=requester(req,MAX_HDF_BYTES,timeout=35) if requester is _open else requester(req,MAX_HDF_BYTES)
    if not raw.startswith(b'\x89HDF\r\n\x1a\n'):raise ValueError('KAIA vastus ei olnud HDF5 (võimalik serveri vealeht)')
    with tempfile.NamedTemporaryFile(dir=cache,suffix='.part',delete=False) as t:
        t.write(raw)
        tmp=Path(t.name)
    try:os.replace(tmp,file)
    finally:tmp.unlink(missing_ok=True)
    return file


def _attrs(group):
    return dict(group.attrs.items()) if group is not None else {}


def _str(value):
    if isinstance(value,bytes):return value.decode('utf-8','replace')
    return str(value)


def read_hdf(path, expected_utc=None):
    np,h5py,_,CRS,Transformer=_deps()
    with h5py.File(path,'r') as h5:
        if not all(g in h5 for g in ('what','where','dataset1','dataset1/data1/data')):
            raise ValueError('KAIA HDF5 ODIM kohustuslik struktuur puudub')
        top=_attrs(h5['what']);where=_attrs(h5['where'])
        dwhat=_attrs(h5['dataset1/what']) if 'dataset1/what' in h5 else {}
        datawhat=_attrs(h5['dataset1/data1/what']) if 'dataset1/data1/what' in h5 else {}
        if _str(top.get('object'))!='COMP':raise ValueError('Radarifail ei ole COMP-komposiit')
        quantity=_str(datawhat.get('quantity',dwhat.get('quantity','')))
        if quantity != 'RATE':raise ValueError('Komposiit ei ole sademete intensiivsus RATE (mm/h)')
        dtstr=_str(top.get('date',''))+_str(top.get('time',''))
        if not re.fullmatch(r'\d{14}',dtstr):raise ValueError('HDF5 mõõtmise ajatempel puudub')
        stamp=int(dt.datetime.strptime(dtstr,'%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc).timestamp())
        if expected_utc is not None and abs(int(expected_utc)-stamp)>20*60:
            raise ValueError('KAIA faili ja metaandmete ajad ei ühti')
        raw=h5['dataset1/data1/data']
        if len(raw.shape)!=2 or min(raw.shape)<100 or max(raw.shape)>3200:
            raise ValueError('Ootamatu radari maatriksi mõõt')
        v=np.asarray(raw[()],dtype=np.float32)
        params={**dwhat,**datawhat}
        try:
            gain=float(params['gain']);offset=float(params['offset'])
            nodata=float(params['nodata']);undetect=float(params['undetect'])
        except (KeyError,ValueError,TypeError) as e:raise ValueError('RATE kalibreerimisparameetrid puuduvad') from e
        if not (0<gain<=10 and -100<=offset<=100 and nodata>=0):raise ValueError('RATE kalibreerimisväärtused kahtlased')
        valid=np.isfinite(v)&(v!=nodata)
        # Don't infer "dry" from missing coverage. Undetect is valid but below sensor detection.
        v=np.where(valid&(v!=undetect),v*gain+offset,np.where(valid,0.,np.nan))
        if np.count_nonzero(valid)<v.size*0.02:raise ValueError('Radarikomposiidil pole piisavalt andmekatet')
        if np.nanmin(v)<0 or np.nanmax(v)>3000:raise ValueError('Kahtlased RATE väärtused')
        coords=[]
        for tag in ('UL','UR','LR','LL'):
            try:coords.append([float(where[tag+'_lon']),float(where[tag+'_lat'])])
            except (KeyError,ValueError,TypeError) as e:raise ValueError('KAIA radari geograafilised nurgad puuduvad') from e
        if any(not (15<=lon<=35 and 53<=lat<=65) for lon,lat in coords):
            raise ValueError('Komposiidi geograafiline asukoht pole Eesti radariga kooskõlas')
        nodes=_str(_attrs(h5['how']).get('nodes','')) if 'how' in h5 else ''
        proj=_str(where.get('projdef',''))
        if not proj or '+proj=' not in proj:raise ValueError('Komposiidi projektsioon puudub')
        # Use the measured ODIM four corners. Do not assume a LatLon rectangle.
        # MapLibre image source georeferences the four corners in Mercator space.
    return {'time':stamp,'rate':v,'valid':valid,'coords':coords,'projdef':proj,'quantity':'RATE',
            'source':'Keskkonnaagentuur KAIA COMP', 'nodes':nodes}


def write_png(info,outfile):
    np,_,Image,_,_=_deps()
    v=info['rate']; valid=info['valid']
    indexes=np.searchsorted(np.array(LEVELS),np.nan_to_num(v,nan=-1),side='right')-1
    rgba=np.zeros((v.shape[0],v.shape[1],4),dtype=np.uint8)
    shown=valid & (v>=LEVELS[0]) & (v<=1000)
    palette=np.asarray(COLORS,dtype=np.uint8)
    rgba[shown,:3]=palette[np.clip(indexes[shown],0,len(COLORS)-1)]
    rgba[shown,3]=210
    image=Image.fromarray(rgba,'RGBA')
    out=io.BytesIO();image.save(out,format='PNG',compress_level=6)
    data=out.getvalue()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('PNG teisendus ebaõnnestus')
    Path(outfile).write_bytes(data)
    return {'width':v.shape[1],'height':v.shape[0],'bytes':len(data),
            'rain_pixels':int(shown.sum()),'covered_pixels':int(valid.sum())}


ZOOM = 7  # RainViewer free API max native zoom as of 2026
TILE_SIZE = 256
STEP = 2  # analysis grid resolution: 2 native pixels (~1.3 km near Pärnu)
SHIFT_MAX = 11  # cells per 10-min frame (about 85 km/h near Pärnu)
FRAME_MIN_GAP = 4 * 60  # KAIA five-minute timestamps have second-level jitter.
FRAME_MAX_GAP = 15 * 60
MAX_AGE_SECONDS = 30 * 60
FRAMES_REQUIRED = 3
POINTS = {
    'Pärnu linn': (58.3859, 24.4971),
    'Pärnu rand': (58.3765, 24.4845),
    'Häädemeeste': (58.0825, 24.4950),
    'Tõstamaa': (58.3339, 23.9921),
    'Sindi': (58.3990, 24.6550),
}
# Covers the west/southwestern upwind region and all five target points.
# It is NOT Pärnumaa's administrative boundary.
AREA_LON_LAT = (22.8, 57.75, 26.2, 58.95)


def lonlat_to_global(lon, lat):
    n = (2 ** ZOOM) * TILE_SIZE
    lat = max(-85.0511, min(85.0511, lat))
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _filter_area(points):
    west,south,east,north=AREA_LON_LAT
    xlo,ylo=lonlat_to_global(west,north)
    xhi,yhi=lonlat_to_global(east,south)
    lo_x,hi_x=xlo/STEP,xhi/STEP
    lo_y,hi_y=ylo/STEP,yhi/STEP
    return {p for p in points if lo_x<=p[0]<=hi_x and lo_y<=p[1]<=hi_y}


def _denoise(mask):
    if not mask:return set()
    return {p for p in mask if sum((p[0]+dx,p[1]+dy) in mask
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)))>=2}


def _best_shift(before,after,max_shift=SHIFT_MAX):
    """Find best binary-mask translation. Report overlap and improvement vs no shift."""
    if min(len(before),len(after))<45:
        return None
    a=list(before)
    if len(a)>4000:
        # Deterministic subsampling avoids excessively costly pair matching.
        a=sorted(a)[::math.ceil(len(a)/4000)]
    baseline=sum((x,y) in after for x,y in a)/len(a)
    best=(-1,None,None)
    second=(-1,None,None)
    for dy in range(-max_shift,max_shift+1):
        for dx in range(-max_shift,max_shift+1):
            overlap=sum((x+dx,y+dy) in after for x,y in a)/len(a)
            candidate=(overlap,dx,dy)
            if overlap>best[0]:
                second=best;best=candidate
            elif overlap>second[0]:second=candidate
    return {'dx':best[1],'dy':best[2], 'overlap':best[0],
            'baseline':baseline,'gain':best[0]-baseline,
            'runner_up':second[0], 'counts':[len(before),len(after)]}


def estimate_mask_motion(masks:list[set], stamps:list[int], now=None):
    """KAIA RATE echo movement and conservative 5-minute-step arrival *window*.

    Uses the latest three real, timestamped HDF masks. Rejects ambiguous or
    unphysical translation. A positive ETA describes *radar echo*, NOT rain
    reaching the ground. Never turns an absent echo into a dry-weather claim.
    Existing backend/frontend and verification fields are kept intact.
    """
    now=time.time() if now is None else now
    status={'quality':'unverified','motion_verified':False,'eta_verified':False,
            'latest_frame_utc':stamps[-1] if stamps else None,'targets':[],
            'method_revision':'kaia_eta_v2',
            'reason':'Radari kaja liikumist ei saanud usaldusväärselt hinnata.'}
    if len(masks)!=3 or len(stamps)!=3:
        status['reason']='Vaja on kolme tegelikku järjestikust KAIA radarikaadrit.';return status
    if not all(isinstance(t,(int,float)) and math.isfinite(t) for t in stamps):
        status['reason']='Radari mõõtmise ajad pole kinnitatud.';return status
    if any(not FRAME_MIN_GAP<=stamps[i+1]-stamps[i]<=FRAME_MAX_GAP for i in (0,1)):
        status['reason']='Kaadrite ajavahemikud pole liikumise määramiseks sobivad.';return status
    if not -120<=now-stamps[-1]<=15*60:
        status['reason']='Viimane radarikaader on saabumisaja arvutamiseks aegunud.';return status
    clean=[_denoise(_filter_area(m)) for m in masks]
    if min(map(len,clean))<45:
        status['reason']='Piirkonnas pole piisavalt püsivat radarikaja liikumise määramiseks.';return status
    shifts=[_best_shift(clean[i],clean[i+1]) for i in range(2)]
    if not all(shifts):
        status['reason']='Radari liikumise võrdlus ebaõnnestus.';return status
    if any(s['overlap']<0.48 or s['gain']<0.065 for s in shifts):
        status['reason']='Sajuala kuju muutub või nihe pole piisavalt üheselt määratav.';return status
    if any(abs(s['dx'])>=SHIFT_MAX or abs(s['dy'])>=SHIFT_MAX for s in shifts):
        status['reason']='Radarikaja nihe jääb otsinguvahemiku piirile.';return status
    displacement_disagreement=math.hypot(shifts[0]['dx']-shifts[1]['dx'],
                                         shifts[0]['dy']-shifts[1]['dy'])
    if displacement_disagreement>2.2:
        status['reason']='Järjestikustel kaadritel on vastuoluline liikumissuund.';return status
    dx=sum(s['dx']/(stamps[i+1]-stamps[i]) for i,s in enumerate(shifts))/2
    dy=sum(s['dy']/(stamps[i+1]-stamps[i]) for i,s in enumerate(shifts))/2
    if math.hypot(dx,dy)*600<0.9:
        status['reason']='Liikumine on radari analüüsi lahutusvõimest väiksem.';return status
    meters_per_px=math.cos(math.radians(58.38))*2*math.pi*6371008.8/(2**ZOOM*TILE_SIZE)
    speed_kmh=math.hypot(dx,dy)*STEP*meters_per_px*3.6
    if not 3<=speed_kmh<=115:
        status['reason']='Arvutatud radarikaja liikumiskiirus pole usutav.';return status
    bearing=(math.degrees(math.atan2(dx,-dy))+360)%360
    compass=['põhja','kirde','itta','kagu','lõunasse','edela','läände','loode']
    direction=compass[int((bearing+22.5)//45)%8]
    status.update({'quality':'estimated','motion_verified':True,'heading_degrees':round(bearing),
                   'moving_toward':direction,'speed_kmh_approx':round(speed_kmh),
                   'pair_agreement':round(sum(x['overlap'] for x in shifts)/2,2),
                   'arrival_resolution_minutes':5,
                   'reason':'Kahe järjestikuse KAIA ajavahemiku radarikaja nihe on kooskõlas. '
                            'Hinnatakse kajavälja, mitte mõõdetud maapinnasadu.'})
    latest=clean[-1]
    targets=[]
    for name,(lat,lon) in POINTS.items():
        px,py=lonlat_to_global(lon,lat)
        px/=STEP;py/=STEP
        # ~6 km vicinity; require >=7 coherent pixels on two projected steps.
        def count_near(minutes):
            sx,sy=dx*minutes*60,dy*minutes*60
            return sum((x+sx-px)**2+(y+sy-py)**2<=25 for x,y in latest)
        if count_near(0)>=7:
            targets.append({'name':name,'status':'radarikaja kohal','eta_minutes':None,
                            'detail':'Radarikaja on juba asukoha lähedal; maapinnasadu on kinnitamata.'})
            continue
        eta=None
        for minutes in range(5,90,5):
            # Reject a one-step grazing echo or an isolated echo pixel.
            if count_near(minutes)>=7 and count_near(minutes+5)>=7:
                eta=minutes
                break
        if eta is not None:
            uncertainty=5*max(2,math.ceil((5+eta/4)/5))  # 10-30 min, longer horizon less certain
            earliest=max(0,eta-uncertainty)
            latest_min=min(90,eta+uncertainty)
            targets.append({'name':name,'status':'võimalik saabumine','eta_minutes':eta,
                            'eta_from_frame_utc':int(stamps[-1]+eta*60),
                            'eta_window_start_utc':int(stamps[-1]+earliest*60),
                            'eta_window_end_utc':int(stamps[-1]+latest_min*60),
                            'eta_uncertainty_minutes':uncertainty,
                            'detail':'KAIA radarikaja nihke-ekstrapolatsioon 5 min sammuga. '
                                     'Ajavahemik on hinnanguline, mitte ametlik sajuprognoos.'})
        else:
            targets.append({'name':name,'status':'saabumist ei saa kinnitada','eta_minutes':None,
                            'detail':'Liikumise põhjal uut radarikaja saabumist ei kinnitatud; '
                                     'see ei tõenda sademeteta ilma.'})
    status['targets']=targets
    status['eta_verified']=False  # A forecast is never a verified observation.
    return status


def echo_observations(masks: list[set], stamps: list[int]) -> list[dict]:
    """Independent, point-specific radar *echo* checks on decoded PNG frames.

    Threshold is the same as the existing movement display (>=7 denoised
    sampled pixels inside about 6 km). A negative echo is NOT proof of dry
    weather, radar network coverage, or surface rainfall absence.
    """
    if len(masks) != len(stamps):
        raise ValueError('Radarikaadrite ja ajatemplite arv ei ühti')
    results=[]
    for stamp, mask in zip(stamps, masks):
        clean=_denoise(_filter_area(mask))
        targets=[]
        for name,(lat,lon) in POINTS.items():
            x,y=lonlat_to_global(lon,lat)
            x/=STEP;y/=STEP
            count=sum((px-x)**2+(py-y)**2<=25 for px,py in clean)
            targets.append({'name':name,'echo_detected':count>=7,'echo_pixels':count})
        results.append({'frame_utc':stamp,'targets':targets,
                        'complete_tiles':True,'observation_kind':'radar_echo_png'})
    return results




def _mask_for_region(info):
    """Sample official RATE onto old 1.3km world-pixel grid for conservative motion.

    Uses real CRS + 4-corner affine/bilinear transform, never image colors.
    """
    np,_,_,CRS,Transformer=_deps()
    west,south,east,north=AREA_LON_LAT
    gx0,gy0=lonlat_to_global(west,north)
    gx1,gy1=lonlat_to_global(east,south)
    sx=np.arange(int(gx0//STEP),int(gx1//STEP)+1)
    sy=np.arange(int(gy0//STEP),int(gy1//STEP)+1)
    X,Y=np.meshgrid(sx,sy)
    world_x=(X+.5)*STEP
    world_y=(Y+.5)*STEP
    n=(2**ZOOM)*TILE_SIZE
    lon=world_x/n*360-180
    lat=np.degrees(np.arctan(np.sinh(np.pi*(1-2*world_y/n))))
    tf=Transformer.from_crs(CRS.from_epsg(4326),CRS.from_user_input(info['projdef']),always_xy=True)
    px,py=tf.transform(lon,lat)
    corners=np.asarray([tf.transform(*c) for c in info['coords']])
    ul,ur,lr,ll=corners
    # The published COMP corners may be a slightly skewed quadrilateral;
    # iteratively invert a bilinear transform instead of assuming straight lat/lon.
    v=np.clip((py-ul[1])/(ll[1]-ul[1]),-1,2)
    u=np.clip((px-ul[0])/(ur[0]-ul[0]),-1,2)
    for _ in range(5):
        top=ul+np.expand_dims(u,-1)*(ur-ul)
        bottom=ll+np.expand_dims(u,-1)*(lr-ll)
        approx=top+np.expand_dims(v,-1)*(bottom-top)
        delta_x=approx[:,:,0]-px;delta_y=approx[:,:,1]-py
        dxdu=ur[0]-ul[0]+v*(lr[0]-ll[0]-ur[0]+ul[0])
        dydv=ll[1]-ul[1]+u*(lr[1]-ur[1]-ll[1]+ul[1])
        u-=np.divide(delta_x,dxdu,out=np.zeros_like(u),where=np.abs(dxdu)>1)
        v-=np.divide(delta_y,dydv,out=np.zeros_like(v),where=np.abs(dydv)>1)
    ny,nx=info['rate'].shape
    col=np.rint(u*(nx-1)).astype(int)
    row=np.rint(v*(ny-1)).astype(int)
    inside=(col>=0)&(col<nx)&(row>=0)&(row<ny)
    yc=np.clip(row,0,ny-1);xc=np.clip(col,0,nx-1)
    valid=inside & info['valid'][yc,xc]
    rates=info['rate'][yc,xc]
    hit=valid & (rates>=0.3) # detector threshold: weak drizzle excluded for motion stability
    # Only perform negative echo verification if ALL five points have sensor coverage.
    for lat0,lon0 in POINTS.values():
        wx,wy=lonlat_to_global(lon0,lat0)
        cx,cy=wx/STEP,wy/STEP
        disk=((X-cx)**2+(Y-cy)**2)<=25
        if disk.sum()<30 or (valid & disk).sum()<.8*disk.sum():
            raise ValueError('Radarikomposiidi andmekate on mõne sihtkoha juures puudulik')
    return {(int(x),int(y)) for x,y in zip(X[hit],Y[hit])}


def analyze_official(infos:list,now=None):
    """Try recent 5-min motion first; verify 10-min-baseline motion if needed.

    Five recent *actual* HDF frames allow a less quantized 20-min trajectory
    without relaxing the original displacement/shape/velocity quality gates.
    Keep the latest 3 consecutive frames for independent echo observations;
    these must not be derived from an extrapolated forecast.
    """
    now=time.time() if now is None else now
    if len(infos)<3:
        return {'quality':'unverified','motion_verified':False,'eta_verified':False,
                'reason':'Vaja on kolme päriselt loetud ametlikku radarikaadrit.','targets':[],
                'latest_frame_utc':infos[-1]['time'] if infos else None}
    recent=infos[-3:]
    stamps=[s['time'] for s in recent]
    masks=[_mask_for_region(s) for s in recent]
    result=estimate_mask_motion(masks,stamps,now)
    result['motion_window_minutes']=round((stamps[-1]-stamps[0])/60,1)
    result['motion_window']='recent_5min'
    result['long_window_attempted']=False

    # Short-interval movement may be sub-pixel. A SECOND, independent
    # two-pair comparison over 20 minutes can establish slower coherent drift.
    # Only attempt it for five consecutive KAIA ~5-minute frames and a still
    # fresh earliest frame. Never replace a confirmed 5-min estimate.
    if not result['motion_verified'] and len(infos)>=5:
        wider=infos[-5:]
        times=[s['time'] for s in wider]
        regular=all(240<=times[i+1]-times[i]<=420 for i in range(4))
        fresh=0<=now-times[0]<=35*60
        if regular and fresh:
            result['long_window_attempted']=True
            older=[_mask_for_region(s) for s in wider[:2]]
            # Timestamp order: -5, -4, -3, -2, -1.
            five=[older[0],older[1],*masks]
            # A large intermediate fade/flare makes an apparently coherent
            # two-step long baseline potentially misleading.
            counts=[len(_denoise(_filter_area(m))) for m in five]
            adequate=min(counts)>=45
            stable=all(0.55<=counts[i+1]/counts[i]<=1.8 for i in range(4)) if adequate else False
            if adequate and stable:
                candidate=estimate_mask_motion([five[0],five[2],five[4]],
                         [times[0],times[2],times[4]],now)
                if candidate['motion_verified']:
                    result=candidate
                    result['motion_window_minutes']=round((times[-1]-times[0])/60,1)
                    result['motion_window']='confirmed_10min_steps'
                    result['long_window_attempted']=True
                else:
                    result['long_window_reason']=candidate['reason']
            else:
                result['long_window_reason']='Kaadrite radarikaja katvus muutus liiga palju või jäi napiks.'

    result['observation_schema']=1
    obs=echo_observations(masks,stamps)
    for row in obs:row['observation_kind']='kaia_rate_hdf5_georeferenced';row['complete_tiles']=True
    result['echo_observations']=obs
    method='KAIA RATE: 3 järjestikust kaadrit, 5 min liikumissamm'
    if result['motion_window']=='confirmed_10min_steps':
        method='KAIA RATE: 5 järjestikust kaadrit, 2 kinnitatud 10 min liikumissammu'
    result.update({'frames_analysed':3 if result['motion_window']=='recent_5min' else 5,
                   'method':method,
                   'echo_threshold_mm_h':0.3,'image_source':'kaia_comp','latest_frame_utc':stamps[-1]})
    return result


def public_overlay(info):
    """Sample RATE in a north-up Web Mercator rectangle for Leaflet."""
    np,_,_,CRS,Transformer=_deps()
    west,south,east,north=AREA_LON_LAT
    merc=Transformer.from_crs(4326,3857,always_xy=True)
    x0,y0=merc.transform(west,north)
    x1,y1=merc.transform(east,south)
    width=520
    height=round(width*(y0-y1)/(x1-x0))
    X,Y=np.meshgrid(x0+(np.arange(width)+.5)*(x1-x0)/width,
                    y0+(np.arange(height)+.5)*(y1-y0)/height)
    crs=CRS.from_user_input(info['projdef'])
    px,py=Transformer.from_crs(3857,crs,always_xy=True).transform(X,Y)
    tf=Transformer.from_crs(4326,crs,always_xy=True)
    ul,ur,lr,ll=np.array([tf.transform(*p) for p in info['coords']])
    rate=info['rate']
    origin=np.column_stack((ur-ul,ll-ul))
    bend=lr-ur-ll+ul
    xy=np.array([(px-ul[0]).ravel(),(py-ul[1]).ravel()])
    u,v=np.linalg.solve(origin,xy)
    for _ in range(6):
        err=origin@np.array([u,v])+bend[:,None]*(u*v)-xy
        ax,ay=(ur-ul)[:,None]+bend[:,None]*v
        bx,by=(ll-ul)[:,None]+bend[:,None]*u
        det=ax*by-ay*bx
        u=u-(err[0]*by-err[1]*bx)/det
        v=v-(ax*err[1]-ay*err[0])/det
    uv=np.array([u,v])
    col,row=np.floor(uv*np.array(rate.shape[::-1])[:,None]).astype(int).reshape(2,height,width)
    valid=(row>=0)&(row<rate.shape[0])&(col>=0)&(col<rate.shape[1])
    row=row.clip(0,rate.shape[0]-1);col=col.clip(0,rate.shape[1]-1)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'radar.png'
        write_png({'rate':rate[row,col],'valid':valid & info['valid'][row,col]},path)
        return base64.b64encode(path.read_bytes()).decode('ascii')


def main():
    import sys
    now=time.time()
    with tempfile.TemporaryDirectory() as tmp:
        frames=[]
        for item in list_files(now)[-5:]:
            try:
                frames.append(read_hdf(fetch_one(item,Path(tmp)),item['time']))
            except Exception as exc:
                print('Kaadri lugemine:',exc,file=sys.stderr)
        if not frames:
            raise ValueError('KAIA värskeid kaadreid ei saadud')
        frames.sort(key=lambda f:f['time'])
        latest=frames[-1]
        try:
            result=analyze_official(frames)
        except Exception as exc:
            print('Liikumisarvutus:',exc,file=sys.stderr)
            result={'motion_verified':False,'reason':'Liikumisarvutuse andmed on puudulikud.'}
        observations=result.get('echo_observations') or []
        data={'frame':latest['time'],'image':public_overlay(latest),'bounds':AREA_LON_LAT,
              'motion':result.get('motion_verified',False),'reason':result.get('reason'),
              'direction':result.get('moving_toward'),'speed':result.get('speed_kmh_approx'),
              'targets':result.get('targets',[]),
              'observations':observations[-1]['targets'] if observations and observations[-1]['frame_utc']==latest['time'] else []}
        Path(sys.argv[1]).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

if __name__=='__main__':
    main()
