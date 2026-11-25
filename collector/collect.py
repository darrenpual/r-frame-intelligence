#!/usr/bin/env python3
"""Collect public brand discovery metadata only. No images or article copies."""
import hashlib, json, re, time, unicodedata, urllib.request, urllib.parse, urllib.robotparser
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/candidates.json"
AGENT="RFrameResearch/1.0"
TARGET=1000
def norm(x):
    return "".join(c for c in unicodedata.normalize("NFKC", x).casefold() if c.isalnum())
def host(x):
    if not x:return ""
    return (urllib.parse.urlparse(x if "://" in x else "https://"+x).hostname or "").removeprefix("www.")
def read_json(p,default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
def request(url):
    req=urllib.request.Request(url,headers={"User-Agent":AGENT,"Accept":"text/html,application/xml,text/plain"})
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status!=200:raise ValueError(f"HTTP {response.status}")
        if not any(t in response.headers.get("Content-Type","").lower() for t in ("html","xml","text")):raise ValueError("Not a text response")
        return response.read(3_000_000).decode("utf-8","replace")
class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.current=None
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            self.current=[dict(attrs).get("href",""),[]]
    def handle_data(self,data):
        if self.current:self.current[1].append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.current:
            href,parts=self.current;self.links.append((href," ".join(" ".join(parts).split())));self.current=None
def listing(url,robots):
    if not robots.can_fetch(AGENT,url):raise PermissionError("robots.txt disallows collection")
    parser=Links();parser.feed(request(url));return parser.links
def rules(origin):
    p=urllib.robotparser.RobotFileParser();p.set_url(origin+"/robots.txt")
    # Fail closed if robots.txt cannot be retrieved.
    p.parse(request(origin+"/robots.txt").splitlines());return p
html=(ROOT/"index.html").read_text(encoding="utf-8")
match=re.search(r"let records=mergeSeed\('rf_100_records',(\[.*?\])\),saved=load",html,re.S)
if not match:raise SystemExit("Cannot find existing script records; refusing to overwrite")
scripts=json.loads(match.group(1)); existing={norm(x["brand"]) for x in scripts}
old=read_json(OUT,[]); candidates=[];names=set(existing);domains=set();urls=set()
def append(row):
    name=norm(row["brand"]);domain=host(row.get("official_domain"));url=row["source_url"]
    if not name or name in names or (domain and domain in domains):return False
    # A listing URL can be shared; deduplicate individual profile URLs only.
    if "/brand/" in url and url in urls:return False
    names.add(name)
    if domain:domains.add(domain)
    urls.add(url);candidates.append(row);return True
for row in old:append(row)
start=len(candidates);errors=[];pages=0
origin="https://www.dtcetc.com"
try:
    robot=rules(origin)
    delay=max(2,robot.crawl_delay(AGENT) or 0)
    empty=0
    for page in range(1,118):
        if len(candidates)+len(scripts)>=TARGET:break
        url=origin+"/brands"+("/"+str(page) if page>1 else "")
        try:
            before=len(candidates)
            links=listing(url,robot);pages+=1
            for href,label in links:
                full=urllib.parse.urljoin(url,href)
                u=urllib.parse.urlparse(full)
                if u.netloc not in ("www.dtcetc.com","dtcetc.com") or not re.fullmatch(r"/brand/[a-zA-Z0-9_-]+/?",u.path):continue
                slug=u.path.rstrip("/").split("/")[-1]
                generic=(not label or len(label)>100 or bool(re.search(r"view brand|read more|review|score|shop now|learn more|compare|\bdetails\b|→|↗",label,re.I)))
                name=slug.replace("-"," ").title() if generic else label
                append({"brand":name,"brand_name_source":"profile_slug_unconfirmed" if generic else "directory_anchor","category":None,"official_domain":None,"source_channel":"DTCetc","source_url":origin+u.path.rstrip("/"),"discovered_on":url,"status":"candidate","growth_verified":False,"script":None,"collected_at":datetime.now(timezone.utc).isoformat(),"collection_method":"public_directory_link"})
                if len(candidates)+len(scripts)>=TARGET:break
            empty=empty+1 if len(candidates)==before else 0
            if empty>=4:break
        except Exception as e:
            errors.append({"url":url,"error":str(e)});print(url,str(e))
            if len(errors)>=3:break
        time.sleep(delay)
except Exception as e:errors.append({"url":origin,"error":str(e)})
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(candidates,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
report={"target_total":TARGET,"existing_scripts":len(scripts),"candidate_count":len(candidates),"new_candidates":len(candidates)-start,"total_unique":len(scripts)+len(candidates),"pages_fetched":pages,"errors":errors,"images_downloaded":0,"completed_at":datetime.now(timezone.utc).isoformat(),"notes":"Discovery only. No generated scripts or growth claims. Source terms must be checked before expanded collection; blocked sources are not bypassed."}
(ROOT/"data/collection-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
