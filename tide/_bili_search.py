"""跑在刷B站插件的 venv 里，搜一条视频再把结果打成 JSON。

Tide自己是标准库、零依赖的，所以真正的 B站 访问放在这个脚本里，
由插件那边的 venv（有 bilibili_api、有登录态）执行。

用法:
    <bili-duty venv python> _bili_search.py "猫"
输出:
    {"ok": true, "items": [{bvid, title, author, play, url, cover}, ...]}
    {"error": "..."}
"""
import asyncio
import json
import sys


async def main(keyword: str) -> None:
    try:
        from bilibili_api import search
    except Exception as exc:  # 插件没装 / venv 不对
        print(json.dumps({"error": "import_failed: %s" % exc}, ensure_ascii=False))
        return
    try:
        res = await search.search_by_type(
            keyword, search_type=search.SearchObjectType.VIDEO, page=1
        )
        items = []
        for it in (res.get("result") or [])[:5]:
            title = str(it.get("title") or "")
            for a in ('<em class="keyword">', "</em>"):
                title = title.replace(a, "")
            pic = str(it.get("pic") or "")
            if pic.startswith("//"):
                pic = "https:" + pic
            bvid = str(it.get("bvid") or "")
            items.append({
                "bvid": bvid,
                "title": title,
                "author": str(it.get("author") or ""),
                "play": it.get("play"),
                "url": ("https://www.bilibili.com/video/%s" % bvid) if bvid else "",
                "cover": pic,
            })
        print(json.dumps({"ok": True, "items": items}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "猫"
    asyncio.run(main(kw))