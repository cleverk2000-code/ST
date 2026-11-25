"""Setup-only SmartThings API. PAT never written to config entries or disk."""
import asyncio
from urllib.parse import urlparse
from aiohttp import ClientError, ClientTimeout

BASE="https://api.smartthings.com/v1"
class ApiError(Exception):
    def __init__(self,status,operation):
        self.status=status
        super().__init__(f"SmartThings {operation}: HTTP {status}")

class Api:
    def __init__(self,session,token):
        self.session=session;self._token=token
    async def request(self,method,path,body=None,params=None):
        if not path.startswith("/") or path.startswith("//"): raise ValueError("Invalid path")
        async with self.session.request(method,BASE+path,json=body,params=params,
                headers={"Authorization":"Bearer "+self._token,"Accept":"application/json"},
                timeout=ClientTimeout(total=25),allow_redirects=False) as response:
            if response.status>=300: raise ApiError(response.status,method+" "+path.split("?")[0])
            if response.status==204: return {}
            raw=await response.read()
            if not raw: return {}
            import json
            return json.loads(raw)
    async def list(self,path,params=None):
        result=[]; seen=set()
        while True:
            page=await self.request("GET",path,params=params)
            if isinstance(page,list): return result+page
            result+=page.get("items",[])
            link=page.get("_links",{}).get("next",{}).get("href")
            if not link:return result
            parsed=urlparse(link)
            if parsed.scheme!="https" or parsed.netloc!="api.smartthings.com" or not parsed.path.startswith("/v1/") or link in seen: raise ValueError("Invalid pagination")
            seen.add(link)
            path=parsed.path[3:]+("?" + parsed.query if parsed.query else "")
            params=None
    async def devices(self): return await self.list("/devices")
    async def device(self,id): return await self.request("GET",f"/devices/{id}")
    async def status(self,id): return await self.request("GET",f"/devices/{id}/status")
    async def rules(self,loc): return await self.list("/rules",{"locationId":loc})
    async def rule(self,loc,id): return await self.request("GET",f"/rules/{id}",params={"locationId":loc})
    async def create_rule(self,loc,body): return await self.request("POST","/rules",body,{"locationId":loc})
    async def delete_rule(self,loc,id):
        try: await self.request("DELETE",f"/rules/{id}",params={"locationId":loc})
        except ApiError as exc:
            if exc.status!=404:raise
    async def delete_device(self,id):
        try: await self.request("DELETE",f"/devices/{id}")
        except ApiError as exc:
            if exc.status!=404:raise
