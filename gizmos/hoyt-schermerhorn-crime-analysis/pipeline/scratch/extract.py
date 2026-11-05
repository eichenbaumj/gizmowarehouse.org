import pandas as pd, glob, sys, os
src = sys.argv[1]; out = sys.argv[2]
cols = ["cmplnt_num","cmplnt_fr_dt","cmplnt_fr_tm","cmplnt_to_dt","rpt_dt","addr_pct_cd","ky_cd","ofns_desc","pd_cd","pd_desc",
        "crm_atpt_cptd_cd","law_cat_cd","boro_nm","loc_of_occur_desc","prem_typ_desc","juris_desc","jurisdiction_code",
        "parks_nm","hadevelopt","latitude","longitude","patrol_boro","station_name","transit_district",
        "susp_age_group","susp_sex","vic_age_group","vic_sex"]
LAT0,LAT1,LON0,LON1 = 40.678, 40.699, -73.998, -73.972
parts=[]
for f in sorted(glob.glob(os.path.join(src,"nyc_raw_*.csv"))):
    n=0
    for ch in pd.read_csv(f, usecols=lambda c: c in cols, chunksize=400_000, low_memory=False, dtype=str):
        lat=pd.to_numeric(ch.latitude,errors="coerce"); lon=pd.to_numeric(ch.longitude,errors="coerce")
        m=(lat.between(LAT0,LAT1))&(lon.between(LON0,LON1))
        sub=ch[m].copy(); sub["src_file"]=os.path.basename(f); parts.append(sub); n+=len(sub)
    print(os.path.basename(f), n, flush=True)
df=pd.concat(parts)
df.to_parquet(out)
print("total", len(df), "unique cmplnt", df.cmplnt_num.nunique())
