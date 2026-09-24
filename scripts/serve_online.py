import argparse,uvicorn
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=8000); p.add_argument('--config',default='config/online.yaml'); a=p.parse_args()
    import os; os.environ['VN_LABOR_ONLINE_CONFIG']=a.config
    uvicorn.run('vn_labor_online.api:create_app',factory=True,host=a.host,port=a.port)
