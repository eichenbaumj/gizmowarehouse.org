import pandas as pd, glob, os, sys
src=sys.argv[1]; out=sys.argv[2]
rows=[]
for f in sorted(glob.glob(os.path.join(src,"nyc_raw_*.csv"))):
    for ch in pd.read_csv(f, usecols=["cmplnt_num","cmplnt_fr_dt","cmplnt_fr_tm","ky_cd","juris_desc","boro_nm"], chunksize=500_000, dtype=str, low_memory=False):
        ch=ch[ch.ky_cd.isin(["101","105","106"])].copy()
        ch["year"]=ch.cmplnt_fr_dt.str[:4]; ch["hour"]=pd.to_numeric(ch.cmplnt_fr_tm.str[:2],errors="coerce")
        ch["transit"]=ch.juris_desc.str.contains("TRANSIT",na=False)
        rows.append(ch.groupby(["year","ky_cd","hour","transit","boro_nm"]).size().rename("n").reset_index())
    print(os.path.basename(f),flush=True)
pd.concat(rows).groupby(["year","ky_cd","hour","transit","boro_nm"]).n.sum().reset_index().to_csv(out,index=False)
print("done")
