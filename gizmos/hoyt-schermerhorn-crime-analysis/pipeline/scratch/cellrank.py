import pandas as pd, numpy as np, sys, glob, os
src, grid, out = sys.argv[1:4]
g=pd.read_csv(grid)
souths=np.sort(g.south.unique()); wests=np.sort(g.west.unique())
rs=np.round(np.diff(souths).mean(),8); cs=np.round(np.diff(wests).mean(),8)
rows=[]
for yr in (2024,2025):
    f=os.path.join(src,f"nyc_raw_{yr}.csv")
    for ch in pd.read_csv(f, usecols=["cmplnt_num","cmplnt_fr_dt","ky_cd","pd_desc","prem_typ_desc","latitude","longitude"], chunksize=500_000, dtype=str, low_memory=False):
        ch=ch[ch.ky_cd.isin(["101","105","106"])].copy()
        lat=pd.to_numeric(ch.latitude,errors="coerce"); lon=pd.to_numeric(ch.longitude,errors="coerce")
        ch["row"]=np.floor((lat-souths[0])/rs).astype("Int64"); ch["col"]=np.floor((lon-wests[0])/cs).astype("Int64")
        d=ch.pd_desc.fillna("")
        ch["officer"]=d.str.contains("POLICE/PEACE|PUBLIC SERVICE|TRAFFIC AGENT")
        ch["retail"]=d.str.contains("SHOPLIFTING|CHAIN STORE|COMMERCIAL")|ch.prem_typ_desc.fillna("").str.contains("DEPARTMENT STORE|CHAIN STORE")
        rows.append(ch.groupby(["row","col","officer","retail"]).size().rename("n").reset_index())
    print(yr,flush=True)
pd.concat(rows).groupby(["row","col","officer","retail"]).n.sum().reset_index().to_csv(out,index=False)
print("spacing",rs,cs,"origin",souths[0],wests[0])
