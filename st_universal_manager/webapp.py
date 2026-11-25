import os,secrets,threading,time
from flask import Flask,request,render_template_string,abort,session
import manager as m
app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=32768
app.secret_key=secrets.token_bytes(32)
app.config.update(SESSION_COOKIE_NAME="st_universal_admin",SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Strict")
auth_cache={}
csrf=secrets.token_urlsafe(32)
lock=threading.Lock()
state={"busy":False,"lines":["Ready"],"ok":None,"hub":"","channel":""}
HUB=""
CHANNEL=""
PAGE="""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ST Universal Manager</title><style>body{font:16px system-ui,sans-serif;margin:0 auto;padding:18px;max-width:760px;color:#dde4ed;background:#18212a}fieldset{border:1px solid #52606d;border-radius:8px;margin:14px 0;padding:14px}label{display:block;margin:9px 0}input:not([type=checkbox]):not([type=radio]){box-sizing:border-box;width:100%;padding:10px;margin-top:4px;border:1px solid #687684;border-radius:5px;background:#0f1720;color:#fff}button{padding:12px 18px;background:#2879b8;color:#fff;border:0;border-radius:6px;margin:5px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#101820;padding:12px}a{color:#87ceff}small{color:#afbecb}</style>
<h2>ST Universal Manager</h2><p>기존 드라이버 ID를 확인한 뒤 업데이트합니다. 기기 삭제, 드라이버 강제 변경 및 채널 삭제는 하지 않습니다.</p>
{% if busy %}<p>작업 중 · <a href="./">로그 새로고침</a></p>{% else %}
<form method="post" action="./"><input type="hidden" name="csrf" value="{{csrf}}">
<fieldset><legend>삼성 인증 (작업 중에만 사용)</legend>
<label>임시 PAT <input name="token" type="password" autocomplete="off" placeholder="{{token_hint}}"></label>
<p><a href="https://account.smartthings.com/tokens" target="_blank" rel="noopener noreferrer">스마트폰에서 PAT 발급</a></p>
<label>허브 ID <input name="hub" value="{{hub}}" required></label>
<label>채널 ID <input name="channel" value="{{channel}}" required></label></fieldset>
<fieldset><legend>드라이버 선택</legend>{% for family in families %}<label><input type="checkbox" name="family" value="{{family}}" checked> {{family}}</label>{% endfor %}
<label><input type="checkbox" name="allow_new"> 기존 설치가 없는 패키지 신규 설치 허용 (기본 OFF)</label></fieldset>
<fieldset><legend>MQTT 자동 설정 (선택)</legend>
<label><input type="checkbox" name="embed"> 모든 선택 드라이버에 공통 접속 정보 내장</label>
<label>브로커 <input name="host" value="{{host}}"></label>
<label>포트 <input name="port" value="{{port}}" type="number"></label>
<label>사용자 <input name="user" value="{{user}}"></label>
<label>비밀번호 <input name="password" type="password" autocomplete="new-password" placeholder="{{placeholder}}"></label>
<label>사이트 <input name="site" value="{{site}}"></label>
<label><input type="checkbox" name="save"> 공통 MQTT 설정을 애드온 /data에 저장 (백업에 포함될 수 있음)</label>
<label><input type="checkbox" name="consent"> 자격 증명이 삼성 서버에 업로드되는 패키지에 포함됨을 이해했습니다. 전용 MQTT 계정을 사용합니다.</label>
<small>기존 토픽을 유지하려면 기존 site 값(home)을 유지하세요. 내장 옵션을 끄면 기존 Master 설정을 유지합니다.</small></fieldset>
<button name="action" value="forget">임시 PAT 지우기</button><button name="action" value="inventory">기존 드라이버 확인</button>
<button name="action" value="dry">빌드 및 사전 검증</button>
<label><input type="checkbox" name="confirm"> 선택 드라이버 업로드 및 업데이트 승인</label>
<button name="action" value="apply">업데이트 실행</button></form>{% endif %}
<h3>작업 로그</h3><pre>{{log}}</pre><p><small>실제 허브 적용 및 MQTT 동작은 SmartThings와 HA에서 확인하세요. 이 애드온은 HA MQTT 제어 경로에 있지 않습니다.</small></p></html>"""
def report(msg):
    with lock:state["lines"].append(str(msg)[:500]);state["lines"]=state["lines"][-150:]
def worker(token,hub,channel,families,cfg,action,allow_new):
    try:
        cli=m.CLI(token);ins,owned,assigned=cli.inventory(hub,channel)
        plan=m.make_plan(families,ins,owned,assigned,channel,allow_new)
        for p in plan:report(p["family"]+": "+p["mode"]+" "+str(p["driver_id"] or "new"))
        if action!="inventory":m.build_and_deploy(cli,hub,channel,plan,cfg,action=="apply",report)
        with lock:state["ok"]=True
    except (ValueError,RuntimeError) as e:
        # Never reflect a token or MQTT secret even if a downstream exception contains it.
        msg=str(e).replace(token,"[redacted]")
        if cfg:
            for secret in (cfg["password"],):
                if secret:msg=msg.replace(secret,"[redacted]")
        report("STOP: "+msg)
        with lock:state["ok"]=False
    except Exception:
        report("STOP: unexpected error; no automatic retry. Check installed drivers before retry.")
        with lock:state["ok"]=False
    finally:
        with lock:state["busy"]=False
def page():
    sid=session.setdefault("sid",secrets.token_urlsafe(24))
    try:cfg=m.read_config() or {}
    except Exception:cfg={}
    with lock:
        busy=state["busy"];lines="\n".join(state["lines"])
        entry=auth_cache.get(sid)
        hint="메모리의 임시 PAT 재사용 가능" if entry and entry[1]>time.monotonic() else "24시간 임시 PAT 입력"
    return render_template_string(PAGE,csrf=csrf,busy=busy,hub=state["hub"],channel=state["channel"],families=m.FAMILIES,host=cfg.get("host","192.168.0.19"),port=cfg.get("port",1883),user=cfg.get("user",""),site=cfg.get("site","home"),placeholder="저장된 암호 사용" if cfg else "MQTT 비밀번호",log=lines,token_hint=hint)
@app.before_request
def ingress_only():
    if request.remote_addr not in ("172.30.32.2","127.0.0.1","::1") and os.getenv("ST_TEST")!="1":abort(403)
@app.after_request
def headers(r):
    r.headers["Cache-Control"]="no-store";r.headers["X-Content-Type-Options"]="nosniff";r.headers["Referrer-Policy"]="no-referrer";return r
@app.route("/",methods=["GET","POST"])
def index():
    if request.method=="GET":return page()
    f=request.form
    if not secrets.compare_digest(f.get("csrf",""),csrf):abort(403)
    try:
        action=f["action"]
        sid=session.setdefault("sid",secrets.token_urlsafe(24))
        if action=="forget":
            with lock:auth_cache.pop(sid,None)
            return page()
        if action not in ("inventory","dry","apply"):raise ValueError("Invalid action")
        if action=="apply" and not f.get("confirm"):raise ValueError("Update confirmation required")
        hub=m.uuid_text(f["hub"]);channel=m.uuid_text(f["channel"]);token=f.get("token","").strip()
        if not token:
            with lock:entry=auth_cache.get(sid)
            if entry and entry[1]>time.monotonic():token=entry[0]
        supplied=bool(f.get("token","").strip())
        if not m.token_valid(token):raise ValueError("Invalid PAT")
        families=f.getlist("family")
        if not families or any(x not in m.FAMILIES for x in families):raise ValueError("Choose supported packages")
        cfg=None
        if action!="inventory" and f.get("embed"):
            if not f.get("consent"):raise ValueError("Credential upload consent required")
            old=m.read_config() or {}
            password=f.get("password") or old.get("password","")
            cfg=m.mqtt_config(f["host"],f["port"],f["user"],password,f["site"])
        with lock:
            if state["busy"]:return "Another job is active",409
            if supplied:
                for k in list(auth_cache):
                    if auth_cache[k][1]<=time.monotonic():auth_cache.pop(k,None)
                if len(auth_cache)>=8:auth_cache.pop(next(iter(auth_cache)))
                auth_cache[sid]=(token,time.monotonic()+23*3600)
            if cfg and f.get("save"):m.save_config(cfg)
            state.update(busy=True,lines=["Job started: "+action],ok=None,hub=hub,channel=channel)
        threading.Thread(target=worker,args=(token,hub,channel,families,cfg,action,bool(f.get("allow_new"))),daemon=True).start()
    except (ValueError,KeyError):return "Invalid fields or missing consent/confirmation. Return and check the form.",400
    return page()
if __name__=="__main__":app.run(host="0.0.0.0",port=8099,threaded=True,debug=False)
