"""Pull NYC 311 requests 2010-2019 (archive dataset 76ig-c548) within ~450 m of Hoyt-Schermerhorn, one year at a time."""
import requests, pandas as pd, sys, time
out=sys.argv[1]
URL="https://data.cityofnewyork.us/resource/76ig-c548.json"
cols="unique_key,created_date,closed_date,agency,agency_name,complaint_type,descriptor,location_type,incident_zip,incident_address,street_name,cross_street_1,cross_street_2,address_type,status,resolution_description,community_board,bbl,open_data_channel_type,latitude,longitude"
rows=[]
for yr in [int(y) for y in sys.argv[2].split(",")]:
    off=0; lim=20000
    while True:
        p={"$select":cols,"$where":f"within_circle(location,40.6885,-73.985,450) AND created_date >= '{yr}-01-01T00:00:00' AND created_date < '{yr+1}-01-01T00:00:00'","$order":"unique_key","$limit":lim,"$offset":off}
        d=None
        for attempt in range(6):
            try:
                r=requests.get(URL,params=p,timeout=600)
                if r.ok: d=r.json(); break
                print("retry",yr,r.status_code,r.text[:120],flush=True)
            except Exception as e:
                print("retry",yr,type(e).__name__,flush=True)
            time.sleep(20)
        if d is None: raise SystemExit(f"gave up on {yr}")
        rows.extend(d); off+=lim
        if len(d)<lim: break
    print(yr,len(rows),flush=True)
df=pd.DataFrame(rows); df.to_parquet(out); print("done",len(df))
