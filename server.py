#!/usr/bin/env python3
"""Sahan Journal Community Citation Tracker v0.5.1.

Zero-dependency prototype server.
- Proxies Sahan Journal's public WordPress REST API.
- Performs low-volume Reddit discovery with Reddit's public JSON endpoints.
- Searches Bluesky using an authenticated session when BSKY_HANDLE and BSKY_APP_PASSWORD are configured; public read endpoints remain unauthenticated.
- Fetches Reddit comments and Bluesky replies for relevant threads, emphasizing
  audience/community responses rather than publisher distribution alone.

For production/high-volume Reddit monitoring, replace the public Reddit JSON adapter
with an approved Reddit Developer Platform integration.
"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from urllib.parse import urlparse, parse_qs, urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json, os, re, time, html, math
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
WP_BASE = "https://sahanjournal.com/wp-json/wp/v2"
REDDIT_BASE = "https://www.reddit.com"
BSKY_API = "https://public.api.bsky.app/xrpc"
BSKY_SERVICE = os.environ.get("BSKY_SERVICE", "https://bsky.social").rstrip("/")
BSKY_HANDLE = os.environ.get("BSKY_HANDLE", "").strip()
BSKY_APP_PASSWORD = os.environ.get("BSKY_APP_PASSWORD", "").strip()
BSKY_SESSION = {"accessJwt":"", "created":0.0}
USER_AGENT = "SahanJournal-CommunityCitationTracker/0.5.1 (contact: contact@sahanjournal.com)"
SAHAN_REDDIT = {"sahan-journal", "sahanjournalnews"}
SAHAN_BSKY = {"sahanjournal.bsky.social"}
CACHE = {}
CACHE_TTL = 300

ALLOWED_POST_PARAMS = {
    "search","after","before","categories","categories_exclude","tags","author",
    "orderby","order","page","per_page","slug","include","exclude"
}

STOP = {
    "the","and","for","with","from","that","this","into","after","before","over",
    "sahan","journal","minnesota","about","their","they","them","will","have","has",
    "how","why","what","when","where","who","more","new","news","story","stories"
}

def request_bytes(url, cache_key=None, ttl=CACHE_TTL):
    now = time.time()
    if cache_key and cache_key in CACHE and now - CACHE[cache_key][0] < ttl:
        return CACHE[cache_key][1], CACHE[cache_key][2]
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=25) as resp:
        body = resp.read()
        headers = {k:v for k,v in resp.headers.items()}
    if cache_key:
        CACHE[cache_key] = (now, body, headers)
    return body, headers

def request_json(url, cache_key=None, ttl=CACHE_TTL):
    body, headers = request_bytes(url, cache_key, ttl)
    return json.loads(body.decode("utf-8")), headers

def normalize_url(u):
    if not u: return ""
    try:
        p = urlparse(u.strip())
        host = (p.netloc or "").lower().replace("www.", "")
        path = re.sub(r"/+$", "", p.path or "")
        return f"{host}{path}".lower()
    except Exception:
        return str(u).strip().lower().rstrip("/")

def text_tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) >= 4 and w not in STOP}

def overlap_score(a, b):
    aa, bb = text_tokens(a), text_tokens(b)
    if not aa or not bb: return 0.0
    return len(aa & bb) / max(1, len(aa))

def keyword_phrase(title, n=6):
    words = [w for w in re.findall(r"[A-Za-z0-9’'-]+", title or "") if len(w) >= 4 and w.lower() not in STOP]
    return " ".join(words[:n])

def unix_iso(ts):
    try: return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception: return ""


def request_json_post(url, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    h = {"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"}
    if headers: h.update(headers)
    req = Request(url, data=body, headers=h, method="POST")
    with urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8")), {k:v for k,v in resp.headers.items()}


def bsky_auth_configured():
    return bool(BSKY_HANDLE and BSKY_APP_PASSWORD)


def bsky_access_token(force=False):
    # Access JWTs are short-lived; refreshing by creating a new app-password session
    # is acceptable for this low-volume prototype and avoids storing a refresh token.
    now=time.time()
    if not force and BSKY_SESSION.get("accessJwt") and now-BSKY_SESSION.get("created",0) < 3600:
        return BSKY_SESSION["accessJwt"]
    if not bsky_auth_configured():
        return ""
    data,_=request_json_post(
        f"{BSKY_SERVICE}/xrpc/com.atproto.server.createSession",
        {"identifier":BSKY_HANDLE,"password":BSKY_APP_PASSWORD}
    )
    token=data.get("accessJwt") or ""
    if not token:
        raise RuntimeError("Bluesky session did not return an access token")
    BSKY_SESSION["accessJwt"]=token
    BSKY_SESSION["created"]=now
    return token


def bsky_get_authenticated(nsid, params, cache_key=None, ttl=120):
    """Authenticated app.bsky request through the account PDS.

    searchPosts may return 403 from the public AppView. Authenticated requests
    are sent through the user's PDS, which proxies app.bsky calls to AppView.
    """
    now=time.time()
    if cache_key and cache_key in CACHE and now-CACHE[cache_key][0] < ttl:
        return json.loads(CACHE[cache_key][1].decode("utf-8"))
    token=bsky_access_token()
    if not token:
        raise RuntimeError("Bluesky search requires authentication. Set BSKY_HANDLE and BSKY_APP_PASSWORD.")
    url=f"{BSKY_SERVICE}/xrpc/{nsid}?"+urlencode(params,doseq=True)
    headers={"User-Agent":USER_AGENT,"Accept":"application/json","Authorization":f"Bearer {token}"}
    req=Request(url,headers=headers)
    try:
        with urlopen(req,timeout=25) as resp:
            body=resp.read()
    except HTTPError as e:
        if e.code==401:
            token=bsky_access_token(force=True)
            headers["Authorization"]=f"Bearer {token}"
            req=Request(url,headers=headers)
            with urlopen(req,timeout=25) as resp:
                body=resp.read()
        else:
            raise
    if cache_key: CACHE[cache_key]=(now,body,{})
    return json.loads(body.decode("utf-8"))


def bsky_post_url(uri, handle):
    if not uri or not handle: return ""
    rkey = uri.rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"

def bsky_get(nsid, params, cache_key=None, ttl=120):
    url = f"{BSKY_API}/{nsid}?" + urlencode(params, doseq=True)
    data, _ = request_json(url, cache_key=cache_key, ttl=ttl)
    return data

def bsky_normalize(post, article):
    author = post.get("author") or {}
    record = post.get("record") or {}
    embed = post.get("embed") or {}
    external = embed.get("external") or {}
    uri = post.get("uri") or ""
    handle = author.get("handle") or ""
    text = record.get("text") or ""
    eurl = external.get("uri") or ""
    etitle = external.get("title") or ""
    article_url = article.get("url", "")
    article_title = article.get("title", "")
    exact_url = bool(article_url and (normalize_url(eurl) == normalize_url(article_url) or normalize_url(article_url) in normalize_url(text)))
    sahan_domain = "sahanjournal.com" in (eurl + " " + text).lower()
    overlap = overlap_score(article_title, text + " " + etitle)
    publisher = handle.lower() in SAHAN_BSKY
    relevance = 0; reasons=[]
    if exact_url:
        relevance += 70; reasons.append("exact Sahan article link")
    elif sahan_domain:
        relevance += 38; reasons.append("links to Sahan Journal")
    if overlap >= .65:
        relevance += 25; reasons.append("strong headline/topic match")
    elif overlap >= .35:
        relevance += 14; reasons.append("headline/topic match")
    elif overlap >= .18:
        relevance += 7; reasons.append("partial topic match")
    if "sahan journal" in text.lower():
        relevance += 10; reasons.append("names Sahan Journal")
    if publisher:
        reasons.append("posted by Sahan account")
    return {
        "uri": uri, "post_url": bsky_post_url(uri, handle),
        "author_handle": handle, "author_display_name": author.get("displayName") or "",
        "text": text[:1800], "created_at": record.get("createdAt") or post.get("indexedAt") or "",
        "reply_count": int(post.get("replyCount") or 0), "repost_count": int(post.get("repostCount") or 0),
        "like_count": int(post.get("likeCount") or 0), "quote_count": int(post.get("quoteCount") or 0),
        "embedded_url": eurl, "embedded_title": etitle,
        "publisher_owned": publisher, "ownership": "publisher_distribution" if publisher else "independent_or_other",
        "relevance": min(100,relevance), "match_reasons": reasons,
        "article_id": article.get("id"), "article_title": article_title, "article_url": article_url,
        "replies": []
    }

def bsky_search(query, limit=15, sort="latest"):
    params={"q":query,"limit":max(1,min(100,limit)),"sort":sort}
    if bsky_auth_configured():
        data=bsky_get_authenticated("app.bsky.feed.searchPosts", params, cache_key="bsky:search:"+query, ttl=120)
    else:
        # Keep the public call as a diagnostic fallback, but current Bluesky
        # deployments may return 403 for searchPosts without a session.
        try:
            data=bsky_get("app.bsky.feed.searchPosts", params, cache_key="bsky:search:"+query, ttl=120)
        except HTTPError as e:
            if e.code==403:
                raise RuntimeError("Bluesky search returned 403. Configure BSKY_HANDLE and BSKY_APP_PASSWORD (an app password, not the account password).") from e
            raise
    return data.get("posts", [])

def flatten_bsky_replies(node, out, root_url):
    for child in (node or {}).get("replies") or []:
        post=child.get("post") or {}
        author=post.get("author") or {}; record=post.get("record") or {}
        handle=author.get("handle") or ""; body=(record.get("text") or "").strip()
        if body and handle.lower() not in SAHAN_BSKY:
            action=bool(re.search(r"\b(i|we)\s+(commented|emailed|called|submitted|signed|contacted|attended|donated|shared|sent|wrote)\b", body, re.I))
            cites="sahan" in body.lower() or "sahanjournal.com" in body.lower()
            question="?" in body; substantive=len(body)>=90; likes=int(post.get("likeCount") or 0)
            impact_score=likes+(50 if action else 0)+(20 if cites else 0)+(8 if substantive else 0)+(3 if question else 0)
            uri=post.get("uri") or ""
            out.append({
                "uri":uri,"author_handle":handle,"author_display_name":author.get("displayName") or "",
                "text":body[:1800],"created_at":record.get("createdAt") or post.get("indexedAt") or "",
                "like_count":likes,"reply_count":int(post.get("replyCount") or 0),
                "post_url":bsky_post_url(uri,handle) or root_url,
                "action_signal":action,"explicit_sahan_reference":cites,"question":question,
                "substantive":substantive,"impact_score":impact_score
            })
        flatten_bsky_replies(child,out,root_url)

def fetch_bsky_replies(post, limit=10):
    uri=post.get("uri")
    if not uri: return []
    data=bsky_get("app.bsky.feed.getPostThread", {"uri":uri,"depth":6,"parentHeight":1}, cache_key="bsky:thread:"+uri, ttl=120)
    out=[]; flatten_bsky_replies(data.get("thread") or {},out,post.get("post_url", ""))
    out.sort(key=lambda x:(x["impact_score"],x["like_count"]),reverse=True)
    return out[:limit]

def discover_bluesky(article, post_limit=5, reply_limit=8):
    title=article.get("title",""); url=article.get("url",""); phrase=keyword_phrase(title)
    queries=[]
    if url: queries.append(url)
    if title: queries.append(f'"{title}"')
    if phrase: queries.append(f'"Sahan Journal" {phrase}')
    seen={}; errors=[]
    for q in queries[:3]:
        try:
            for raw in bsky_search(q,limit=20,sort="latest"):
                post=bsky_normalize(raw,article)
                if not post.get("uri"): continue
                old=seen.get(post["uri"])
                if not old or post["relevance"]>old["relevance"]: seen[post["uri"]]=post
            time.sleep(.12)
        except HTTPError as e:
            errors.append(f"Bluesky returned HTTP {e.code} for search")
        except Exception as e:
            errors.append(str(e))
    posts=list(seen.values())
    posts.sort(key=lambda p:(p["relevance"],p["reply_count"],p["like_count"]+p["repost_count"]),reverse=True)
    posts=[p for p in posts if p["relevance"]>=20][:post_limit]
    for p in posts:
        if p["reply_count"]>0 and (p["publisher_owned"] or p["relevance"]>=55):
            try: p["replies"]=fetch_bsky_replies(p,reply_limit)
            except Exception as e: p["reply_error"]=str(e)
    return {"article":article,"queries":queries,"posts":posts,"errors":errors}

def reddit_post_from_child(child, article):
    d = child.get("data", {})
    article_url = article.get("url", "")
    article_title = article.get("title", "")
    candidate_url = d.get("url_overridden_by_dest") or d.get("url") or ""
    selftext = d.get("selftext") or ""
    title = d.get("title") or ""
    author = d.get("author") or "[deleted]"
    exact_url = bool(article_url and (normalize_url(candidate_url) == normalize_url(article_url) or normalize_url(article_url) in normalize_url(selftext)))
    sahan_domain = "sahanjournal.com" in (candidate_url + " " + selftext).lower()
    overlap = overlap_score(article_title, title + " " + selftext)
    publisher = author.lower() in SAHAN_REDDIT
    relevance = 0
    reasons = []
    if exact_url:
        relevance += 70; reasons.append("exact Sahan article link")
    elif sahan_domain:
        relevance += 38; reasons.append("links to Sahan Journal")
    if overlap >= .65:
        relevance += 25; reasons.append("strong headline/topic match")
    elif overlap >= .35:
        relevance += 14; reasons.append("headline/topic match")
    elif overlap >= .18:
        relevance += 7; reasons.append("partial topic match")
    if "sahan journal" in (title + " " + selftext).lower():
        relevance += 10; reasons.append("names Sahan Journal")
    if publisher:
        reasons.append("posted by Sahan account")
    relevance = min(100, relevance)
    permalink = d.get("permalink") or ""
    return {
        "id": d.get("id"), "fullname": d.get("name"), "title": title,
        "author": author, "subreddit": d.get("subreddit") or "",
        "created_utc": d.get("created_utc"), "created_at": unix_iso(d.get("created_utc")),
        "score": d.get("score", 0), "num_comments": d.get("num_comments", 0),
        "permalink": REDDIT_BASE + permalink if permalink.startswith("/") else permalink,
        "outbound_url": candidate_url, "selftext": selftext[:1200],
        "publisher_owned": publisher, "ownership": "publisher_distribution" if publisher else "independent_or_other",
        "relevance": relevance, "match_reasons": reasons,
        "article_id": article.get("id"), "article_title": article_title, "article_url": article_url,
        "comments": []
    }

def flatten_comments(children, post_permalink, out):
    for child in children or []:
        if child.get("kind") != "t1":
            continue
        d = child.get("data", {})
        author = d.get("author") or "[deleted]"
        body = html.unescape(d.get("body") or "").strip()
        if not body or body in {"[deleted]", "[removed]"}:
            pass
        elif author.lower() not in SAHAN_REDDIT and author.lower() != "automoderator":
            action = bool(re.search(r"\b(i|we)\s+(commented|emailed|called|submitted|signed|contacted|attended|donated|shared|sent|wrote)\b", body, re.I))
            cites = "sahan" in body.lower() or "sahanjournal.com" in body.lower()
            question = "?" in body
            substantive = len(body) >= 90
            score = int(d.get("score") or 0)
            impact_score = score + (50 if action else 0) + (20 if cites else 0) + (8 if substantive else 0) + (3 if question else 0)
            perma = d.get("permalink") or ""
            if perma.startswith("/"): perma = REDDIT_BASE + perma
            out.append({
                "id": d.get("id"), "author": author, "body": body[:1800], "score": score,
                "created_utc": d.get("created_utc"), "created_at": unix_iso(d.get("created_utc")),
                "permalink": perma or post_permalink,
                "action_signal": action, "explicit_sahan_reference": cites,
                "question": question, "substantive": substantive, "impact_score": impact_score
            })
        replies = d.get("replies")
        if isinstance(replies, dict):
            flatten_comments(replies.get("data", {}).get("children", []), post_permalink, out)

def fetch_comments(post, limit=10):
    pid = post.get("id")
    if not pid: return []
    url = f"{REDDIT_BASE}/comments/{quote(pid)}.json?" + urlencode({"limit":50,"depth":4,"sort":"top","raw_json":1})
    data, _ = request_json(url, cache_key="comments:"+pid, ttl=120)
    comments=[]
    if isinstance(data, list) and len(data) > 1:
        flatten_comments(data[1].get("data",{}).get("children",[]), post.get("permalink", ""), comments)
    comments.sort(key=lambda x: (x["impact_score"], x["score"]), reverse=True)
    return comments[:limit]

def reddit_search(query, limit=15):
    url = f"{REDDIT_BASE}/search.json?" + urlencode({"q":query,"sort":"relevance","t":"all","limit":limit,"type":"link","raw_json":1})
    data, _ = request_json(url, cache_key="search:"+query, ttl=120)
    return data.get("data", {}).get("children", [])

def discover_reddit(article, post_limit=5, comment_limit=8):
    title = article.get("title", "")
    url = article.get("url", "")
    phrase = keyword_phrase(title)
    queries = []
    if url: queries.append(url)
    if title: queries.append(f'"{title}"')
    if phrase: queries.append(f'"Sahan Journal" {phrase}')
    seen = {}
    errors=[]
    for q in queries[:3]:
        try:
            for child in reddit_search(q, limit=12):
                post = reddit_post_from_child(child, article)
                if not post.get("id"): continue
                old=seen.get(post["id"])
                if not old or post["relevance"] > old["relevance"]:
                    seen[post["id"]]=post
            time.sleep(.18)
        except HTTPError as e:
            errors.append(f"Reddit returned HTTP {e.code} for search")
        except Exception as e:
            errors.append(str(e))
    posts = list(seen.values())
    posts.sort(key=lambda p: (p["relevance"], p["num_comments"], p["score"]), reverse=True)
    # Keep plausible matches. Search can be noisy for long headlines.
    posts = [p for p in posts if p["relevance"] >= 20][:post_limit]
    for p in posts:
        # Comments are important on publisher posts; also useful on strong independent matches.
        if p["publisher_owned"] or (p["relevance"] >= 55 and p["num_comments"] > 0):
            try:
                p["comments"] = fetch_comments(p, comment_limit)
            except Exception as e:
                p["comment_error"] = str(e)
    return {"article": article, "queries": queries, "posts": posts, "errors": errors}

class Handler(SimpleHTTPRequestHandler):
    def send_json(self, obj, status=200, extra_headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k,v in extra_headers.items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)

    def proxy_wp(self, endpoint, params, cache_key=None):
        url = WP_BASE + endpoint + ("?"+urlencode(params, doseq=True) if params else "")
        try:
            body,h = request_bytes(url, cache_key=cache_key)
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            for key in ("X-WP-Total","X-WP-TotalPages"):
                if key in h: self.send_header(key,h[key])
            self.end_headers(); self.wfile.write(body)
        except HTTPError as e:
            self.send_json({"error":"Sahan WordPress API error","status":e.code,"detail":e.reason}, e.code)
        except Exception as e:
            self.send_json({"error":"Could not reach Sahan WordPress API","detail":str(e)},502)

    def do_GET(self):
        p=urlparse(self.path); q=parse_qs(p.query)
        if p.path=="/api/health":
            self.send_json({"ok":True,"version":"0.5.1","wordpress":WP_BASE,"reddit_mode":"public-json-prototype","bluesky_mode":"authenticated-search" if bsky_auth_configured() else "public-search-fallback","bluesky_auth_configured":bsky_auth_configured(),"bluesky_handle":BSKY_HANDLE if bsky_auth_configured() else "","known_bluesky_accounts":sorted(SAHAN_BSKY)}); return
        if p.path=="/api/posts":
            params={k:v for k,v in q.items() if k in ALLOWED_POST_PARAMS}
            params["status"]=["publish"]
            params["_fields"]=["id,date,modified,link,slug,title,excerpt,author,categories,tags"]
            if "per_page" not in params: params["per_page"]=["25"]
            self.proxy_wp("/posts",params); return
        if p.path=="/api/categories":
            self.proxy_wp("/categories",{"per_page":"100","orderby":"count","order":"desc","_fields":"id,name,slug,count"},"wp:categories"); return
        if p.path=="/api/users":
            self.proxy_wp("/users",{"per_page":"100","orderby":"name","order":"asc","_fields":"id,name,slug"},"wp:users"); return
        if p.path=="/api/tags":
            params={"per_page":"100","orderby":"count","order":"desc","_fields":"id,name,slug,count"}
            if q.get("search"): params["search"]=q["search"]
            self.proxy_wp("/tags",params); return
        if p.path=="/": self.path="/dashboard.html"
        return super().do_GET()

    def do_POST(self):
        p=urlparse(self.path)
        try:
            n=int(self.headers.get("Content-Length","0")); payload=json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self.send_json({"error":"Invalid JSON request"},400); return
        if p.path=="/api/reddit/discover":
            articles=payload.get("articles") or []
            max_articles=max(1,min(int(payload.get("max_articles") or 10),12))
            post_limit=max(1,min(int(payload.get("post_limit") or 5),10))
            comment_limit=max(1,min(int(payload.get("comment_limit") or 8),20))
            if not articles:
                self.send_json({"error":"No articles supplied"},400); return
            results=[]; global_errors=[]
            for a in articles[:max_articles]:
                try:
                    results.append(discover_reddit(a,post_limit,comment_limit))
                except HTTPError as e:
                    global_errors.append(f"Reddit HTTP {e.code}: {e.reason}")
                except (URLError,TimeoutError) as e:
                    global_errors.append(f"Could not reach Reddit: {e}")
                except Exception as e:
                    global_errors.append(str(e))
                time.sleep(.22)
            self.send_json({
                "results":results,"errors":global_errors,
                "known_sahan_accounts":sorted(SAHAN_REDDIT),
                "note":"Publisher-owned posts are distribution evidence; comments from other users are returned as audience/community evidence."
            }); return
        if p.path=="/api/bluesky/discover":
            articles=payload.get("articles") or []
            max_articles=max(1,min(int(payload.get("max_articles") or 10),12))
            post_limit=max(1,min(int(payload.get("post_limit") or 5),10))
            reply_limit=max(1,min(int(payload.get("reply_limit") or 8),20))
            if not articles:
                self.send_json({"error":"No articles supplied"},400); return
            results=[]; global_errors=[]
            for a in articles[:max_articles]:
                try: results.append(discover_bluesky(a,post_limit,reply_limit))
                except HTTPError as e: global_errors.append(f"Bluesky HTTP {e.code}: {e.reason}")
                except (URLError,TimeoutError) as e: global_errors.append(f"Could not reach Bluesky: {e}")
                except Exception as e: global_errors.append(str(e))
                time.sleep(.15)
            self.send_json({
                "results":results,"errors":global_errors,
                "known_sahan_accounts":sorted(SAHAN_BSKY),
                "note":"Sahan-owned Bluesky posts are distribution evidence; replies from other users are returned as audience/community evidence."
            }); return
        self.send_json({"error":"Not found"},404)

if __name__=="__main__":
    port=int(os.environ.get("PORT","8000"))
    print(f"Sahan Citation Tracker v0.5.1: http://localhost:{port}")
    print("Bluesky search auth:", "configured" if bsky_auth_configured() else "NOT configured (search may return 403)")
    ThreadingHTTPServer(("0.0.0.0",port), partial(Handler,directory=ROOT)).serve_forever()
