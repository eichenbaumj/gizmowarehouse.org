"""311 archive (76ig-c548) month by month for 2018-2019, small pages, numeric bbox instead of within_circle."""
import requests, pandas as pd, sys, time
out=sys.argv[1]
URL="https://data.cityofnewyork.us/resource/76ig-c548.json"
cols="unique_key,created_date,closed_date,agency,agency_name,complaint_type,descriptor,location_type,incident_zip,incident_address,street_name,cross_street_1,cross_street_2,address_type,status,resolution_description,community_board,bbl,open_data_channel_type,latitude,longitude"
rows=[]
for yr in (2018,2019):
    for mo in range(1,13):
        a=f"{yr}-{mo:02d}-01T00:00:00"; b=f"{yr+(mo==12)}-{(mo%12)+1:02d}-01T00:00:00"
        off=0; lim=5000
        while True:
            p={"$select":cols,"$where":f"latitude between 40.6845 and 40.6925 AND longitude between -73.9903 and -73.9797 AND created_date >= '{a}' AND created_date < '{b}'","$order":"unique_key","$limit":lim,"$offset":off}
            d=None
            for attempt in range(6):
                try:
                    r=requests.get(URL,params=p,timeout=240)
                    if r.ok: d=r.json(); break
                    print("retry",a,r.status_code,flush=True)
                except Exception as e: print("retry",a,type(e).__name__,flush=True)
                time.sleep(15)
            if d is None: raise SystemExit(f"gave up on {a}")
            rows.extend(d); off+=lim
            if len(d)<lim: break
        print(a,len(rows),flush=True)
pd.DataFrame(rows).to_parquet(out); print("done",len(rows))
