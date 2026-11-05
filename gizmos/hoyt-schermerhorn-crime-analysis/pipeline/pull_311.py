"""Pull every NYC 311 request within ~450 m of Hoyt-Schermerhorn (40.6885, -73.985), 2010+."""
import requests, pandas as pd, sys, time
out=sys.argv[1]
URL="https://data.cityofnewyork.us/resource/erm2-nwe9.json"
cols="unique_key,created_date,closed_date,agency,agency_name,complaint_type,descriptor,location_type,incident_zip,incident_address,street_name,cross_street_1,cross_street_2,address_type,status,resolution_description,community_board,bbl,open_data_channel_type,latitude,longitude"
rows=[]; off=0; lim=50000
while True:
    p={"$select":cols,"$where":"within_circle(location,40.6885,-73.985,450)","$order":"unique_key","$limit":lim,"$offset":off}
    for attempt in range(5):
        r=requests.get(URL,params=p,timeout=180)
        if r.ok: break
        print("retry",r.status_code,flush=True); time.sleep(10)
    r.raise_for_status(); d=r.json()
    if not d: break
    rows.extend(d); off+=lim; print(len(rows),flush=True)
    if len(d)<lim: break
df=pd.DataFrame(rows); df.to_parquet(out); print("done",len(df))
