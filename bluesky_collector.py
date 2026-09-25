#!/usr/bin/env python3
"""Sahan Journal Bluesky collector v0.1

Uses Bluesky's public AppView API (no login required) to search public posts
and optionally retrieve reply threads. Designed for newsroom impact monitoring.

Examples:
  python3 bluesky_collector.py --query 'sahanjournal.com Northern Iron'
  python3 bluesky_collector.py --query '"Sahan Journal" Northern Iron' --thread
  python3 bluesky_collector.py --articles articles.csv --output results.csv --json results.json

Input CSV may contain columns: title,url (article_url is also accepted).
"""
from __future__ import annotations
import argparse, csv, json, sys, time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API = "https://public.api.bsky.app/xrpc"
UA = "SahanJournal-CommunityCitationTracker/0.1 (+https://sahanjournal.com/)"

@dataclass
class Hit:
    query: str
    uri: str
    post_url: str
    author_handle: str
    author_display_name: str
    text: str
    created_at: str
    reply_count: int
    repost_count: int
    like_count: int
    quote_count: int
    embedded_url: str
    embedded_title: str
    match_type: str
    article_title: str = ""
    article_url: str = ""
    thread_reply_count_collected: int = 0


def api_get(nsid: str, params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    url = f"{API}/{nsid}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Bluesky API HTTP {e.code}: {body[:300]}") from e
    except URLError as e:
        raise RuntimeError(f"Could not reach Bluesky API: {e}") from e


def post_url(uri: str, handle: str) -> str:
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    who = handle or (uri.split("/")[2] if uri.startswith("at://") else "")
    return f"https://bsky.app/profile/{who}/post/{rkey}" if who and rkey else ""


def normalize(post: Dict[str, Any], query: str, article_title: str = "", article_url: str = "") -> Hit:
    author = post.get("author") or {}
    record = post.get("record") or {}
    embed = post.get("embed") or {}
    external = embed.get("external") or {}
    uri = post.get("uri", "")
    text = record.get("text", "") or ""
    eurl = external.get("uri", "") or ""
    match_type = "keyword"
    if article_url and (article_url in text or article_url == eurl):
        match_type = "direct_article_link"
    elif "sahanjournal.com" in text.lower() or "sahanjournal.com" in eurl.lower():
        match_type = "sahan_link"
    elif "sahan journal" in text.lower():
        match_type = "explicit_sahan_mention"
    return Hit(
        query=query,
        uri=uri,
        post_url=post_url(uri, author.get("handle", "")),
        author_handle=author.get("handle", "") or "",
        author_display_name=author.get("displayName", "") or "",
        text=text,
        created_at=record.get("createdAt", "") or post.get("indexedAt", "") or "",
        reply_count=int(post.get("replyCount") or 0),
        repost_count=int(post.get("repostCount") or 0),
        like_count=int(post.get("likeCount") or 0),
        quote_count=int(post.get("quoteCount") or 0),
        embedded_url=eurl,
        embedded_title=external.get("title", "") or "",
        match_type=match_type,
        article_title=article_title,
        article_url=article_url,
    )


def search_posts(query: str, limit: int = 25, sort: str = "latest", cursor: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    params: Dict[str, Any] = {"q": query, "limit": max(1, min(100, limit)), "sort": sort}
    if cursor:
        params["cursor"] = cursor
    data = api_get("app.bsky.feed.searchPosts", params)
    return data.get("posts", []), data.get("cursor")


def get_thread(uri: str, depth: int = 6) -> Dict[str, Any]:
    return api_get("app.bsky.feed.getPostThread", {"uri": uri, "depth": max(0, min(1000, depth)), "parentHeight": 1})


def flatten_replies(thread_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    root = thread_obj.get("thread") or thread_obj
    def walk(node: Dict[str, Any]) -> None:
        for child in node.get("replies") or []:
            post = child.get("post") or {}
            if post:
                out.append(post)
            walk(child)
    if isinstance(root, dict):
        walk(root)
    return out


def article_queries(title: str, url: str) -> List[str]:
    qs: List[str] = []
    if url:
        qs.append(url)
    if title:
        qs.append(f'"{title}"')
        words = [w.strip(".,:;!?()[]{}\"'") for w in title.split() if len(w.strip(".,:;!?()[]{}\"'")) >= 5]
        distinctive = " ".join(words[:6])
        if distinctive:
            qs.append(f'"Sahan Journal" {distinctive}')
    return list(dict.fromkeys(qs))


def load_articles(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out=[]
    for r in rows:
        title=(r.get("title") or r.get("headline") or "").strip()
        url=(r.get("url") or r.get("article_url") or r.get("canonical_url") or "").strip()
        if title or url:
            out.append({"title":title,"url":url})
    return out


def write_csv(path: str, hits: Iterable[Hit]) -> None:
    rows=[asdict(h) for h in hits]
    if not rows:
        rows=[]
    fields=list(Hit.__dataclass_fields__.keys())
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def main() -> int:
    ap=argparse.ArgumentParser(description="Search public Bluesky posts for Sahan Journal citations/shares")
    ap.add_argument("--query", action="append", help="Search query; may be repeated")
    ap.add_argument("--articles", help="CSV with title,url columns; generates queries per article")
    ap.add_argument("--limit", type=int, default=25, help="Max results per query (1-100)")
    ap.add_argument("--sort", choices=["latest","top"], default="latest")
    ap.add_argument("--thread", action="store_true", help="Fetch reply thread for each matched post")
    ap.add_argument("--thread-depth", type=int, default=6)
    ap.add_argument("--delay", type=float, default=0.25, help="Pause between requests")
    ap.add_argument("--output", default="bluesky_results.csv")
    ap.add_argument("--json", dest="json_path")
    args=ap.parse_args()

    jobs: List[Tuple[str,str,str]]=[]
    for q in args.query or []:
        jobs.append((q,"",""))
    if args.articles:
        for a in load_articles(args.articles):
            for q in article_queries(a["title"],a["url"]):
                jobs.append((q,a["title"],a["url"]))
    if not jobs:
        jobs=[("sahanjournal.com","","")]

    seen: Dict[str,Hit]={}
    for i,(q,title,url) in enumerate(jobs,1):
        print(f"[{i}/{len(jobs)}] {q}", file=sys.stderr)
        try:
            posts,_=search_posts(q,args.limit,args.sort)
        except Exception as e:
            print(f"  ERROR: {e}",file=sys.stderr)
            continue
        for post in posts:
            hit=normalize(post,q,title,url)
            if not hit.uri:
                continue
            existing=seen.get(hit.uri)
            if existing is None or (existing.match_type=="keyword" and hit.match_type!="keyword"):
                seen[hit.uri]=hit
        time.sleep(max(0,args.delay))

    if args.thread:
        for i,hit in enumerate(list(seen.values()),1):
            if not hit.reply_count:
                continue
            print(f"[thread {i}/{len(seen)}] {hit.post_url}",file=sys.stderr)
            try:
                data=get_thread(hit.uri,args.thread_depth)
                hit.thread_reply_count_collected=len(flatten_replies(data))
            except Exception as e:
                print(f"  THREAD ERROR: {e}",file=sys.stderr)
            time.sleep(max(0,args.delay))

    hits=sorted(seen.values(), key=lambda h:(h.created_at,h.like_count+h.repost_count+h.reply_count), reverse=True)
    write_csv(args.output,hits)
    if args.json_path:
        with open(args.json_path,"w",encoding="utf-8") as f:
            json.dump([asdict(h) for h in hits],f,indent=2,ensure_ascii=False)
    print(f"Wrote {len(hits)} unique Bluesky posts to {args.output}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
